BEGIN;

-- Running upgrade aade32d24ec0 -> a852d77d150b

CREATE TABLE leave_policies (
    id VARCHAR(36) NOT NULL,
    name VARCHAR(120) NOT NULL,
    reference VARCHAR(250) NOT NULL,
    requires_balance BOOLEAN NOT NULL,
    count_basis VARCHAR(20) NOT NULL,
    working_days TEXT NOT NULL,
    final_role VARCHAR(40) NOT NULL,
    active BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (name)
);

CREATE TABLE public_holidays (
    id VARCHAR(36) NOT NULL,
    day DATE NOT NULL,
    name VARCHAR(120) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (day)
);

CREATE TABLE leave_balances (
    id VARCHAR(36) NOT NULL,
    employee_id VARCHAR(36) NOT NULL,
    policy_id VARCHAR(36) NOT NULL,
    year INTEGER NOT NULL,
    granted INTEGER NOT NULL,
    note VARCHAR(500) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(employee_id) REFERENCES employees (id),
    FOREIGN KEY(policy_id) REFERENCES leave_policies (id),
    CONSTRAINT uq_leave_balance UNIQUE (employee_id, policy_id, year)
);

CREATE INDEX ix_leave_balances_employee_id ON leave_balances (employee_id);

CREATE TABLE administrative_cases (
    id VARCHAR(36) NOT NULL,
    reference VARCHAR(60) NOT NULL,
    kind VARCHAR(30) NOT NULL,
    title VARCHAR(180) NOT NULL,
    body TEXT NOT NULL,
    employee_id VARCHAR(36),
    created_by VARCHAR(36) NOT NULL,
    assigned_to VARCHAR(36),
    policy_id VARCHAR(36),
    source_unit_id VARCHAR(36),
    target_unit_id VARCHAR(36),
    start_date DATE,
    end_date DATE,
    due_date DATE,
    days INTEGER,
    data TEXT NOT NULL,
    status VARCHAR(40) NOT NULL,
    final_role VARCHAR(40),
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(assigned_to) REFERENCES users (id),
    FOREIGN KEY(created_by) REFERENCES users (id),
    FOREIGN KEY(employee_id) REFERENCES employees (id),
    FOREIGN KEY(policy_id) REFERENCES leave_policies (id),
    FOREIGN KEY(source_unit_id) REFERENCES organization_units (id),
    FOREIGN KEY(target_unit_id) REFERENCES organization_units (id)
);

CREATE INDEX ix_administrative_cases_employee_id ON administrative_cases (employee_id);

CREATE INDEX ix_administrative_cases_kind ON administrative_cases (kind);

CREATE UNIQUE INDEX ix_administrative_cases_reference ON administrative_cases (reference);

CREATE INDEX ix_administrative_cases_status ON administrative_cases (status);

CREATE TABLE employee_documents (
    id VARCHAR(36) NOT NULL,
    employee_id VARCHAR(36) NOT NULL,
    title VARCHAR(180) NOT NULL,
    category VARCHAR(60) NOT NULL,
    employee_visible BOOLEAN NOT NULL,
    created_by VARCHAR(36) NOT NULL,
    archived BOOLEAN NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(created_by) REFERENCES users (id),
    FOREIGN KEY(employee_id) REFERENCES employees (id)
);

CREATE INDEX ix_employee_documents_employee_id ON employee_documents (employee_id);

CREATE TABLE document_versions (
    id VARCHAR(36) NOT NULL,
    document_id VARCHAR(36) NOT NULL,
    number INTEGER NOT NULL,
    object_key VARCHAR(500) NOT NULL,
    filename VARCHAR(180) NOT NULL,
    content_type VARCHAR(80) NOT NULL,
    size INTEGER NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    uploaded_by VARCHAR(36) NOT NULL,
    verified BOOLEAN NOT NULL,
    expiry_date DATE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(document_id) REFERENCES employee_documents (id),
    FOREIGN KEY(uploaded_by) REFERENCES users (id),
    CONSTRAINT uq_document_version UNIQUE (document_id, number),
    UNIQUE (object_key)
);

CREATE INDEX ix_document_versions_document_id ON document_versions (document_id);

CREATE TABLE notifications (
    id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    case_id VARCHAR(36),
    title VARCHAR(180) NOT NULL,
    read BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(case_id) REFERENCES administrative_cases (id),
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE TABLE workflow_approvals (
    id VARCHAR(36) NOT NULL,
    case_id VARCHAR(36) NOT NULL,
    actor_id VARCHAR(36) NOT NULL,
    action VARCHAR(50) NOT NULL,
    comment TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(actor_id) REFERENCES users (id),
    FOREIGN KEY(case_id) REFERENCES administrative_cases (id)
);

CREATE INDEX ix_workflow_approvals_case_id ON workflow_approvals (case_id);

UPDATE alembic_version SET version_num='a852d77d150b' WHERE alembic_version.version_num = 'aade32d24ec0';

-- Running upgrade a852d77d150b -> a6547d792a83

ALTER TABLE notifications ADD COLUMN document_id VARCHAR(36);

ALTER TABLE notifications ADD COLUMN event_key VARCHAR(300);

ALTER TABLE notifications ADD CONSTRAINT uq_notification_event_key UNIQUE (event_key);

ALTER TABLE notifications ADD CONSTRAINT fk_notification_document FOREIGN KEY(document_id) REFERENCES employee_documents (id);

UPDATE alembic_version SET version_num='a6547d792a83' WHERE alembic_version.version_num = 'a852d77d150b';

COMMIT;
