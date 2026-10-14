# Operations, recovery and production approval

## Hosting

Render Docker web service and dedicated Neon PostgreSQL pilot in Frankfurt. The Render free service may sleep when idle; availability is not guaranteed for operations. Database records persist across container redeploys. Phase 2 files are stored in the private Neon personnel-documents bucket, never the ephemeral container filesystem. Back up object contents and metadata alongside PostgreSQL and test their joint restoration.

Secrets: pooled DATABASE_URL, direct DATABASE_URL_UNPOOLED, MFA_ENCRYPTION_KEY, ADMIN_EMAIL and initial ADMIN_PASSWORD. COOKIE_SECURE stays true for HTTPS. Bootstrap is once-only and never resets existing users. Save the MFA encryption key separately and do not rotate it without re-encrypting enrolled secrets. Initial ADMIN_PASSWORD can be removed after bootstrap. Check health, deploy status/logs, MFA, dashboard and a create/edit/export workflow after deployment. Never print credentials in logs.

Migrations run on startup for this single-instance pilot. Production release migrations must be serialized as separate jobs. Application connections have a bounded pool and pool_pre_ping. No background worker, automatic backup scheduler or SMS/email provider is provisioned. Phase 2 uses private object storage and refreshes in-app reminders on demand.

## MFA recovery

After identity verification, from a trusted environment with application configuration:

`python -m app.admin approved-user@example.com --reason "Identity verified under approved recovery procedure"`

This clears MFA enrollment and revokes sessions. Next privileged login requires enrollment again. It does not reset/disclose passwords. HR administrators can reset other accounts' passwords. For loss of the sole administrator password, use the trusted operator recovery command's optional `--reset-password` flag; it generates a temporary password, revokes sessions and records the action. No public unauthenticated recovery endpoint exists.

## Backup and restoration

Proposed targets requiring confirmation: daily encrypted backup, RPO 24 hours, RTO one working day. These are planning targets, not verified guarantees. Configure a real schedule and restore drill before production.

1. In a trusted shell: `pg_dump "$DATABASE_URL_UNPOOLED" --format=custom --file=staffhub.backup`.
2. Encrypt/store the archive privately outside the hosting account, with approved retention. Protect the MFA key separately.
3. Restore into an isolated database: `pg_restore --no-owner --dbname="$RESTORE_DATABASE_URL" staffhub.backup`.
4. Verify Alembic revision, counts, history, audit and MFA key. Revoke all restored sessions. Test employee/facility isolation before cutover.
5. Record timestamp, duration and authorized sign-off. Never test restoration into the active database.

Inspect Neon history retention before relying on branch restore; portable encrypted exports remain necessary.

## Infrastructure migration

Freeze writes, take a direct database backup and protect configuration. Restore to institution-approved PostgreSQL, deploy the same container with changed URLs, preserve the MFA key, revoke old sessions and run migrations/access tests. Verify counts/history before DNS cutover and revoke old credentials afterward. Prefer a clean production database rather than turning synthetic test identities into staff records. Separate the limited runtime database role from migration/schema ownership.

## Implemented controls and open production work

Implemented: Argon2, privileged TOTP, encrypted MFA secrets, secure sessions/CSRF/origin checks, lockout, expiry, role and subtree scoping, confidential-field filtering, minimal audit, atomic validation, uniqueness, stale-edit protection, HTTPS configuration, no public personnel endpoints and no geolocation tracking.

Open: formal institutional hosting/data authorization; independent security review; verified role/field matrix; privacy/retention/incident procedures; PostgreSQL RLS and restricted runtime role; edge rate limiting for arbitrary-email/IP attacks; CSP hardening to remove inline allowances; malware scanning and private-object backup/restore validation; automated encrypted backups with restore drills; monitoring/alerting; migration release process; accessibility/load tests; audit archival; verified hosting capacity/geography.

Audit is read-only through the API, not cryptographically immutable or protected from a database owner. The current connection role has owner privileges for startup migrations. The app uses API scopes rather than database RLS, supports one pilot district and is for synthetic evaluation. Real employee processing remains subject to institutional approval.
