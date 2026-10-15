# Phase 4 — analytics, reporting and controlled expansion

Status: implementation prepared; application code is not changed by this document. The coding environment was unavailable on 15 October 2026, so no Phase 4 code, builds or migrations have been executed. The last verified release is Phase 3, version 0.3.0, Alembic revision 9de5817b676b. Synthetic seeding must remain disabled.

## Delivery sequence

### 4A. Scoped analytics and report exports

Implement a dedicated FastAPI reporting router and a Reports screen backed by current database data. Share filters and query builders between charts, PDF and Excel so totals reconcile. Do not duplicate authorization rules or allow browser-provided unit IDs to expand scope.

| Report | Data and filter requirements | Intended access |
|---|---|---|
| Nominal roll | Staff identifiers, name, cadre, grade, current unit and status; unit subtree, cadre and status filters | HR; scoped heads with the existing permitted field set |
| Staff distribution | Counts by facility, sub-district, department, cadre and grade; exclude archived records | Authorized district and scoped managers |
| Leave utilization | Reporting period, policy, requested/reserved/approved/completed days; distinguish requests from actual recorded leave | HR and scoped managers; employees retain their personal leave view |
| Attendance summary | Reporting period; submitted versus independently verified outcomes; roster counts shown separately | HR and scoped managers |
| Posting and transfers | Effective dates, originating/receiving unit, approval status and assumption-of-duty acknowledgement | Existing movement scopes |
| Training and CPD | Reporting period, provider, recorded hours/credits, verification status; no accreditation claim | Existing training scopes |
| Promotion tracking | Target grade, evidence reference, status, authorized role and recorded decision | Existing promotion scopes; omit evidence narrative from general exports |
| Retirement planning | Explicit configured rule, indicative date, missing birth-date counts and officer review flag | HR and director only |
| Licence expiry | Configurable horizon and expired/due/unknown counts | Existing personnel scopes |
| Staffing gaps | Approved effective establishment, filled/vacant/surplus counts; avoid summing overlapping hierarchy rows | HR, director and authorized scoped managers |
| Monthly HR activity | Period totals for requests, leaves, movements, training and unresolved deadlines | HR and authorized management, with aggregate output |

Do not create a general appraisal report or export confidential assessment text. Any later appraisal report needs its own explicit field permissions. Technical platform administrators and auditors must not gain report access to personnel information.

Proposed routes: GET /api/reports/catalog, GET /api/reports/summary, GET /api/reports/{report_key}, and POST /api/reports/{report_key}/exports. Validate report keys against a fixed registry. Apply scope before filtering, grouping, counting or exporting. Use explicit date semantics for each report and label unknown/missing data instead of inventing values.

Start with synchronous bounded exports. Add openpyxl for genuine .xlsx files and reuse ReportLab for PDF. Excel cells containing user-controlled text must be written as literal strings rather than formulas; apply formula protection to CSV. Use safe filenames, row limits, no-store response headers, audit entries and explicit truncated-result messages. Avoid storing export contents in logs or public object storage.

PDFs must identify the district, report title, applied filters, reporting period, generation time, page numbers and pilot status. Empty data must produce a readable empty report, not a failed download. Charts must have a tabular equivalent and must not imply forecasting confidence from an empty pilot database.

Acceptance: API role/scope tests, direct unauthorized-unit attempts, aggregate-versus-export reconciliation, verified/unverified attendance separation, future/draft staffing exclusion, date boundaries, spreadsheet formula-injection tests, .xlsx parsing and PDF rendering checks, followed by the full regression suite and frontend production build.

### 4B. Durable report jobs and reminders

Add persisted job definitions, runs and delivery attempts only after 4A passes. A worker must claim work transactionally with leases, bounded retries, exponential backoff and an idempotency key. Test duplicate claims, process termination and retry after partial failure. Store timestamps in UTC and preserve the user's requested display timezone.

Scheduled report jobs must preserve both tenant and requesting-user scope; revalidate current permissions at execution and download time. Disabling an account must prevent its jobs from exposing data. Keep generated reports private, record retention/expiry, and deliver only generic in-app notices with authorized download access. Do not attach confidential HR reports to ordinary email or SMS.

Use a separately configured Render worker/cron service only after its plan, cost and schedule have been established. Do not silently create a paid service or simulate scheduled execution with browser polling. External email, SMS, payroll or government integrations remain disabled until their provider, credentials, data contract and authorization are supplied.

### 4C. Tenant keys and database role separation

Design an additive migration that introduces organization/district tenant keys on every tenant-owned entity, including accounts, employee records, units, sessions, workflows, documents, notifications, workforce records and jobs. Backfill the existing pilot into its one known district. Validate missing keys and inconsistent cross-tenant references before enforcing NOT NULL and composite constraints. Do not onboard a second district until this is tested.

Split the DDL/migration owner from the application runtime role. The runtime role must not own tables or possess SUPERUSER/BYPASSRLS. Keep migration credentials out of the application process after a separate migration job has been established. Review worker, export and maintenance permissions independently.

Implement PostgreSQL row-level policies with transaction-local tenant/user context and default denial when context is absent. Do not treat a browser-supplied tenant ID as authentication. Scope resolution must derive from authenticated membership. Test using the actual restricted runtime role, not the migration owner, on an isolated Neon branch. Retain application-level role, field and subtree checks: tenant RLS alone does not protect appraisals or establish professional access rights.

Acceptance: cross-tenant reads/writes/exports/foreign-key attempts fail; owner/runtime role separation is confirmed; missing context fails closed; pool reuse does not leak prior context; technical and auditor roles retain their existing restrictions; live-pilot backfill preserves the administrator and existing records.

### 4D. Operational evidence and rollout

Document agreed recovery objectives, retention and incident owners. Verify the available backup/PITR configuration rather than assuming that a provider name guarantees a recoverable backup. Perform and time an isolated restore drill with integrity checks and record the evidence. Test representative report sizes, connection limits and concurrent job load without adding synthetic staff to the live pilot.

Independent security testing and institutional approval must be recorded as external milestones; passing internal tests is not a substitute. No real personnel data, integration or multi-district rollout is authorized by this plan alone.

## Implementation and release gates

1. Restore a working coding environment and synchronize the latest main branch.
2. Implement 4A on a feature branch with authorization tests and real generated-file checks.
3. Run the full API suite, frontend build, migration check and dependency audit.
4. Test any additive migration on an isolated Neon branch; preserve existing accounts and the no-demo-data state.
5. Publish the tested pilot increment, verify the exact deployed commit, health version, schema and recent logs, and describe which Phase 4 substage is delivered.
6. Implement 4B and 4C as separate reviewed increments. Keep unavailable integrations disabled and report external milestones honestly.

Do not label the entire phase complete when only report exports or dashboards have shipped. Do not make irreversible changes to the live schema or change runtime database roles without the branch tests and recovery path being concrete and reviewable.
