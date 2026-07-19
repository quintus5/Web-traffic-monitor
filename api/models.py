from datetime import datetime, time
from sqlalchemy import (
    Column, Integer, String, DateTime, Time, Boolean,
    ForeignKey, Index, Text
)
from sqlalchemy.orm import relationship
from api.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    ips = relationship("EmployeeIP", back_populates="employee", cascade="all, delete-orphan")
    # passive_deletes: let SQLite apply ON DELETE SET NULL instead of loading
    # every referencing row into memory (a delete on a large table would
    # otherwise take minutes and balloon RSS to gigabytes).
    traffic_logs = relationship("TrafficLog", back_populates="employee", passive_deletes=True)


class EmployeeIP(Base):
    __tablename__ = "employee_ips"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    ip_address = Column(String(45), nullable=False, index=True)
    label = Column(String(100), nullable=True)
    active = Column(Boolean, default=True)

    employee = relationship("Employee", back_populates="ips")

    __table_args__ = (
        Index("ix_employee_ips_ip_active", "ip_address", "active"),
    )


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    color = Column(String(7), default="#6b7280")
    description = Column(String(255), nullable=True)

    rules = relationship("CategoryRule", back_populates="category", cascade="all, delete-orphan")
    # passive_deletes: rely on the DB's ON DELETE SET NULL (see Employee above).
    traffic_logs = relationship("TrafficLog", back_populates="category", passive_deletes=True)


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    pattern = Column(String(255), nullable=False)
    match_type = Column(String(20), nullable=False, default="suffix")  # exact | suffix | regex
    priority = Column(Integer, default=0)

    category = relationship("Category", back_populates="rules")


class WorkSchedule(Base):
    __tablename__ = "work_schedules"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), default="default")
    timezone = Column(String(100), default="UTC")
    work_days = Column(String(20), default="[1,2,3,4,5]")  # JSON: 1=Mon, 7=Sun
    work_start = Column(Time, default=time(9, 0))
    work_end = Column(Time, default=time(18, 0))
    active = Column(Boolean, default=True)

    breaks = relationship("ScheduleBreak", back_populates="schedule", cascade="all, delete-orphan")


class ScheduleBreak(Base):
    __tablename__ = "schedule_breaks"

    id = Column(Integer, primary_key=True)
    schedule_id = Column(Integer, ForeignKey("work_schedules.id", ondelete="CASCADE"), nullable=False)
    label = Column(String(100), default="Break")
    break_start = Column(Time, nullable=False)
    break_end = Column(Time, nullable=False)

    schedule = relationship("WorkSchedule", back_populates="breaks")


class TrafficLog(Base):
    __tablename__ = "traffic_logs"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    src_ip = Column(String(45), nullable=False, index=True)
    domain = Column(String(255), nullable=False, index=True)
    url = Column(String(2048), nullable=True)
    method = Column(String(10), nullable=True)
    protocol = Column(String(10), nullable=False, default="https")
    status_code = Column(Integer, nullable=True)
    bytes_sent = Column(Integer, default=0)
    bytes_received = Column(Integer, default=0)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    time_classification = Column(String(10), nullable=False, default="outside")  # work | break | outside

    employee = relationship("Employee", back_populates="traffic_logs")
    category = relationship("Category", back_populates="traffic_logs")

    __table_args__ = (
        Index("ix_traffic_employee_timestamp", "employee_id", "timestamp"),
        Index("ix_traffic_domain_timestamp", "domain", "timestamp"),
        Index("ix_traffic_classification_timestamp", "time_classification", "timestamp"),
    )
