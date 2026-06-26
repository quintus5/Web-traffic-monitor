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
