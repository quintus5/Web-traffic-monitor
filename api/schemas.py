from datetime import datetime, time
from typing import Optional, List
from pydantic import BaseModel


# ── Employee ──────────────────────────────────────────────────────────────────

class EmployeeIPBase(BaseModel):
    ip_address: str
    label: Optional[str] = None
    active: bool = True


class EmployeeIPCreate(EmployeeIPBase):
    pass


class EmployeeIPSchema(EmployeeIPBase):
    id: int
    employee_id: int

    model_config = {"from_attributes": True}


class EmployeeBase(BaseModel):
    username: str
    email: Optional[str] = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None


class EmployeeSchema(EmployeeBase):
    id: int
    created_at: datetime
    ips: List[EmployeeIPSchema] = []

    model_config = {"from_attributes": True}


# ── Category ─────────────────────────────────────────────────────────────────

class CategoryRuleBase(BaseModel):
    pattern: str
    match_type: str = "suffix"
    priority: int = 0


class CategoryRuleCreate(CategoryRuleBase):
    pass


class CategoryRuleSchema(CategoryRuleBase):
    id: int
    category_id: int

    model_config = {"from_attributes": True}


class CategoryBase(BaseModel):
    name: str
    color: str = "#6b7280"
    description: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class CategorySchema(CategoryBase):
    id: int
    rules: List[CategoryRuleSchema] = []

    model_config = {"from_attributes": True}


# ── Work Schedule ─────────────────────────────────────────────────────────────

class ScheduleBreakBase(BaseModel):
    label: str = "Break"
    break_start: time
    break_end: time


class ScheduleBreakCreate(ScheduleBreakBase):
    pass


class ScheduleBreakSchema(ScheduleBreakBase):
    id: int
    schedule_id: int

    model_config = {"from_attributes": True}


class WorkScheduleBase(BaseModel):
    name: str = "default"
    timezone: str = "UTC"
    work_days: str = "[1,2,3,4,5]"
    work_start: time
    work_end: time


class WorkScheduleCreate(WorkScheduleBase):
    breaks: List[ScheduleBreakCreate] = []


class WorkScheduleUpdate(BaseModel):
    name: Optional[str] = None
    timezone: Optional[str] = None
    work_days: Optional[str] = None
    work_start: Optional[time] = None
    work_end: Optional[time] = None
    breaks: Optional[List[ScheduleBreakCreate]] = None


class WorkScheduleSchema(WorkScheduleBase):
    id: int
    active: bool
    breaks: List[ScheduleBreakSchema] = []

    model_config = {"from_attributes": True}


# ── Traffic Log ───────────────────────────────────────────────────────────────

class TrafficLogSchema(BaseModel):
    id: int
    timestamp: datetime
    employee_id: Optional[int]
    src_ip: str
    domain: str
    url: Optional[str]
    method: Optional[str]
    protocol: str
    status_code: Optional[int]
    bytes_sent: int
    bytes_received: int
    category_id: Optional[int]
    time_classification: str
    employee: Optional[EmployeeSchema] = None
    category: Optional[CategorySchema] = None

    model_config = {"from_attributes": True}


class PaginatedTrafficLogs(BaseModel):
    items: List[TrafficLogSchema]
    total: int
    page: int
    pages: int


# ── Reports ───────────────────────────────────────────────────────────────────

class TopSiteSchema(BaseModel):
    domain: str
    category_name: Optional[str]
    category_color: Optional[str]
    request_count: int
    bytes_total: int


class WorkBreakSummarySchema(BaseModel):
    employee_id: Optional[int]
    employee_name: Optional[str]
    work_requests: int
    break_requests: int
    outside_requests: int
    work_bytes: int
    break_bytes: int
    outside_bytes: int


class CategoryBreakdownSchema(BaseModel):
    category_name: str
    category_color: str
    count: int
    bytes: int
    percentage: float


class TimelineBucketSchema(BaseModel):
    bucket_start: datetime
    employee_id: Optional[int]
    employee_name: Optional[str]
    domain: str
    category_name: Optional[str]
    category_color: Optional[str]
    count: int


# ── Health ────────────────────────────────────────────────────────────────────

class HealthSchema(BaseModel):
    status: str
    db_size_mb: float
    log_count: int
