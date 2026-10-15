# Phase 3 — workforce management pilot

The live pilot starts with no demo staff. Institutional approval remains pending. No policy, grade, eligibility decision, retirement age or professional accreditation is inferred from Ghana Health Service practice.

## Daily workflows

| Module | Workflow | Authority and boundary |
|---|---|---|
| Attendance | Record → independently verify; reopen with reason → explicitly reconcile | Employees record only themselves. HR and heads record staff in scope. An officer cannot verify their own entry or correction. One record per staff/day. Future entries rejected. |
| Duty rosters | Draft → publish → cancel with reason | HR or scoped heads. Overlapping shifts rejected; shift length 0–24 hours with timezone required. Published shifts conflict with leave in either approval order; reconcile before approval. Employees see only their own published shifts. |
| Training & CPD | Completed learning → submit → HR verify/reject | Employees see own history. Provider, hours, credits and optional certificate reference. No future completion, accreditation assertion or assumed professional credit threshold. Certificates can be managed in private personnel documents. |
| Promotion | Evidence, configured target grade and policy reference → submit → explicitly selected final authority approve/reject | HR records; a separate HR-configured final officer records the decision. No automatic grade, payroll or eligibility change. |
| Retirement & exit | Authorized date, authority reference and checklist → submit → explicitly selected final authority approve/reject → HR checklist → complete | Date must arrive and all checklist items must be complete. No automatic staff-status change. A separate HR action on the staff profile is required after validation. |
| Retirement planning | HR administrator configures age, notice days and approved reference → HR/director forecast | No default rule. Birth-date-derived dates are indicative, including overdue records. Missing dates counted explicitly. Leap-day birthdays use 28 February in non-leap years; officers must validate exceptions and official dates. |
| Performance | HR opens period and assigns reviewer → reviewer writes and submits → separate HR releases or returns → employee acknowledges | HR and assigned scoped reviewer only before release. Even HR cannot read their own unreleased review. Employees cannot see other reviews. Appraisal periods cannot overlap. Notifications contain no assessment text. |
| Staffing establishments | HR proposal → separately selected final authority approves/rejects → gaps calculated from assigned staff | Configured cadre and authority reference required. Draft/future proposals do not generate official gaps. Rejected/draft proposals can be revised; approved rows are immutable in this pilot. Counts use the selected organizational subtree and exact cadre, excluding archived, retired, separated, transferred-out and deceased staff. Compare each establishment independently; do not sum overlapping hierarchy rows. No automatic recruitment or transfers. |

HR must explicitly select the final approval role (director or HR administrator) on each promotion, exit or staffing proposal and supply the verified authority reference. The choice is a workflow configuration, not a claim of institutional authority. There is no default approval role. The creator and the affected employee cannot approve their own case.

## Connectivity and concurrency

Forms remain in React memory while their tab is open. They are never written to browser local storage, IndexedDB or a service worker. Closing or refreshing loses unsaved forms. Reconnect and explicitly retry. There is no background sync or continuous tracking.

Attendance creation uses version 0. If another entry already exists, the API returns 409 without overwriting it. Refresh, open that entry, compare it and use **Reconcile entry** to send its current version. Verified entries must first be reopened by a separate officer with a reason. All workflow actions and edits use version checks; staff row locks serialize roster and leave decisions on PostgreSQL. No silent last-write-wins synchronization.

Attendance/roster queries are limited to 93 days and 1,000 rows; use narrower dates if necessary. Other workforce histories paginate 50 records per page. Appraisal text and decision notes must not be copied into public messages.

## Deployment and validation

Additive Alembic revision `23fd21cacf50` creates five tables; `9de5817b676b` adds the explicit staffing approval role. Existing personnel, account and Phase 2 tables are not rewritten or seeded. Docker startup applies migrations before serving the new code. Health reports version `0.3.0`.

Tests cover role and staff scope, hidden reviews and HR self-access, independent attendance verification including corrections, stale versions, roster overlaps and leave conflicts in both directions, CPD verification, manual promotion decisions, exit checklist gates, establishment approval/gaps, and no default retirement rule. Existing Phase 1–2 tests remain part of the regression suite.

The PostgreSQL SQL generated from this migration was applied transactionally through the Neon connector to the isolated `phase3-migration-test` branch. Its revision, five new tables, preserved administrator and zero employees were checked. Direct PostgreSQL connections from the execution host are unavailable; full ORM tests run against SQLite. Live startup and the health endpoint must be verified separately before reporting deployment success.
