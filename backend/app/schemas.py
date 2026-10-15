from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, EmailStr, model_validator, field_validator
ROLES = ['platform_admin','director','hr_admin','hr_officer','subdistrict_head','facility_head','department_head','employee','auditor']
STATUSES = ['Active','On approved leave','On study leave','On secondment','Transferred out','Retired','Separated','Deceased']
class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
class MfaCode(BaseModel):
    code: str = Field(pattern=r'^\d{6}$')
class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)
class UnitInput(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    kind: Literal['organization','district','subdistrict','facility','department']
    parent_id: str | None = None
    category: Literal['DHD','Polyclinic','Health Centre','CHPS','Other'] | None = None
class EmployeeInput(BaseModel):
    staff_id: str | None = Field(default=None, min_length=1, max_length=40, pattern=r'^[A-Za-z0-9][A-Za-z0-9/_-]*$')
    @field_validator('staff_id',mode='before')
    @classmethod
    def normalize_staff_id(cls,value):
        return value.strip().upper() if isinstance(value,str) else value

    full_name: str = Field(min_length=2, max_length=160)
    preferred_name: str | None = Field(default=None,max_length=100)
    ghs_number: str | None = Field(default=None,max_length=60)
    payroll_number: str | None = Field(default=None,max_length=60)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None,max_length=40)
    email: EmailStr | None = None
    phone: str | None = Field(default=None,max_length=30)
    address: str | None = Field(default=None,max_length=1000)
    emergency_contact: str | None = Field(default=None,max_length=200)
    job_title: str = Field(min_length=2,max_length=120)
    cadre: str = Field(min_length=2,max_length=100)
    grade: str | None = Field(default=None,max_length=80)
    rank: str | None = Field(default=None,max_length=80)
    appointment_type: str | None = Field(default=None,max_length=80)
    employment_date: date | None = None
    first_appointment_date: date | None = None
    posting_date: date | None = None
    status: Literal['Active','On approved leave','On study leave','On secondment','Transferred out','Retired','Separated','Deceased'] = 'Active'
    unit_id: str
    supervisor_id: str | None = None
    qualification: str | None = Field(default=None,max_length=180)
    registration_body: str | None = Field(default=None,max_length=120)
    registration_number: str | None = Field(default=None,max_length=100)
    licence_expiry: date | None = None
    specialty: str | None = Field(default=None,max_length=100)
    verified: bool = False
    version: int | None = None
    @model_validator(mode='after')
    def valid_dates(self):
        if self.date_of_birth and self.date_of_birth >= date.today():
            raise ValueError('Date of birth must be in the past')
        if self.first_appointment_date and self.employment_date and self.first_appointment_date > self.employment_date:
            raise ValueError('First appointment cannot follow employment date')
        return self
class UserInput(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2,max_length=160)
    password: str = Field(min_length=12,max_length=128)
    role: str
    unit_id: str | None = None
    employee_id: str | None = None
class Vocabulary(BaseModel):
    cadres: list[str] = Field(min_length=1,max_length=100)
    grades: list[str] = Field(min_length=1,max_length=100)
