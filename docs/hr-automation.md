# HR tasks and reminders — 0.4.0

Today’s HR Tasks is the default personnel workspace. It recalculates reminders from authorized live records whenever opened and refreshes every 60 seconds while open. No worker, paid messaging service, browser storage of staff data, or new schema is needed. These are in-app reminders: they do not send email, SMS or WhatsApp while the app is closed.

## Leave and return to duty

Approved leave near its end, expected return today, overdue returns and reported returns awaiting confirmation appear for the staff member, scoped supervisor and HR under existing access rules. The leave detail displays the expected return date. The notification centre creates deduplicated leave-ending/return notices when opened; the task dashboard is the source of current outstanding work, while notifications retain their history.

Expected return is the first working day after the approved leave end, excluding configured public holidays. Weekdays come from the leave policy; when it has none, HR’s configurable fallback workweek is used (initially Monday–Friday). The policy workweek should reflect the applicable staff schedule. The dashboard warns when the holiday calendar is empty. Approved contiguous leave moves the expected return forward; pending extensions do not. Dates are recalculated when calendars or approved records change. Original charged leave days remain unchanged.

Staff or HR can report return once the approved leave has reached its start date, including an approved case whose commencement was not recorded. The system does not manufacture a commencement event. Supervisor/HR confirmation is independent of the submitter/staff member and is audited. Return reporting and confirmation dates are recorded. No reminder automatically confirms return, changes employment status, alleges unauthorized absence or overrides an approved extension. Existing balance, overlap, roster conflict, recommendation and final approval checks remain in force.

## HR configuration

- **Reminder rules** (HR administrator): leave notice lead time (initially 3 days before end), document/licence lead time (90 days), career-review lead time (30 days), and pending-action escalation age (7 days). These initial notification settings are editable, not statutory eligibility rules.
- Configure completeness fields, passport-photo checks and universally required document categories. Initially the checks flag missing birth date, gender, phone, emergency contact, grade, employment date and photo; no document category is assumed mandatory. Heads and directors cannot see private document reminder titles.
- **Review dates** (HR): set applicable probation/promotion review dates, approved policy/authority reference and optional responsible HR officer per staff file. Clear completed dates or enter the next dates. Promotion eligibility is never inferred from service length or grade alone.
- **Retirement & exit**: configure the approved retirement rule and notice interval. Tasks show indicative dates requiring officer validation. No default retirement age is assumed.
- **HR policies & letters**: maintain the holiday calendar and applicable leave policies/workweeks.

Rules and review dates have optimistic version checks and audit entries. Technical administrators and auditors cannot access personnel tasks. Staff see their own leave and permitted document reminders, heads their staff scope, and HR/directors their authorized administrative work. Appraisal review reminders reuse the existing restricted reviewer access. Tasks link to the request, relevant module and staff file; assignees or responsible roles are shown. Resolving source records automatically removes the corresponding outstanding tasks.

## Monthly reporting

The last completed month’s report is flagged for HR/directors until HR records a review note. Open **Prepare report** to generate the current summary for a selected current/past month and export CSV. Counts cover currently accessible, non-archived staff only:

- Current staffing by status and cadre, explicitly dated as a current snapshot (not reconstructed historical headcount).
- Approved/completed leave overlapping the month, with chargeable days recalculated using the current policy and holiday calendar. This does not change the original request charge snapshot.
- Verified attendance entries by outcome plus a separate unverified-entry count. Missing entries are not inferred as absence.
- Applied transfers with an effective date in the selected month.

Preparation, configuration and review are audited. The review marker acknowledges an officer’s review; it is not a locked historical report or final institutional approval. Reports opened after source data changes reflect those changes. No employment decision is automated.

## Release verification

No migrations or production sample records are required. Tests cover holiday/workweek return calculations, contiguous approved extensions, ending/due/overdue/resolved tasks, independent return confirmation, notification deduplication, review/rule conflicts, required-file checks, document latest-version privacy, retirement reminders, workforce pending scopes, monthly counts, review and CSV export. All pre-existing personnel/workflow tests must pass before deployment.
