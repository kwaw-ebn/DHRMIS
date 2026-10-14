# Phase 2 — daily HR administration

Phase 2 adds working leave, internal movements, private document management, correspondence, administrative requests, approval history, in-app notifications and letter PDF exports. Use synthetic staff and test policies until institutional approval. Existing accounts, MFA, personnel records and historical initial assignments remain intact.

## Setup

1. In HR policies & letters, enter the verified transfer approval role, its authority reference, institutional heading and authorized signatory details. PDF copies contain a signature line; the app does not create a digital signature.
2. Add leave policies with a reference, calendar/working-day basis, explicit working weekdays, whether an allocated balance is required, and final approval role. Rules are immutable: deactivate a superseded policy and create a new version under a distinct name.
3. Configure confirmed public holidays. No Ghana holiday calendar or leave entitlement is invented. New applications snapshot their calculated dates/days; later calendar changes do not silently change applications already submitted.
4. Allocate authorized annual balances per employee/policy/year, documenting the allocation or adjustment. Cross-year requests use each year's balance separately. Pending leave reserves days and cannot exceed the available allocation. Approved/commenced/completed requests charge the allocation. Rejection/cancellation releases it.
5. Create the authorized head, HR officer and final approver accounts in User management. Final approval cannot be performed by the submitter or linked employee. Privileged accounts require MFA. The sole pilot administrator cannot run every approval stage alone.

## Leave

Employee or HR submits → originating supervisor recommends → HR validates → configured final role approves. HR can record an external supervisor recommendation with a comment, provided they did not submit the request. Rejection needs a reason. Pending requests can be cancelled by their submitter or HR. Approved unstarted leave requires a cancellation request and final-authority approval. Leave commencement is confirmed within the approved period by scoped heads/HR; staff status changes at commencement rather than immediately on approval. Employee/HR reports return, then scoped heads/HR confirm it. Early return does not automatically prorate a balance; any policy-based adjustment requires documented HR handling. Overlapping leave periods and stale/duplicate decisions are rejected.

## Postings and movements

HR initiates an internal transfer, reassignment, temporary deployment or secondment with an effective date and target unit. Temporary deployment/secondment requires a planned end date. The origin recommendation, HR validation and final approval stages must be completed, followed by receiving-unit acknowledgement. A scoped receiving head acknowledges, or HR administrator records an external receiving officer's acknowledgement. HR applies the movement once its effective date arrives. The source must still match; inactive target units and incompatible staff statuses are rejected. Previous assignments close at the cutover date, using exclusive end dates; a new assignment is added, the personnel ID is preserved and an obsolete supervisor link is cleared. Planned end dates generate review reminders and never silently reverse an assignment.

This MVP processes internal placements; new staff registration creates its initial posting. Cross-district transfer-in/out, concurrent appointments and externally routed regional approvals are not implemented in Phase 2.

## Private documents

Neon bucket `personnel-documents` is private. The server validates scope, type signature and size (PDF/JPEG/PNG, up to 10 MB), uploads to immutable object keys and records checksum/version metadata. New versions retain previous files. HR verifies each version and controls whether an employee may view it. Employees can upload their own licences, academic/training certificates and other supporting documents, but cannot replace HR-issued versions or upload official appointment/appraisal letters. Heads, auditors and technical platform roles have no document API access. Authorized downloads use 60-second signed links and attachment disposition. Archive/file deletion is intentionally not exposed. PDF in-app preview and malware scanning are not implemented; scan uploads externally before any real-data rollout.

## Requests, correspondence and notifications

Employees submit personal administrative requests; HR can submit on behalf of an employee, assign an active HR officer, respond and close. Employees see their own requests and responses. HR registers incoming/outgoing correspondence or internal memos, records offices/external references, tracks deadlines and assignment, and exports letter copies. The director has authorized district workflow visibility; ordinary employees cannot see the correspondence register.

In-app notifications are created transactionally for workflow changes. Opening Notification centre refreshes deduplicated deadline, leave-start, temporary-placement-end and current document-version expiry reminders within the user's authorized scope. These are on-demand reminders, not an unattended background scheduler. No SMS/email provider is activated. Notices provide minimal context, and linked details enforce current permissions.

## Validation and rollout

Migrations add tables without rewriting Phase 1 personnel records. Test them on a Neon child branch first. Docker startup applies Alembic before serving the updated API. Set AWS_ENDPOINT_URL_S3, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION and DOCUMENT_BUCKET in Render; keep credentials outside Git. Extend encrypted backups to include private objects and their version/checksum metadata. Production additionally requires malware scanning, private-storage recovery drills, authorization review, restricted runtime credentials and the previously documented institutional approval controls.
