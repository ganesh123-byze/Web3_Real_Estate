#!/usr/bin/env python3
"""Call POST /properties/stream with high values and print every SSE step."""
from __future__ import annotations

import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

# Repo root on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import httpx

from backend.api.routers.properties import _log_create_property_economics, _token_sale_price_eth
from backend.api.schemas import PropertyCreate
from backend.db.connection import get_connection
from backend.services.auth import get_user_by_wallet, issue_session
from backend.services.blockchain import to_wei


def _economics_preview(payload: PropertyCreate) -> None:
    token_price_wei = str(to_wei(_token_sale_price_eth(payload)))
    monthly = (
        str(to_wei(payload.monthly_rent_eth))
        if payload.monthly_rent_eth is not None
        else None
    )
    _log_create_property_economics(
        source="diagnose_script",
        payload=payload,
        token_price_wei=token_price_wei,
        monthly_rent_wei=monthly,
        owner_wallet=os.getenv("ADMIN_WALLET_ADDRESS", "") or "",
    )
    sale = _token_sale_price_eth(payload)
    print("\n--- Economics preview ---")
    print(f"  total_value ETH     : {payload.total_value}")
    print(f"  token_supply        : {payload.token_supply}")
    print(f"  sale_price_eth      : {sale}")
    print(f"  token_price_wei     : {token_price_wei}")
    print(f"  wei digit length    : {len(token_price_wei)}")
    print(f"  monthly_rent_eth    : {payload.monthly_rent_eth}")
    print("-------------------------\n")


def _owner_user():
    wallet = (os.getenv("ADMIN_WALLET_ADDRESS") or "").strip()
    if not wallet:
        raise SystemExit("ADMIN_WALLET_ADDRESS missing in .env")
    db = get_connection()
    user = get_user_by_wallet(db, wallet)
    if not user:
        db.close()
        raise SystemExit(f"No DB user for {wallet}. Sign in once via the UI.")
    # API requires property_owner; wallet may be registered as another role in DB.
    from backend.services.auth import AuthUser

    owner = AuthUser(
        id=user.id,
        wallet_address=user.wallet_address,
        role="property_owner",
        email=user.email,
        kyc_status=user.kyc_status,
        active=user.active,
    )
    return db, owner


def _auth_token() -> str:
    db, owner = _owner_user()
    try:
        session = issue_session(db, wallet_address=owner.wallet_address, role="property_owner")
        return session.token
    finally:
        db.close()


def _stream_create(base_url: str, token: str, payload: dict) -> int:
    url = f"{base_url.rstrip('/')}/properties/stream"
    print(f"POST {url}")
    print("payload:", json.dumps(payload, indent=2))

    failed_step: str | None = None
    last_step: str | None = None
    property_id: int | None = None

    timeout = httpx.Timeout(600.0, connect=60.0, read=600.0, write=60.0, pool=60.0)
    with httpx.Client(timeout=timeout) as client:
        with client.stream(
            "POST",
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "text/event-stream",
            },
        ) as response:
            print(f"HTTP {response.status_code}")
            if response.status_code != 200:
                print(response.read().decode("utf-8", errors="replace")[:2000])
                return 1

            buffer = ""
            for chunk in response.iter_bytes():
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n\n" in buffer:
                    part, buffer = buffer.split("\n\n", 1)
                    for line in part.split("\n"):
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        if not raw:
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            print("  [parse error]", raw[:200])
                            continue
                        step = event.get("step")
                        last_step = step
                        if step == "error":
                            failed_step = event.get("failed_step") or failed_step
                            print("  ERROR:", json.dumps(event, indent=2))
                        elif step == "done":
                            prop = event.get("property") or {}
                            property_id = prop.get("id") or event.get("property_id")
                            print("  DONE:", f"id={property_id}", f"token={prop.get('token_address')}")
                        else:
                            detail = event.get("detail")
                            extra = f" detail={detail!r}" if detail else ""
                            print(f"  {step}{extra}")

    print("\n--- Summary ---")
    print(f"  last_step   : {last_step}")
    print(f"  failed_step : {failed_step}")
    print(f"  property_id : {property_id}")
    return 0 if last_step == "done" else 1


def _direct_create(total: str, supply: str) -> int:
    """Run create_property_record in-process (same as POST /properties)."""
    from backend.api._helpers import create_property_record
    from backend.services.blockchain import get_web3

    get_web3()
    if not get_web3().is_connected():
        print("WARNING: Web3 RPC not connected — deploy will likely fail")

    sale = Decimal(total) / Decimal(supply)
    payload_model = PropertyCreate(
        name=f"diag-direct-{int(time.time())}",
        location="Hyderabad",
        total_value=Decimal(total),
        token_supply=Decimal(supply),
        token_symbol="DHT",
        token_sale_price_eth=sale,
        monthly_rent_eth=Decimal("99"),
        images=[],
    )
    _economics_preview(payload_model)
    db, owner = _owner_user()
    print("Direct create_property_record (on-chain deploy)…")
    try:
        row = create_property_record(db, owner, payload_model)
        print(
            "SUCCESS id=%s token_address=%s supply=%s sold=%s available=%s"
            % (
                row.get("id"),
                row.get("token_address"),
                row.get("token_supply"),
                row.get("tokens_sold"),
                row.get("tokens_available"),
            )
        )
        return 0
    except Exception as exc:
        print("FAILED:", type(exc).__name__, exc)
        return 1
    finally:
        db.close()


def main() -> None:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "direct").lower()
    if mode == "http":
        base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
        total = sys.argv[3] if len(sys.argv) > 3 else "100000000"
        supply = sys.argv[4] if len(sys.argv) > 4 else "10002"
        sale = Decimal(total) / Decimal(supply)
        payload_model = PropertyCreate(
            name=f"diag-high-{int(time.time())}",
            location="Hyderabad",
            total_value=Decimal(total),
            token_supply=Decimal(supply),
            token_symbol="DHT",
            token_sale_price_eth=sale,
            monthly_rent_eth=Decimal("99"),
            images=[],
        )
        _economics_preview(payload_model)
        token = _auth_token()
        body = {
            "name": payload_model.name,
            "location": payload_model.location,
            "total_value": str(payload_model.total_value),
            "token_supply": str(payload_model.token_supply),
            "token_symbol": payload_model.token_symbol,
            "token_sale_price_eth": str(sale),
            "monthly_rent_eth": "99",
            "images": [],
        }
        raise SystemExit(_stream_create(base, token, body))

    total = sys.argv[2] if len(sys.argv) > 2 else "100000000"
    supply = sys.argv[3] if len(sys.argv) > 3 else "10002"
    raise SystemExit(_direct_create(total, supply))


if __name__ == "__main__":
    main()
