from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from api.database import get_db
from api import models, schemas

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _base_filter(q, from_dt, to_dt, employee_id, classification):
    if from_dt:
        q = q.filter(models.TrafficLog.timestamp >= from_dt)
    if to_dt:
        q = q.filter(models.TrafficLog.timestamp <= to_dt)
    if employee_id:
        q = q.filter(models.TrafficLog.employee_id == employee_id)
    if classification:
        q = q.filter(models.TrafficLog.time_classification == classification)
    return q


@router.get("/top-sites", response_model=List[schemas.TopSiteSchema])
def top_sites(
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    employee_id: Optional[int] = None,
    classification: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(
        models.TrafficLog.domain,
        models.Category.name.label("category_name"),
        models.Category.color.label("category_color"),
        func.count(models.TrafficLog.id).label("request_count"),
        func.sum(models.TrafficLog.bytes_received + models.TrafficLog.bytes_sent).label("bytes_total"),
    ).outerjoin(models.Category, models.TrafficLog.category_id == models.Category.id)

    q = _base_filter(q, from_dt, to_dt, employee_id, classification)
    rows = q.group_by(models.TrafficLog.domain).order_by(func.count(models.TrafficLog.id).desc()).limit(limit).all()

    return [
        schemas.TopSiteSchema(
            domain=r.domain,
            category_name=r.category_name,
            category_color=r.category_color,
            request_count=r.request_count,
            bytes_total=r.bytes_total or 0,
        )
        for r in rows
    ]


@router.get("/top-sites-by-employee")
def top_sites_by_employee(
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    classification: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    employees = db.query(models.Employee).all()
    result = []
    for emp in employees:
        q = db.query(
            models.TrafficLog.domain,
            func.count(models.TrafficLog.id).label("count"),
        ).filter(models.TrafficLog.employee_id == emp.id)
        q = _base_filter(q, from_dt, to_dt, None, classification)
        sites = q.group_by(models.TrafficLog.domain).order_by(func.count(models.TrafficLog.id).desc()).limit(limit).all()
        result.append({
            "employee": {"id": emp.id, "username": emp.username, "email": emp.email},
            "sites": [{"domain": s.domain, "count": s.count} for s in sites],
        })
    return result


@router.get("/timeline")
def timeline(
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    employee_id: Optional[int] = None,
    bucket: str = Query("hour", pattern="^(hour|day)$"),
    db: Session = Depends(get_db),
):
    if not from_dt:
        from_dt = datetime.utcnow() - timedelta(hours=24)
    if not to_dt:
        to_dt = datetime.utcnow()

    # Aggregate in SQL (GROUP BY a truncated timestamp) so we never load the
    # full result set into memory, and join names to avoid N+1 lazy loads.
    fmt = "%Y-%m-%dT%H:00:00" if bucket == "hour" else "%Y-%m-%dT00:00:00"
    bucket_col = func.strftime(fmt, models.TrafficLog.timestamp).label("bucket_start")

    q = (
        db.query(
            bucket_col,
            models.TrafficLog.employee_id,
            models.Employee.username.label("employee_name"),
            models.TrafficLog.domain,
            models.Category.name.label("category_name"),
            models.Category.color.label("category_color"),
            func.count(models.TrafficLog.id).label("count"),
        )
        .outerjoin(models.Employee, models.TrafficLog.employee_id == models.Employee.id)
        .outerjoin(models.Category, models.TrafficLog.category_id == models.Category.id)
        .filter(
            models.TrafficLog.timestamp >= from_dt,
            models.TrafficLog.timestamp <= to_dt,
        )
    )
    if employee_id:
        q = q.filter(models.TrafficLog.employee_id == employee_id)

    rows = (
        q.group_by(bucket_col, models.TrafficLog.employee_id, models.TrafficLog.domain)
        .order_by(bucket_col.asc())
        .all()
    )

    return [
        {
            "bucket_start": r.bucket_start,
            "employee_id": r.employee_id,
            "employee_name": r.employee_name,
            "domain": r.domain,
            "category_name": r.category_name,
            "category_color": r.category_color or "#6b7280",
            "count": r.count,
        }
        for r in rows
    ]


@router.get("/work-break-summary", response_model=List[schemas.WorkBreakSummarySchema])
def work_break_summary(
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(
        models.TrafficLog.employee_id,
        models.Employee.username,
        models.TrafficLog.time_classification,
        func.count(models.TrafficLog.id).label("count"),
        func.sum(models.TrafficLog.bytes_sent + models.TrafficLog.bytes_received).label("bytes"),
    ).outerjoin(models.Employee, models.TrafficLog.employee_id == models.Employee.id)

    q = _base_filter(q, from_dt, to_dt, employee_id, None)
    rows = q.group_by(models.TrafficLog.employee_id, models.TrafficLog.time_classification).all()

    # Pivot by employee
    pivot: dict = {}
    for r in rows:
        eid = r.employee_id
        if eid not in pivot:
            pivot[eid] = {
                "employee_id": eid,
                "employee_name": r.username,
                "work_requests": 0, "break_requests": 0, "outside_requests": 0,
                "work_bytes": 0, "break_bytes": 0, "outside_bytes": 0,
            }
        cls = r.time_classification
        pivot[eid][f"{cls}_requests"] = r.count
        pivot[eid][f"{cls}_bytes"] = r.bytes or 0

    return list(pivot.values())


@router.get("/category-breakdown", response_model=List[schemas.CategoryBreakdownSchema])
def category_breakdown(
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    employee_id: Optional[int] = None,
    classification: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(
        models.Category.name.label("category_name"),
        models.Category.color.label("category_color"),
        func.count(models.TrafficLog.id).label("count"),
        func.sum(models.TrafficLog.bytes_sent + models.TrafficLog.bytes_received).label("bytes"),
    ).outerjoin(models.Category, models.TrafficLog.category_id == models.Category.id)

    q = _base_filter(q, from_dt, to_dt, employee_id, classification)
    rows = q.group_by(models.TrafficLog.category_id).all()

    # Merge by display name so rows that resolve to the same label collapse into
    # one entry. In particular, a category_id that references a since-deleted
    # category has a NULL name and would otherwise show up as a second,
    # separate "uncategorized" bucket alongside the real category_id IS NULL one.
    merged: dict = {}
    for r in rows:
        name = r.category_name or "uncategorized"
        entry = merged.setdefault(
            name,
            {"category_name": name, "category_color": r.category_color or "#6b7280",
             "count": 0, "bytes": 0},
        )
        entry["count"] += r.count
        entry["bytes"] += r.bytes or 0

    total = sum(e["count"] for e in merged.values())
    return [
        schemas.CategoryBreakdownSchema(
            category_name=e["category_name"],
            category_color=e["category_color"],
            count=e["count"],
            bytes=e["bytes"],
            percentage=round((e["count"] / total * 100) if total else 0, 1),
        )
        for e in sorted(merged.values(), key=lambda x: x["count"], reverse=True)
    ]
