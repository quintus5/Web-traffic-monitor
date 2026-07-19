"""
Tests for the dashboard HTTP Basic authentication middleware.
"""
import base64
import pytest
from fastapi.testclient import TestClient

from tests.conftest import test_engine, Base
from config.settings import settings
from api.main import app


def _auth_header(user, pw):
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture(scope="module")
def auth_client():
    Base.metadata.create_all(bind=test_engine)
    prev = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    settings.ADMIN_USERNAME = "boss"
    settings.ADMIN_PASSWORD = "s3cret"
    with TestClient(app) as c:
        yield c
    settings.AUTH_ENABLED = prev


def test_no_credentials_rejected(auth_client):
    r = auth_client.get("/api/v1/health")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


def test_wrong_password_rejected(auth_client):
    r = auth_client.get("/api/v1/health", headers=_auth_header("boss", "wrong"))
    assert r.status_code == 401


def test_correct_credentials_accepted(auth_client):
    r = auth_client.get("/api/v1/health", headers=_auth_header("boss", "s3cret"))
    assert r.status_code == 200


def test_ca_cert_exempt_from_auth(auth_client):
    # CA cert download must work without login (employees need it).
    # Returns 404 here because no cert exists in the test env — but NOT 401.
    r = auth_client.get("/ca-cert.pem")
    assert r.status_code != 401


def test_unicode_password_accepted(auth_client):
    # secrets.compare_digest rejects non-ASCII str; comparing bytes must let a
    # correct unicode password through instead of silently locking the admin out.
    prev = settings.ADMIN_PASSWORD
    settings.ADMIN_PASSWORD = "Sécür3!"
    try:
        r = auth_client.get("/api/v1/health", headers=_auth_header("boss", "Sécür3!"))
        assert r.status_code == 200
        bad = auth_client.get("/api/v1/health", headers=_auth_header("boss", "wrong"))
        assert bad.status_code == 401
    finally:
        settings.ADMIN_PASSWORD = prev


def test_server_error_not_masked_as_401(auth_client):
    # A downstream route error must surface as a 500, not be swallowed by the
    # auth middleware and reported to the client as a misleading 401.
    def _boom():
        raise RuntimeError("boom")

    app.add_api_route("/api/v1/__boom_test", _boom)
    # Move it ahead of the SPA static catch-all mount so it actually matches.
    app.router.routes.insert(0, app.router.routes.pop())
    client = TestClient(app, raise_server_exceptions=False)

    # Wrong creds never reach the route -> clean 401.
    assert client.get("/api/v1/__boom_test").status_code == 401
    # Correct creds reach the route, which raises -> 500, not 401.
    r = client.get("/api/v1/__boom_test", headers=_auth_header("boss", "s3cret"))
    assert r.status_code == 500
