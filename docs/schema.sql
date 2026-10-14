BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> aade32d24ec0

CREATE TABLE organization_units (
    id VARCHAR(36) NOT NULL,
    name VARCHAR(180) NOT NULL,
    kind VARCHAR(30) NOT NULL,
    category VARCHAR(40),
    parent_id VARCHAR(36),
    active BOOLEAN NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(parent_id) REFERENCES organization_units (id),
    CONSTRAINT uq_unit_parent_name UNIQUE (parent_id, name)
);

CREATE TABLE system_settings (
    key VARCHAR(80) NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (key)
);

CREATE TABLE employees (
    id VARCHAR(36) NOT NULL,
    staff_id VARCHAR(40) NOT NULL,
    ghs_number VARCHAR(60),
    payroll_number VARCHAR(60),
    full_name VARCHAR(160) NOT NULL,
    preferred_name VARCHAR(100),
    date_of_birth DATE,
    gender VARCHAR(40),
    email VARCHAR(160),
    phone VARCHAR(30),
    address TEXT,
    emergency_contact VARCHAR(200),
    job_title VARCHAR(120) NOT NULL,
    cadre VARCHAR(100) NOT NULL,
    grade VARCHAR(80),
    rank VARCHAR(80),
    appointment_type VARCHAR(80),
    employment_date DATE,
    first_appointment_date DATE,
    posting_date DATE,
    status VARCHAR(40) NOT NULL,
    unit_id VARCHAR(36) NOT NULL,
    supervisor_id VARCHAR(36),
    qualification VARCHAR(180),
    registration_body VARCHAR(120),
    registration_number VARCHAR(100),
    licence_expiry DATE,
    specialty VARCHAR(100),
    verified BOOLEAN NOT NULL,
    archived BOOLEAN NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(supervisor_id) REFERENCES employees (id),
    FOREIGN KEY(unit_id) REFERENCES organization_units (id),
    UNIQUE (ghs_number),
    UNIQUE (payroll_number)
);

CREATE INDEX ix_employees_cadre ON employees (cadre);

CREATE INDEX ix_employees_full_name ON employees (full_name);

CREATE UNIQUE INDEX ix_employees_staff_id ON employees (staff_id);

CREATE INDEX ix_employees_status ON employees (status);

CREATE INDEX ix_employees_unit_id ON employees (unit_id);

CREATE TABLE staff_assignments (
    id VARCHAR(36) NOT NULL,
    employee_id VARCHAR(36) NOT NULL,
    unit_id VARCHAR(36) NOT NULL,
    effective_date DATE NOT NULL,
    end_date DATE,
    reason VARCHAR(250) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(employee_id) REFERENCES employees (id),
    FOREIGN KEY(unit_id) REFERENCES organization_units (id)
);

CREATE INDEX ix_staff_assignments_employee_id ON staff_assignments (employee_id);

CREATE TABLE users (
    id VARCHAR(36) NOT NULL,
    email VARCHAR(160) NOT NULL,
    name VARCHAR(160) NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(40) NOT NULL,
    unit_id VARCHAR(36),
    employee_id VARCHAR(36),
    active BOOLEAN NOT NULL,
    must_change_password BOOLEAN NOT NULL,
    totp_secret TEXT,
    mfa_enabled BOOLEAN NOT NULL,
    last_totp_step INTEGER NOT NULL,
    failed_attempts INTEGER NOT NULL,
    locked_until TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    FOREIGN KEY(employee_id) REFERENCES employees (id),
    FOREIGN KEY(unit_id) REFERENCES organization_units (id),
    UNIQUE (employee_id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE audit_logs (
    id VARCHAR(36) NOT NULL,
    actor_id VARCHAR(36),
    actor_name VARCHAR(160) NOT NULL,
    action VARCHAR(80) NOT NULL,
    entity_id VARCHAR(36),
    detail TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);

CREATE TABLE sessions (
    id VARCHAR(64) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    authenticated BOOLEAN NOT NULL,
    csrf_token VARCHAR(64) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_sessions_user_id ON sessions (user_id);

INSERT INTO alembic_version (version_num) VALUES ('aade32d24ec0') RETURNING alembic_version.version_num;

COMMIT;
