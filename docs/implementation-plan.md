# Requirements, phase plan and policy confirmations

## Phase 1 — implemented foundation

| Module | Delivered | Validation |
|---|---|---|
| Authentication | Invited login, Argon2, TOTP, expiry, lockout, CSRF, password changes | MFA/replay, lockout, expiry and password gate tests |
| Authorization | Nine roles, unit subtree scopes, confidential field filtering | Employee isolation, facility and technical/auditor restrictions |
| Organization | Hierarchy registration, rename, guarded archive | Hierarchy/in-use checks |
| Personnel | Register, view, edit, verify, archive, unique identifiers | CRUD, duplicates and concurrent edit tests |
| CSV | Atomic import, duplicate detection, safe scoped export | Rollback and formula protection tests |
| Dashboard | Database counts, unit/cadre distribution, verification and licence alerts | Integration smoke check |
| Accounts/audit | Invitation, disable, reset, session revocation, restricted audit | Account recovery and audit tests |

## Phase 2 — daily administration

Add institution-approved versioned leave policies, holiday calendars, requests/balances and recommendation/final approval state machines. Add posting/transfer approvals with effective-date history and assumption-of-duty acknowledgement. Build private document storage, versions, short-lived downloads, correspondence, editable letter templates, administrative requests and notification delivery records. Test authority delegation and duplicate approval prevention.

## Phase 3 — workforce management (implemented pilot)

Implemented manual attendance with independent verification, in-memory form retry and version conflicts; published rosters with overlapping shift and approved leave checks; completed training/CPD; promotion tracking with director decisions; HR-configured retirement planning, indicative dates and exit checklists; assigned-reviewer appraisals released by a separate HR officer; and director-approved staffing establishments. Human officers retain employment and eligibility decisions. No persistent confidential browser storage or geolocation. See `phase3-guide.md` for scope and validation.

## Phase 4 — analytics and expansion

Add generated PDF/Excel reports, reliable scheduled jobs and approved integrations. Introduce organization/district tenant keys, separate migration/runtime database roles and PostgreSQL RLS. Complete external security testing, monitored encrypted backups, restore drills, performance tests and institution-approved rollout.

## Details requiring institutional confirmation

1. Approved sub-district/facility/department register and reporting relationships.
2. Official identifiers, required profile fields, cadre/grade vocabulary and duplicate adjudication.
3. Hosting, geography, data handling and operational authorization before real records.
4. Named role owners, allowed fields and approval delegation.
5. Leave entitlements, holidays, carry-forward and approval routes.
6. Posting authority, effective-date rules, concurrent assignments and assumption of duty.
7. Promotion administration, licence review and retirement exceptions.
8. Document retention, legal holds, appraisal privacy and correction requests.
9. Recovery targets, retention, incident owners, availability and migration approval.
10. Notification providers, safe templates and allowed integrations.

No salary, leave entitlement, retirement age or promotion threshold is assumed. Demo staff and units have been removed from the live pilot. Automatic synthetic seeding is disabled. API documentation is generated at `/api/docs`.
