"""
Regression tests for defects found by the break-and-fix stress workflow.
Each test locks in one confirmed fix. DB is the in-memory SQLite from conftest
(auth is disabled there); writer/categorizer unit tests use isolated file DBs.
"""
import time as _time
from datetime import datetime
from queue import Queue

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker

from tests.conftest import test_engine, TestSessionLocal, Base
from api.database import get_db
from api import models
from api.main import app
from proxy.categorizer import Categorizer, is_safe_regex
from proxy.writer import DatabaseWriter


def _override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=test_engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=test_engine)


# ── Finding: PUT update handlers 500 on duplicate unique name ───────────────────

def test_update_employee_duplicate_name_returns_409(client):
    a = client.post("/api/v1/employees", json={"username": "reg_alice"}).json()
    b = client.post("/api/v1/employees", json={"username": "reg_bob"}).json()
    r = client.put(f"/api/v1/employees/{b['id']}", json={"username": "reg_alice"})
    assert r.status_code == 409
    # Renaming to its own current name must still succeed (no false positive).
    same = client.put(f"/api/v1/employees/{b['id']}", json={"username": "reg_bob"})
    assert same.status_code == 200


def test_update_category_duplicate_name_returns_409(client):
    a = client.post("/api/v1/categories", json={"name": "reg_cat_a", "color": "#111111"}).json()
    b = client.post("/api/v1/categories", json={"name": "reg_cat_b", "color": "#222222"}).json()
    r = client.put(f"/api/v1/categories/{b['id']}", json={"name": "reg_cat_a", "color": "#222222"})
    assert r.status_code == 409


# ── Finding: ReDoS via arbitrary regex category rule ────────────────────────────

def test_redos_regex_rule_rejected(client):
    cat = client.post("/api/v1/categories", json={"name": "reg_redos", "color": "#333333"}).json()
    # Nested-quantifier pattern that hangs the categorizer must be rejected.
    r = client.post(f"/api/v1/categories/{cat['id']}/rules",
                    json={"pattern": "(a+)+$", "match_type": "regex", "priority": 10})
    assert r.status_code == 422


def test_invalid_match_type_rejected(client):
    cat = client.post("/api/v1/categories", json={"name": "reg_badtype", "color": "#333333"}).json()
    r = client.post(f"/api/v1/categories/{cat['id']}/rules",
                    json={"pattern": "example.com", "match_type": "bogus", "priority": 1})
    assert r.status_code == 422


def test_safe_regex_rule_accepted(client):
    cat = client.post("/api/v1/categories", json={"name": "reg_saferx", "color": "#333333"}).json()
    r = client.post(f"/api/v1/categories/{cat['id']}/rules",
                    json={"pattern": r"^intranet\.", "match_type": "regex", "priority": 5})
    assert r.status_code == 201


def test_is_safe_regex_unit():
    assert not is_safe_regex("(a+)+$")
    assert not is_safe_regex("(.*)+")
    assert not is_safe_regex("([a-z]+)*x")
    assert is_safe_regex(r"^spotify\.com")
    assert is_safe_regex("(ab){2,4}")  # bounded repetition of a simple group is fine


# ── Finding: category-breakdown shows two "uncategorized" entries ───────────────

def test_category_breakdown_merges_dangling_category(client):
    # FK enforcement is off in the test engine, so we can insert rows whose
    # category_id points at a now-deleted category (id 999999) to reproduce the
    # dangling-reference state a live proxy produces after a category delete.
    db = TestSessionLocal()
    marker = datetime(2030, 3, 3, 10, 0, 0)
    try:
        for _ in range(2):
            db.add(models.TrafficLog(timestamp=marker, src_ip="10.9.9.9", domain="a.example",
                                     protocol="https", category_id=None, time_classification="work"))
        for _ in range(3):
            db.add(models.TrafficLog(timestamp=marker, src_ip="10.9.9.9", domain="b.example",
                                     protocol="https", category_id=999999, time_classification="work"))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/reports/category-breakdown",
                   params={"from_dt": "2030-03-03T00:00:00", "to_dt": "2030-03-04T00:00:00"})
    assert r.status_code == 200
    uncat = [e for e in r.json() if e["category_name"] == "uncategorized"]
    assert len(uncat) == 1, f"expected one merged uncategorized entry, got {r.json()}"
    assert uncat[0]["count"] == 5


# ── Finding: DELETE category nulls referencing rows (passive_deletes) ───────────

