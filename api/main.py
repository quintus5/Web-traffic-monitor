import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import secrets
import base64
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.database import init_db, SessionLocal, get_db
from api import models
from api.routers import traffic, reports, employees, schedule, categories, export
from config.settings import settings


@asynccontextmanager
async def lifespan(app):
    init_db()
    _seed_categories_if_empty()
    _ensure_default_schedule()
    yield


app = FastAPI(title="Web Traffic Monitor", version="1.0.0", lifespan=lifespan)


# ── Authentication (HTTP Basic) ───────────────────────────────────────────────
# Every route requires the admin login except the CA certificate download, which
# employees must be able to fetch without credentials to set up the proxy.
AUTH_EXEMPT_PATHS = {"/ca-cert.pem"}


@app.middleware("http")
async def basic_auth_middleware(request: Request, call_next):
    if not settings.AUTH_ENABLED or request.url.path in AUTH_EXEMPT_PATHS:
        return await call_next(request)

    header = request.headers.get("Authorization", "")
    if header.startswith("Basic "):
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
            username, _, password = decoded.partition(":")
            user_ok = secrets.compare_digest(username, settings.ADMIN_USERNAME)
            pass_ok = secrets.compare_digest(password, settings.ADMIN_PASSWORD)
            if user_ok and pass_ok:
                return await call_next(request)
        except Exception:
            pass

    return Response(
        status_code=401,
        content="Authentication required",
        headers={"WWW-Authenticate": 'Basic realm="Web Traffic Monitor"'},
    )


def _seed_categories_if_empty():
    import json
    db = SessionLocal()
    try:
        if db.query(models.Category).count() > 0:
            return
        json_path = os.path.join(os.path.dirname(__file__), "../config/categories.json")
        with open(json_path) as f:
            data = json.load(f)

        cat_map = {}
        for c in data.get("categories", []):
            cat = models.Category(name=c["name"], color=c["color"], description=c.get("description"))
            db.add(cat)
            db.flush()
            cat_map[c["name"]] = cat.id

        for rule in data.get("rules", []):
            cat_name = rule["category"]
            if cat_name in cat_map:
                db.add(models.CategoryRule(
                    category_id=cat_map[cat_name],
                    pattern=rule["pattern"],
                    match_type=rule.get("match_type", "suffix"),
                    priority=rule.get("priority", 0),
                ))
        db.commit()
    finally:
        db.close()


def _ensure_default_schedule():
    from datetime import time
    db = SessionLocal()
    try:
        if db.query(models.WorkSchedule).count() == 0:
            s = models.WorkSchedule(
                name="default",
                timezone=settings.DEFAULT_TIMEZONE,
                work_days="[1,2,3,4,5]",
                work_start=time(9, 0),
                work_end=time(18, 0),
                active=True,
            )
            s.breaks.append(models.ScheduleBreak(
                label="Lunch", break_start=time(12, 0), break_end=time(13, 0)
            ))
            db.add(s)
            db.commit()
    finally:
        db.close()


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(traffic.router)
app.include_router(reports.router)
app.include_router(employees.router)
app.include_router(schedule.router)
app.include_router(categories.router)
app.include_router(export.router)


# ── Health / Stats ────────────────────────────────────────────────────────────

@app.get("/api/v1/health")
def health(db: Session = Depends(get_db)):
    log_count = db.query(func.count(models.TrafficLog.id)).scalar() or 0
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    db_size_mb = round(os.path.getsize(db_path) / 1024 / 1024, 2) if os.path.exists(db_path) else 0.0
    return {"status": "ok", "db_size_mb": db_size_mb, "log_count": log_count}


@app.get("/api/v1/stats/live")
async def live_stats():
    """Server-Sent Events stream for live request count."""
    import asyncio
    from fastapi.responses import StreamingResponse

    async def event_stream():
        while True:
            db = SessionLocal()
            try:
                count = db.query(func.count(models.TrafficLog.id)).scalar() or 0
            finally:
                db.close()
            yield f"data: {count}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── CA Certificate download ───────────────────────────────────────────────────

@app.get("/ca-cert.pem")
def download_ca_cert():
    ca_dir = settings.MITMPROXY_CA_DIR
    cert_path = os.path.join(ca_dir, "mitmproxy-ca-cert.pem")
    if not os.path.exists(cert_path):
        # Try default mitmproxy location
        home_cert = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
        if os.path.exists(home_cert):
            cert_path = home_cert
        else:
            return JSONResponse({"error": "CA cert not found. Start the proxy first to generate it."}, status_code=404)
    return FileResponse(cert_path, media_type="application/x-pem-file", filename="mitmproxy-ca-cert.pem")


# ── Static files & SPA fallback ───────────────────────────────────────────────

frontend_dir = os.path.join(os.path.dirname(__file__), "../frontend")

app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.get("/{path:path}")
def spa_fallback(path: str):
    # Serve page fragments for the SPA router
    page_path = os.path.join(frontend_dir, "pages", f"{path}.html")
    if os.path.exists(page_path):
        return FileResponse(page_path)
    return FileResponse(os.path.join(frontend_dir, "index.html"))
