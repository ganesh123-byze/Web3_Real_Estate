from contextlib import asynccontextmanager
from pathlib import Path
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.ai.checkpointer import close_checkpointer, setup_checkpointer
from backend.api.routes import router as api_router
from backend.config.cors_policy import cors_headers_for_request
from backend.config.settings import (
    get_cors_policy,
    validate_required_settings,
    LOG_LEVEL,
    RUN_INDEXER_IN_WEB,
)
from backend.db.schema import init_db
from backend.services.blockchain_indexer import start_background_indexer, stop_background_indexer

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"

@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_required_settings()
    init_db()
    try:
        from backend.services.blockchain import platform_deployer_mismatch

        mismatch = platform_deployer_mismatch()
        if mismatch:
            logging.getLogger(__name__).warning(
                "Platform deployer mismatch: %s", mismatch.get("message")
            )
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).debug("Deployer mismatch check skipped: %s", exc)
    try:
        await setup_checkpointer()
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("LangGraph checkpointer init failed (optional): %s", exc)
    if RUN_INDEXER_IN_WEB:
        logging.getLogger(__name__).info(
            "Starting blockchain indexer in the web process (RUN_INDEXER_IN_WEB=true). "
            "Single-instance default (e.g. Render). If you run multiple web replicas, "
            "use one dedicated indexer: `python -m backend.worker` and set RUN_INDEXER_IN_WEB=false."
        )
        start_background_indexer()
    else:
        logging.getLogger(__name__).info(
            "Blockchain indexer not started in this process (RUN_INDEXER_IN_WEB=false). "
            "Optional: run `python -m backend.worker` as a dedicated indexer if you split processes."
        )
    try:
        yield
    finally:
        if RUN_INDEXER_IN_WEB:
            stop_background_indexer()
        await close_checkpointer()

app = FastAPI(title="Real Estate Web3 Backend", lifespan=lifespan)

_cors_policy = get_cors_policy()
if _cors_policy.allowed_origins or _cors_policy.allowed_origin_regex:
    logging.getLogger(__name__).info(
        "CORS enabled: %d explicit origin(s)%s",
        len(_cors_policy.allowed_origins),
        f", regex={_cors_policy.allowed_origin_regex!r}"
        if _cors_policy.allowed_origin_regex
        else "",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_cors_policy.allowed_origins),
        allow_origin_regex=_cors_policy.allowed_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _json_with_cors(
    request: Request,
    content: dict,
    *,
    status_code: int,
) -> JSONResponse:
    """Ensure API errors still carry CORS headers (browser would otherwise hide the real fault)."""
    response = JSONResponse(content, status_code=status_code)
    for key, value in cors_headers_for_request(_cors_policy, request.headers.get("origin")).items():
        response.headers[key] = value
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    content = detail if isinstance(detail, dict) else {"detail": detail}
    return _json_with_cors(request, content, status_code=exc.status_code)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logging.exception("Unhandled exception during request: %s", exc)
    return _json_with_cors(request, {"detail": "Internal server error."}, status_code=500)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.warning("Request validation error: %s", exc)
    errors = exc.errors()
    detail = "Invalid request payload."
    if errors:
        first = errors[0]
        loc = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
        msg = str(first.get("msg") or "")
        if loc and msg:
            detail = f"{loc}: {msg}"
        elif msg:
            detail = msg
    return _json_with_cors(
        request,
        {"detail": detail, "errors": errors},
        status_code=422,
    )


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
app.include_router(api_router)


@app.get("/runtime-config.js")
def serve_runtime_config():
    config_path = FRONTEND_DIR / "runtime-config.js"
    if config_path.exists():
        return FileResponse(str(config_path), media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Runtime config not found")


@app.get("/")
def serve_frontend():
	index_path = FRONTEND_DIR / "index.html"
	if index_path.exists():
		return FileResponse(str(index_path))
	return {"status": "ok"}


# Serve role-specific dashboard entrypoints (support SPA client-side routing)
def _serve_role_index(role: str):
	role_index = FRONTEND_DIR / role / "index.html"
	if role_index.exists():
		return FileResponse(str(role_index))
	# fallback to main index
	fallback = FRONTEND_DIR / "index.html"
	if fallback.exists():
		return FileResponse(str(fallback))
	return {"status": "ok"}


@app.get("/investor")
@app.get("/investor/")
def serve_investor_index():
	return _serve_role_index("investor")


@app.get("/investor/{path:path}")
def serve_investor_spa(path: str):
	return _serve_role_index("investor")


@app.get("/property_owner")
@app.get("/property_owner/")
def serve_property_owner_index():
	return _serve_role_index("property_owner")


@app.get("/property_owner/{path:path}")
def serve_property_owner_spa(path: str):
	return _serve_role_index("property_owner")


@app.get("/tenant")
@app.get("/tenant/")
def serve_tenant_index():
	return _serve_role_index("tenant")


@app.get("/tenant/{path:path}")
def serve_tenant_spa(path: str):
	return _serve_role_index("tenant")