def test_delete_category_nulls_referencing_rows(tmp_path):
    # Uses an isolated engine with foreign_keys=ON, matching the production API
    # engine (api/database.py). passive_deletes relies on the DB's ON DELETE
    # SET NULL, so the referencing row must be preserved with a cleared FK
    # rather than loaded and nulled row-by-row in Python.
    db_url = f"sqlite:///{tmp_path/'del.db'}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        cat = models.Category(name="reg_del", color="#444444")
        db.add(cat)
        db.flush()
        cid = cat.id
        db.add(models.TrafficLog(timestamp=datetime.utcnow(), src_ip="10.8.8.8",
                                 domain="c.example", protocol="https",
                                 category_id=cid, time_classification="work"))
        db.commit()
        # Mirror the API delete path (db.delete(obj); commit()).
        db.delete(db.get(models.Category, cid))
        db.commit()
        rows = db.query(models.TrafficLog).filter(models.TrafficLog.domain == "c.example").all()
        assert len(rows) == 1              # row preserved
        assert rows[0].category_id is None  # FK cleared by ON DELETE SET NULL
    finally:
        db.close()


# ── Finding: categorizer exact-rule priority inversion ─────────────────────────

def test_categorizer_exact_rule_highest_priority_wins(tmp_path):
    db_url = f"sqlite:///{tmp_path/'cat.db'}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        low = models.Category(name="low_cat", color="#000000")
        high = models.Category(name="high_cat", color="#ffffff")
        db.add_all([low, high])
        db.flush()
        # Same exact pattern, two priorities — the higher one must win.
        db.add(models.CategoryRule(category_id=low.id, pattern="x.example.com",
                                   match_type="exact", priority=5))
        db.add(models.CategoryRule(category_id=high.id, pattern="x.example.com",
                                   match_type="exact", priority=50))
        db.commit()
        result = Categorizer(db=db).categorize("x.example.com")
        assert result is not None and result["name"] == "high_cat"
    finally:
        db.close()


# ── Finding: standalone proxy launch never creates schema ──────────────────────

def test_writer_creates_schema_on_fresh_db(tmp_path):
    db_path = tmp_path / "fresh.db"
    db_url = f"sqlite:///{db_path}"
    DatabaseWriter(queue=Queue(), db_url=db_url, batch_size=10, flush_interval=0.1)
    check = create_engine(db_url)
    with check.connect() as conn:
        tables = {r[0] for r in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert "traffic_logs" in tables and "categories" in tables


# ── Finding: writer silently drops batches (count-exact) ───────────────────────

def test_writer_persists_every_valid_item(tmp_path):
    db_url = f"sqlite:///{tmp_path/'feed.db'}"
    q = Queue()
    w = DatabaseWriter(queue=q, db_url=db_url, batch_size=25, flush_interval=0.1)
    w.start()
    n = 60
    for i in range(n):
        q.put({"timestamp": datetime.utcnow(), "src_ip": "10.0.0.1",
               "domain": f"host{i}.example.com", "url": None, "method": "GET",
               "protocol": "https", "status_code": None, "bytes_sent": 1, "bytes_received": 0})
    # Wait for the queue to drain, then stop and join.
    deadline = _time.monotonic() + 10
    while not q.empty() and _time.monotonic() < deadline:
        _time.sleep(0.05)
    w.stop()
    w.join(timeout=10)
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        assert db.query(models.TrafficLog).count() == n
    finally:
        db.close()


# ── Finding: dangling category_id after delete (per-record fallback) ───────────

def test_writer_fallback_preserves_rows_with_dangling_fk(tmp_path):
    # With FK enforcement on (writer engine), a record referencing a deleted
    # category must be salvaged as uncategorized, not drop the whole batch.
    db_url = f"sqlite:///{tmp_path/'fallback.db'}"
    w = DatabaseWriter(queue=Queue(), db_url=db_url, batch_size=100, flush_interval=0.1)
    db = w._SessionFactory()
    try:
        good = models.TrafficLog(timestamp=datetime.utcnow(), src_ip="10.0.0.1",
                                 domain="good.example", protocol="https",
                                 category_id=None, time_classification="outside")
        dangling = models.TrafficLog(timestamp=datetime.utcnow(), src_ip="10.0.0.2",
                                     domain="bad.example", protocol="https",
                                     category_id=424242, time_classification="outside")
        w._commit_records(db, [good, dangling])
    finally:
        db.close()

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db2 = Session()
    try:
        rows = db2.query(models.TrafficLog).order_by(models.TrafficLog.domain).all()
        assert len(rows) == 2, "no valid row should be lost"
        by_domain = {r.domain: r for r in rows}
        assert by_domain["bad.example"].category_id is None  # dangling FK nulled
    finally:
        db2.close()
