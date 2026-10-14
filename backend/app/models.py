import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Date, DateTime, Boolean, Integer, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)
class Unit(Base):
    __tablename__ = 'organization_units'
    __table_args__ = (UniqueConstraint('parent_id', 'name', name='uq_unit_parent_name'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(180))
    kind: Mapped[str] = mapped_column(String(30))
    category: Mapped[str | None] = mapped_column(String(40))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('organization_units.id'))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
class Employee(Base):
    __tablename__ = 'employees'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    staff_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    ghs_number: Mapped[str | None] = mapped_column(String(60), unique=True)
    payroll_number: Mapped[str | None] = mapped_column(String(60), unique=True)
    full_name: Mapped[str] = mapped_column(String(160), index=True)
    preferred_name: Mapped[str | None] = mapped_column(String(100))
    date_of_birth: Mapped[Date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(Text)
    emergency_contact: Mapped[str | None] = mapped_column(String(200))
    job_title: Mapped[str] = mapped_column(String(120))
    cadre: Mapped[str] = mapped_column(String(100), index=True)
    grade: Mapped[str | None] = mapped_column(String(80))
    rank: Mapped[str | None] = mapped_column(String(80))
    appointment_type: Mapped[str | None] = mapped_column(String(80))
    employment_date: Mapped[Date | None] = mapped_column(Date)
    first_appointment_date: Mapped[Date | None] = mapped_column(Date)
    posting_date: Mapped[Date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default='Active', index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey('organization_units.id'), index=True)
    supervisor_id: Mapped[str | None] = mapped_column(ForeignKey('employees.id'))
    qualification: Mapped[str | None] = mapped_column(String(180))
    registration_body: Mapped[str | None] = mapped_column(String(120))
    registration_number: Mapped[str | None] = mapped_column(String(100))
    licence_expiry: Mapped[Date | None] = mapped_column(Date)
    specialty: Mapped[str | None] = mapped_column(String(100))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
class Assignment(Base):
    __tablename__ = 'staff_assignments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    employee_id: Mapped[str] = mapped_column(ForeignKey('employees.id'), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey('organization_units.id'))
    effective_date: Mapped[Date] = mapped_column(Date)
    end_date: Mapped[Date | None] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(250))
class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(40))
    unit_id: Mapped[str | None] = mapped_column(ForeignKey('organization_units.id'))
    employee_id: Mapped[str | None] = mapped_column(ForeignKey('employees.id'), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    totp_secret: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_totp_step: Mapped[int] = mapped_column(Integer, default=-1)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
class Session(Base):
    __tablename__ = 'sessions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    authenticated: Mapped[bool] = mapped_column(Boolean, default=False)
    csrf_token: Mapped[str] = mapped_column(String(64))
class Audit(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    actor_name: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    detail: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
class Setting(Base):
    __tablename__ = 'system_settings'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
