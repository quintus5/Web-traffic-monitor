"""
Classifies a UTC timestamp as 'work', 'break', or 'outside'
based on the active WorkSchedule stored in the DB.
"""
import json
import time as _time_mod
from datetime import datetime, time
from typing import Literal

import pytz


Classification = Literal["work", "break", "outside"]


class TimeClassifier:
    def __init__(self, db=None, ttl: int = 60):
        self._db = db
        self._ttl = ttl
        self._schedule = None
        self._loaded_at: float = 0.0

    def _load(self):
        if self._schedule is not None and (_time_mod.monotonic() - self._loaded_at) < self._ttl:
            return
        if self._db is None:
            return
        from api import models
        self._schedule = (
            self._db.query(models.WorkSchedule)
            .filter(models.WorkSchedule.active == True)
            .first()
        )
        self._loaded_at = _time_mod.monotonic()

    def classify(self, utc_dt: datetime) -> Classification:
        self._load()
        if self._schedule is None:
            return "outside"

        tz = pytz.timezone(self._schedule.timezone)
        local_dt = utc_dt.replace(tzinfo=pytz.utc).astimezone(tz)
        weekday = local_dt.isoweekday()  # 1=Mon, 7=Sun
        local_time = local_dt.time().replace(tzinfo=None)

        try:
            work_days = json.loads(self._schedule.work_days)
        except (ValueError, TypeError):
            work_days = [1, 2, 3, 4, 5]

        if weekday not in work_days:
            return "outside"

        work_start = self._schedule.work_start
        work_end = self._schedule.work_end

        if not (work_start <= local_time < work_end):
            return "outside"

        # Inside work hours — check breaks
        for brk in self._schedule.breaks:
            if brk.break_start <= local_time < brk.break_end:
                return "break"

        return "work"

    def invalidate(self):
        self._loaded_at = 0.0
