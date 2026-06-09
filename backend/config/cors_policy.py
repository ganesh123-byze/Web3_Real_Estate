"""CORS policy helpers — origin lists, Vercel preview matching, response headers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

_VERCEL_HOST_SUFFIX = ".vercel.app"


@dataclass(frozen=True)
class CorsPolicy:
    allowed_origins: tuple[str, ...]
    allowed_origin_regex: str | None

    def is_origin_allowed(self, origin: str | None) -> bool:
        normalized = normalize_origin(origin or "")
        if not normalized:
            return False
        if normalized in self.allowed_origins:
            return True
        if self.allowed_origin_regex:
            return bool(re.fullmatch(self.allowed_origin_regex, normalized))
        return False


def normalize_origin(origin: str) -> str:
    """Strip trailing slash; browsers send scheme + host (+ port), no path."""
    return (origin or "").strip().rstrip("/")


def _hostname_from_origin(origin: str) -> str:
    return (urlparse(origin).hostname or "").lower()


def _vercel_slug_from_origin(origin: str) -> str | None:
    host = _hostname_from_origin(origin)
    if not host.endswith(_VERCEL_HOST_SUFFIX):
        return None
    slug = host[: -len(_VERCEL_HOST_SUFFIX)]
    return slug or None


def vercel_base_slug(slugs: Iterable[str]) -> str | None:
    """
    Pick the shortest Vercel project slug that prefixes every configured slug.

    Example: ``web3-real-estate`` + ``web3-real-estate-zeta`` → ``web3-real-estate``
    so previews like ``web3-real-estate-git-main-*.vercel.app`` are allowed.
    """
    unique = sorted({s.strip() for s in slugs if s and s.strip()}, key=len)
    if not unique:
        return None
    for candidate in unique:
        if all(item == candidate or item.startswith(f"{candidate}-") for item in unique):
            return candidate
    return unique[0]


def build_vercel_origin_regex(origins: Iterable[str]) -> str | None:
    """Derive a regex that allows production + preview URLs for the same Vercel project."""
    slugs = []
    for origin in origins:
        slug = _vercel_slug_from_origin(origin)
        if slug:
            slugs.append(slug)
    base = vercel_base_slug(slugs)
    if not base:
        return None
    return rf"https://{re.escape(base)}[\w-]*\.vercel\.app"


def merge_cors_origins(
    *,
    cors_origins_env: str,
    frontend_url: str,
    backend_url: str,
    deploy_env: str,
) -> list[str]:
    origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
    if frontend_url:
        origins.append(frontend_url.rstrip("/"))
    if backend_url:
        origins.append(backend_url.rstrip("/"))
    if not origins and deploy_env != "production":
        origins.extend([
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ])
    if deploy_env == "production" and not origins:
        raise RuntimeError("CORS_ORIGINS or FRONTEND_URL must be configured in production")
    return list(dict.fromkeys(normalize_origin(origin) for origin in origins))


def build_cors_policy(
    *,
    cors_origins_env: str,
    frontend_url: str,
    backend_url: str,
    cors_origin_regex_env: str,
    deploy_env: str,
) -> CorsPolicy:
    allowed_origins = merge_cors_origins(
        cors_origins_env=cors_origins_env,
        frontend_url=frontend_url,
        backend_url=backend_url,
        deploy_env=deploy_env,
    )
    regex = (cors_origin_regex_env or "").strip() or None
    if not regex:
        regex = build_vercel_origin_regex(allowed_origins)
    return CorsPolicy(
        allowed_origins=tuple(allowed_origins),
        allowed_origin_regex=regex,
    )


def cors_headers_for_request(policy: CorsPolicy, origin: str | None) -> dict[str, str]:
    """Headers to attach when middleware did not run (e.g. some exception paths)."""
    normalized = normalize_origin(origin or "")
    if not policy.is_origin_allowed(normalized):
        return {}
    return {
        "Access-Control-Allow-Origin": normalized,
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
    }
