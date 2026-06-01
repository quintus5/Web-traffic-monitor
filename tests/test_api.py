"""
Integration tests for the FastAPI endpoints.
DB is patched to in-memory SQLite via conftest.py.
"""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import test_engine, TestSessionLocal, Base
from api.database import get_db
from api.main import app


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True, scope="module")
def db_tables():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="module")
def client(db_tables):
    with TestClient(app) as c:
        yield c


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "log_count" in data


def test_employees_empty(client):
    r = client.get("/api/v1/employees")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_employee(client):
    r = client.post("/api/v1/employees", json={"username": "testuser", "email": "test@co.com"})
    assert r.status_code == 201
    data = r.json()
    assert data["username"] == "testuser"
    assert data["id"] > 0


def test_duplicate_employee(client):
    client.post("/api/v1/employees", json={"username": "dupe_user"})
    r = client.post("/api/v1/employees", json={"username": "dupe_user"})
    assert r.status_code == 409


def test_add_ip(client):
    emp = client.post("/api/v1/employees", json={"username": "ipuser"}).json()
    r = client.post(f"/api/v1/employees/{emp['id']}/ips",
                    json={"ip_address": "10.0.0.5", "label": "Laptop"})
    assert r.status_code == 201
    assert r.json()["ip_address"] == "10.0.0.5"


def test_traffic_empty(client):
    r = client.get("/api/v1/traffic")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_schedule_get(client):
    r = client.get("/api/v1/schedule")
    assert r.status_code == 200
    data = r.json()
    assert "work_start" in data
    assert "work_end" in data


def test_schedule_update(client):
    r = client.put("/api/v1/schedule", json={
        "timezone": "America/New_York",
        "work_start": "08:00:00",
        "work_end": "17:00:00",
        "breaks": [{"label": "Lunch", "break_start": "12:00:00", "break_end": "13:00:00"}],
    })
    assert r.status_code == 200
    assert r.json()["timezone"] == "America/New_York"


def test_categories_seeded(client):
    r = client.get("/api/v1/categories")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert "social" in names
    assert "work_tools" in names


def test_test_domain(client):
    r = client.get("/api/v1/categories/test-domain?domain=youtube.com")
    assert r.status_code == 200
    assert r.json()["matched_category"] == "video_streaming"


def test_reports_empty(client):
    r = client.get("/api/v1/reports/top-sites")
    assert r.status_code == 200
    assert r.json() == []


def test_export_csv_headers(client):
    r = client.get("/api/v1/export/csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "timestamp" in r.text
