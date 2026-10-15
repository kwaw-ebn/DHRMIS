from datetime import date, datetime
from sqlalchemy import String, Date, DateTime, Integer, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uid, now

class WorkforceRecord(Base):
    __tablename__ = 'workforce_records'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey('employees.id'), index=True)
    title: Mapped[str] = mapped_column(String(180))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    data: Mapped[str] = mapped_column(Text, default='{}')
    status: Mapped[str] = mapped_column(String(30), default='draft', index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class WorkforceEvent(Base):
    __tablename__ = 'workforce_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    record_id: Mapped[str] = mapped_column(ForeignKey('workforce_records.id'), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(40))
    comment: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class DutyShift(Base):
    __tablename__ = 'duty_shifts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    employee_id: Mapped[str] = mapped_column(ForeignKey('employees.id'), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey('organization_units.id'), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duty: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default='draft')
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))

class Attendance(Base):
    __tablename__ = 'attendance_records'
    __table_args__ = (UniqueConstraint('employee_id', 'day', name='uq_attendance_staff_day'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    employee_id: Mapped[str] = mapped_column(ForeignKey('employees.id'), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    outcome: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(30), default='submitted')
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    verified_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class Establishment(Base):
    __tablename__ = 'staffing_establishments'
    __table_args__ = (UniqueConstraint('unit_id', 'cadre', name='uq_establishment_unit_cadre'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    unit_id: Mapped[str] = mapped_column(ForeignKey('organization_units.id'), index=True)
    cadre: Mapped[str] = mapped_column(String(100))
    positions: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str] = mapped_column(String(250))
    effective_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default='draft')
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    final_role: Mapped[str | None] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer, default=1)
