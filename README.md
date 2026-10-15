# GHS StaffHub — DHRMIS

A working Phase 1–3 pilot for the Agona East District Health Directorate, Ghana Health Service. Built with Next.js/TypeScript, FastAPI, SQLAlchemy and Alembic. PostgreSQL on Neon; a single Docker web service on Render. **Use synthetic information only until institutional authorization is complete.**

## Implemented MVP

- Invitation-only accounts; Argon2 password hashes; database-backed expiring sessions; HttpOnly/Secure/SameSite cookies; CSRF protection; login lockout.
- Mandatory authenticator MFA for privileged roles; encrypted secrets; prevention of code replay; operator recovery; forced temporary-password changes.
- Configurable organization → district → sub-district/facility → department hierarchy, with rename and guarded archive operations.
- Nine roles with API-enforced scopes. Employees see their own record; heads see their assigned subtree. Platform administrators have no personnel API access. Auditors have audit access only.
- Optional private passport photographs on staff registration and profiles, with JPEG/PNG validation, previews, HR replacement, metadata stripping and scoped viewing.
- Personnel files use the Staff ID as their permanent file number. Staff entry accepts an explicit ID; file views group scoped documents and HR history. Current configured grades: Senior, Principal, Deputy Chief and Chief.
- Staff registration, detailed profiles, validated editing with concurrent-update checks, review verification, safe archive and historical initial assignments.
- Search and pagination; cadre, unit and status filters; controlled vocabulary administration.
- UTF-8 CSV import with duplicate checks, row validation and all-or-nothing transactions. Safe, scoped CSV export. Limit: 500 rows / 2 MB per import.
- Database dashboards, distribution by cadre and unit, employment status counts and licence expiry alerts.
- Account creation, disabling, password reset and session revocation; audit logs for sensitive reads, writes, exports and authentication.
- Responsive interface, light/dark themes, loading/error/empty states, browser print stylesheet.

## Phase 2 daily administration

Leave policies, annual balances, holiday calendars, staged approvals, leave start/return/cancellation, internal transfer and posting history, receiving acknowledgement, private Neon document storage/versioning, administrative request assignment/responses, correspondence register, letter PDF export, workflow notifications and scoped on-demand reminders are implemented. See `docs/phase2-guide.md` for setup and boundaries.

## Phase 3 workforce management

Attendance with separate-officer verification and explicit conflict reconciliation; draft/published duty shifts with overlap and leave checks; completed training and CPD records; human promotion decisions; approved retirement/exit dates and checklists; configurable retirement planning with indicative forecasts; confidential reviewer assessments and HR release; approved staffing establishment gap comparisons. See `docs/phase3-guide.md`.

## Explicitly deferred

Persistent offline storage or background sync, geolocation/geofencing, automatic promotion or employment-status changes, configurable multi-stage promotion panels, external CPD accreditation, amendments to already approved establishment rows, cross-district movements, Excel analytics, SMS/email delivery and unattended scheduled reminders remain future work.

This is a pilot, not a production readiness claim. Independent security review and institutional approvals are necessary before real HR use. Application scopes are enforced in the API; database RLS is not implemented in this phase. One pilot district is supported. No public signup, public personnel data or public document storage. Private documents use an authenticated API and short-lived authorized download links.

## Local development

1. Python 3.12+, Node 22+. Copy `.env.example` to a private `.env`; fill values. Use a test PostgreSQL instance or `DATABASE_URL=sqlite:///./staffhub.db` for local tests. Generate a Fernet MFA key as described in `.env.example`.
2. From `backend`: `pip install -r requirements.txt`, export the environment values, `python -m alembic upgrade head`, `python -m app.bootstrap`.
3. From `frontend`: `npm ci && npm run build`. Copy `frontend/out` to `backend/static`.
4. From `backend`: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`. Set `COOKIE_SECURE=false` **only for local HTTP**. Open http://localhost:8000.

The Next.js UI is exported and served by FastAPI from the same origin. This keeps sessions simple and needs only one Render web service. There is no frontend database credential. For UI development, rebuild/copy exports or use a local same-origin reverse proxy; the Next dev server alone does not proxy API requests.

## Deployment

`render.yaml` defines the free Frankfurt Docker service and health endpoint. Set `DATABASE_URL` to Neon’s pooled URL, `DATABASE_URL_UNPOOLED` to its direct URL, `MFA_ENCRYPTION_KEY`, `ADMIN_EMAIL`, and a strong initial `ADMIN_PASSWORD`. The Docker entrypoint runs Alembic and a once-only bootstrap before Uvicorn. Bootstrap never resets an existing account or duplicates seed records.

Synthetic seeding defaults to **off**, including `render.yaml`. Explicitly setting `SEED_SYNTHETIC=true` in a separate test environment seeds 24 clearly synthetic people, demo facilities and pilot grades. The root district identity is Agona East. Real sub-district and facility names must be configured from the approved register. Disable synthetic seed before a separately approved clean production deployment.

API reference: `/api/docs`. Health: `/api/health`. Secret values belong in Render environment variables, never Git. Save the MFA encryption key separately in a protected credential store; rotating it without re-encryption breaks enrolled accounts.

For multi-instance production deployment, run migrations as a separate release job instead of concurrently on every service startup. Move to institution-approved infrastructure by changing standard PostgreSQL environment URLs and redeploying the container, then follow the migration and restore procedure.

## Verification

`cd backend && pip install pytest httpx && python -m pytest -q`

`python -m alembic upgrade head && python -m alembic check`

`cd frontend && npm ci && npm run build`

GitHub Actions runs backend tests, migration checks and the Next.js production build. See `docs/architecture.md`, `docs/implementation-plan.md`, `docs/user-guide.md`, and `docs/operations.md`.

HR automation (0.4.0): Today’s HR Tasks includes leave-ending/return reminders, file completeness, document/licence expiry, configured career/retirement reviews, pending actions and monthly report preparation/export. See [the HR automation guide](docs/hr-automation.md) for configuration, scope and in-app delivery behavior.

Paper duty rosters (0.4.2): upload private PDF/JPEG/PNG copies by workplace and period under Duty rosters. See [the paper roster guide](docs/paper-rosters.md).
