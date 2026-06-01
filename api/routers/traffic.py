from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from api.database import get_db
from api import models, schemas

router = APIRouter(prefix="/api/v1/traffic", tags=["traffic"])


@router.get("", response_model=schemas.PaginatedTrafficLogs)
def list_traffic(
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    employee_id: Optional[int] = None,
    domain: Optional[str] = None,
    category_id: Optional[int] = None,
    classification: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(models.TrafficLog).options(
        joinedload(models.TrafficLog.employee),
        joinedload(models.TrafficLog.category),
    )
    if from_dt:
        q = q.filter(models.TrafficLog.timestamp >= from_dt)
    if to_dt:
        q = q.filter(models.TrafficLog.timestamp <= to_dt)
    if employee_id:
        q = q.filter(models.TrafficLog.employee_id == employee_id)
    if domain:
        q = q.filter(models.TrafficLog.domain.ilike(f"%{domain}%"))
    if category_id:
        q = q.filter(models.TrafficLog.category_id == category_id)
    if classification:
        q = q.filter(models.TrafficLog.time_classification == classification)

    total = q.count()
    items = q.order_by(models.TrafficLog.timestamp.desc()).offset((page - 1) * limit).limit(limit).all()
    pages = max(1, (total + limit - 1) // limit)

    return schemas.PaginatedTrafficLogs(items=items, total=total, page=page, pages=pages)


@router.get("/{log_id}", response_model=schemas.TrafficLogSchema)
def get_traffic_log(log_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    log = db.query(models.TrafficLog).options(
        joinedload(models.TrafficLog.employee),
        joinedload(models.TrafficLog.category),
    ).filter(models.TrafficLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return log
