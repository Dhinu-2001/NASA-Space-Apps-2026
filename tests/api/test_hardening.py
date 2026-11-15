"""Stage 11 security review: HTTP hardening and the one-process production entry point. Needs no kernels or DEM."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from lunarnav_api import serve
from lunarnav_api.config import get_settings
from lunarnav_api.hardening import BodyLimitMiddleware, HeavyLimitMiddleware
from lunarnav_api.main import create_app
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

client = TestClient(create_app(), raise_server_exceptions=False)
ERROR_KEYS = {"code", "message", "field", "details", "request_id"}


def test_every_response_carries_the_security_headers():
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in r.headers["permissions-policy"]
    assert client.get("/no-such-path").headers["x-content-type-options"] == "nosniff"      # also on errors


def test_an_oversize_body_is_refused_with_a_typed_error_and_the_cors_headers_a_browser_needs():
    big = {"site": {"site_id": "im2-athena"}, "start_utc": "2027-01-15T00:00:00Z", "label": "x" * 300_000}
    r = client.post("/scenarios/evaluate", json=big, headers={"origin": "http://localhost:5173"})
    assert r.status_code == 413
    j = r.json()
    assert set(j) == ERROR_KEYS and j["code"] == "INVALID_INPUT" and j["field"] == "body"
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_a_streamed_body_without_content_length_is_limited_too():
    def chunks():
        for _ in range(40):
            yield b"x" * 10_000                                              # 400 KB in total, no declared length
    r = client.post("/scenarios/evaluate", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["code"] == "INVALID_INPUT"


def test_normal_requests_are_unaffected():
    assert client.get("/sites").status_code == 200
    assert client.post("/sites/validate", json={"lat": -85, "lon": 10}).status_code == 200


@pytest.mark.parametrize(("path", "body", "field"), [
    ("/scenarios/compare", {"sites": [{"site_id": "im2-athena"}] * 13, "start_utc_list": ["2027-01-15T00:00:00Z"]}, "sites"),
    ("/scenarios/compare", {"sites": [{"site_id": "im2-athena"}], "start_utc_list": ["2027-01-15T00:00:00Z"] * 13}, "start_utc_list"),
    ("/scenarios/compare", {"scenarios": [{"site": {"site_id": "im2-athena"}, "start_utc": "2027-01-15T00:00:00Z"}] * 13}, "scenarios"),
    ("/scenarios/delay", {"site": {"site_id": "im2-athena"}, "baseline_start_utc": "2027-01-15T00:00:00Z", "offsets_days": [1.0] * 11}, "offsets_days"),
    ("/scenarios/evaluate", {"site": {"site_id": "im2-athena"}, "start_utc": "2027-01-15T00:00:00Z", "label": "x" * 121}, "label"),
])
def test_list_and_label_sizes_are_bounded_before_any_work_is_done(path, body, field):
    r = client.post(path, json=body)
    assert r.status_code == 422, r.text
    j = r.json()
    assert set(j) == ERROR_KEYS and j["code"] == "INVALID_INPUT" and j["field"].split(".")[0] == field


# ---------------------------------------------------------------- the compute limiter, in isolation

def _slow_app(limit: int, queue_seconds: float):
    async def slow(request):
        await asyncio.sleep(0.4)
        return JSONResponse({"ok": True})

    async def fast(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/visibility/slow", slow), Route("/health", fast)])
    return HeavyLimitMiddleware(app, limit=limit, queue_seconds=queue_seconds)


def test_the_limiter_lets_the_allowed_number_run_and_answers_the_rest_with_a_typed_503():
    async def go():
        transport = httpx.ASGITransport(app=_slow_app(limit=1, queue_seconds=0.1))
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await asyncio.gather(c.get("/visibility/slow"), c.get("/visibility/slow"), c.get("/health"))
    a, b, health = asyncio.run(go())
    codes = sorted([a.status_code, b.status_code])
    assert codes == [200, 503]
    busy = a if a.status_code == 503 else b
    j = busy.json()
    assert set(j) == ERROR_KEYS and j["code"] == "SERVER_BUSY" and busy.headers["retry-after"] == "15"
    assert health.status_code == 200                                         # cheap endpoints are never queued


def test_waiting_requests_are_served_when_a_slot_frees_within_the_queue_time():
    async def go():
        transport = httpx.ASGITransport(app=_slow_app(limit=1, queue_seconds=2.0))
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await asyncio.gather(c.get("/visibility/slow"), c.get("/visibility/slow"))
    assert [r.status_code for r in asyncio.run(go())] == [200, 200]


def test_the_body_limiter_passes_small_bodies_through():
    async def echo(request):
        return JSONResponse({"n": len(await request.body())})
    app = BodyLimitMiddleware(Starlette(routes=[Route("/", echo, methods=["POST"])]), max_bytes=100)

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.post("/", content=b"x" * 50), await c.post("/", content=b"x" * 101)
    ok, too_big = asyncio.run(go())
    assert ok.json() == {"n": 50} and too_big.status_code == 413


# ---------------------------------------------------------------- the one-process production entry point

@pytest.fixture
def serving(monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Lunar Landing Site Navigator</title>", encoding="utf-8")
    (dist / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setenv("LUNARNAV_WEB_DIST", str(dist))
    get_settings.cache_clear()
    yield TestClient(serve.create_serving_app(), raise_server_exceptions=False)
    get_settings.cache_clear()


def test_the_ui_and_the_api_are_served_from_one_origin(serving):
    page = serving.get("/")
    assert page.status_code == 200 and "Lunar Landing Site Navigator" in page.text
    assert page.headers["cache-control"] == "no-cache"                         # the HTML must revalidate
    csp = page.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "https://trek.nasa.gov" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-eval" not in csp and "script-src 'self' 'unsafe-inline'" not in csp
    health = serving.get("/api/health")
    assert health.status_code == 200 and health.json()["status"] == "ok"
    assert health.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in health.headers                      # the API keeps its own policy
    assert serving.get("/api/docs").status_code == 200                           # API documentation stays available


def test_hashed_assets_may_be_cached_and_unknown_paths_404(serving):
    asset = serving.get("/assets/app-abc123.js")
    assert asset.status_code == 200 and "cache-control" not in asset.headers or asset.headers["cache-control"] != "no-cache"
    assert serving.get("/missing.js").status_code == 404
    assert serving.get("/api/not-a-route").status_code == 404


def test_without_a_built_ui_the_api_still_works_and_the_root_says_what_to_do(monkeypatch, tmp_path):
    monkeypatch.setenv("LUNARNAV_WEB_DIST", str(tmp_path / "missing"))
    get_settings.cache_clear()
    try:
        c = TestClient(serve.create_serving_app(), raise_server_exceptions=False)
        assert "npm run build" in c.get("/").text
        assert c.get("/api/health").status_code == 200
    finally:
        get_settings.cache_clear()
