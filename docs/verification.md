# Pilot verification — 14 October 2026

- 11 critical backend tests passed: employee isolation, facility scope and field masking, platform/auditor restrictions, staff CRUD and duplicate identifiers, stale edits, transfer guard, atomic CSV validation, formula-safe exports, CSRF/origin checks, expiry, MFA/replay, lockout, invitations/disable/reset, temporary-password gate, hierarchy/vocabulary/audit.
- Alembic initial upgrade and model drift check passed on local SQLite.
- PostgreSQL offline migration SQL generated from the committed Alembic revision.
- Next.js 16.4.1 production export and TypeScript validation passed.
- npm production dependency audit: zero vulnerabilities at verification time.
- Python requirements audit: no known vulnerabilities at verification time, after upgrading multipart and cryptography dependencies.
- Integrated TestClient smoke passed with the exported interface mounted: root/health, first administrator login/MFA/password change, 24 seeded synthetic staff, dashboard, directory, audit, CSV export, logout and denied access after logout.
- Dedicated Neon database provisioned and read-only connectivity checked through the connected Neon tool. Local direct Neon connections are blocked by this environment's network restrictions; live PostgreSQL migration/startup must be verified during Render deployment.
- Chromium download failed in the environment. Interactive browser, mobile visual and accessibility QA are not claimed as completed.
- Render deployment and live service verification are pending target workspace confirmation. No live URL is claimed before that step.

Tests do not establish production certification. See the explicitly open operational and institutional requirements in operations.md.

## Phase 2 validation

25 critical API tests pass, including approval separation, cross-year leave, cancellation, overlapping leave, balances, transfer scope/effective-date/history, private document versions, reminders and correspondence. The frontend production build passes. Both additive PostgreSQL migrations succeeded on the isolated phase2-migration-test Neon branch, preserving 24 employees and the existing account. A fresh local migration and Alembic model drift check also pass. Phase 2 deployment is tracked separately in the live Render service.

Private storage integration passed on the isolated branch: a generated synthetic PDF uploaded via a signed PUT, downloaded with identical bytes via a signed GET, and denied when requested without a signature. Python and npm dependency scans report no known vulnerabilities at verification time.
