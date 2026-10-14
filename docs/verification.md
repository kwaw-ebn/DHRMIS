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
