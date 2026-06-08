"""CORS policy — Vercel preview URLs and error-response headers."""
from backend.config.cors_policy import (
    CorsPolicy,
    build_cors_policy,
    build_vercel_origin_regex,
    cors_headers_for_request,
    vercel_base_slug,
)


def test_vercel_base_slug_picks_shortest_common_prefix():
    assert vercel_base_slug(["web3-real-estate", "web3-real-estate-zeta"]) == "web3-real-estate"


def test_vercel_regex_allows_production_and_zeta_preview():
    regex = build_vercel_origin_regex(["https://web3-real-estate.vercel.app"])
    assert regex is not None
    policy = CorsPolicy(allowed_origins=(), allowed_origin_regex=regex)
    assert policy.is_origin_allowed("https://web3-real-estate.vercel.app")
    assert policy.is_origin_allowed("https://web3-real-estate-zeta.vercel.app")
    assert policy.is_origin_allowed("https://web3-real-estate-git-main-user.vercel.app")
    assert not policy.is_origin_allowed("https://other-project.vercel.app")


def test_build_cors_policy_merges_frontend_and_cors_origins():
    policy = build_cors_policy(
        cors_origins_env="https://web3-real-estate-zeta.vercel.app",
        frontend_url="https://web3-real-estate.vercel.app",
        backend_url="https://web3-real-estate.onrender.com",
        cors_origin_regex_env="",
        deploy_env="production",
    )
    assert "https://web3-real-estate-zeta.vercel.app" in policy.allowed_origins
    assert "https://web3-real-estate.vercel.app" in policy.allowed_origins
    assert policy.allowed_origin_regex is not None
    assert policy.is_origin_allowed("https://web3-real-estate-zeta.vercel.app")


def test_cors_headers_for_allowed_origin():
    policy = CorsPolicy(
        allowed_origins=("https://web3-real-estate-zeta.vercel.app",),
        allowed_origin_regex=None,
    )
    headers = cors_headers_for_request(policy, "https://web3-real-estate-zeta.vercel.app")
    assert headers["Access-Control-Allow-Origin"] == "https://web3-real-estate-zeta.vercel.app"
    assert headers["Access-Control-Allow-Credentials"] == "true"


def test_cors_headers_empty_for_unknown_origin():
    policy = CorsPolicy(allowed_origins=("https://example.com",), allowed_origin_regex=None)
    assert cors_headers_for_request(policy, "https://evil.example") == {}
