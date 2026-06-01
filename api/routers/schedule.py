from datetime import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api import models, schemas

router = APIRouter(prefix="/api/v1/schedule", tags=["schedule"])


@router.get("", response_model=schemas.WorkScheduleSchema)
def get_schedule(db: Session = Depends(get_db)):
    schedule = db.query(models.WorkSchedule).filter(models.WorkSchedule.active == True).first()
    if not schedule:
        # Auto-create default schedule
        schedule = models.WorkSchedule(
            name="default",
            timezone="UTC",
            work_days="[1,2,3,4,5]",
            work_start=time(9, 0),
            work_end=time(18, 0),
            active=True,
        )
        lunch = models.ScheduleBreak(label="Lunch", break_start=time(12, 0), break_end=time(13, 0))
        schedule.breaks.append(lunch)
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
    return schedule


@router.put("", response_model=schemas.WorkScheduleSchema)
def update_schedule(payload: schemas.WorkScheduleUpdate, db: Session = Depends(get_db)):
    schedule = db.query(models.WorkSchedule).filter(models.WorkSchedule.active == True).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="No active schedule found. GET first to create default.")

    if payload.name is not None:
        schedule.name = payload.name
    if payload.timezone is not None:
        schedule.timezone = payload.timezone
    if payload.work_days is not None:
        schedule.work_days = payload.work_days
    if payload.work_start is not None:
        schedule.work_start = payload.work_start
    if payload.work_end is not None:
        schedule.work_end = payload.work_end

    if payload.breaks is not None:
        # Replace all breaks
        for b in list(schedule.breaks):
            db.delete(b)
        for b in payload.breaks:
            schedule.breaks.append(models.ScheduleBreak(
                label=b.label,
                break_start=b.break_start,
                break_end=b.break_end,
            ))

    db.commit()
    db.refresh(schedule)
    return schedule
