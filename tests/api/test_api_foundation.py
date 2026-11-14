from fastapi.testclient import TestClient
from lunarnav import MODEL_VERSION
from lunarnav_api.main import create_app

client = TestClient(create_app(), raise_server_exceptions=False)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_version"] == MODEL_VERSION
    assert body["time_utc"].endswith("Z")
    assert r.headers["x-request-id"]


def test_request_id_is_echoed():
    r = client.get("/health", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


def test_version_lists_unbuilt_capabilities_honestly():
    body = client.get("/version").json()
    assert body["stage"] == 2
    assert "No ephemeris, horizon or visibility results" in body["notice"]
    by_key = {c["key"]: c["status"] for c in body["capabilities"]}
    assert by_key["sites"] == by_key["dem"] == "implemented_unvalidated"
    assert by_key["ephemeris"] == by_key["horizon"] == by_key["visibility"] == "not_implemented"
    assert "validated" not in by_key.values()


def test_not_implemented_uses_error_contract():
    r = client.post("/scenarios/evaluate", json={})
    assert r.status_code == 501
    body = r.json()
    assert body["code"] == "NOT_IMPLEMENTED"
    assert set(body) == {"code", "message", "field", "details", "request_id"}


def test_unhandled_exception_returns_internal_error_without_leaking_details():
    app = create_app()

    @app.get("/_boom")
    def boom():
        raise RuntimeError("secret internal detail")

    r = TestClient(app, raise_server_exceptions=False).get("/_boom")
    body = r.json()
    assert r.status_code == 500
    assert body["code"] == "INTERNAL" and "secret" not in body["message"]
    assert body["request_id"]


def test_engine_error_maps_to_http_status_and_contract():
    from lunarnav.errors import DataMissingError

    app = create_app()

    @app.get("/_missing")
    def missing():
        raise DataMissingError("DEM window not cached", field="dem", details={"product": "x"})

    r = TestClient(app, raise_server_exceptions=False).get("/_missing")
    assert r.status_code == 503
    assert r.json()["code"] == "DATA_MISSING" and r.json()["field"] == "dem"


def test_request_validation_error_uses_error_contract():
    from pydantic import BaseModel

    class Body(BaseModel):
        lat: float

    app = create_app()

    @app.post("/_validate")
    def validate(body: Body):
        return body

    r = TestClient(app, raise_server_exceptions=False).post("/_validate", json={"lat": "abc"})
    body = r.json()
    assert r.status_code == 422
    assert body["code"] == "INVALID_INPUT" and body["field"] == "lat"
    assert set(body) == {"code", "message", "field", "details", "request_id"}


def test_unknown_route_is_404():
    assert client.get("/nope").status_code == 404


def test_cors_allows_dev_frontend():
    r = client.get("/health", headers={"origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
