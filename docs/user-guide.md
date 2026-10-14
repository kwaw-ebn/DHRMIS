# Pilot administrator and employee guide

## Sign in

Use the invited email and private initial password. Privileged users add the displayed setup key as a time-based account in an authenticator app, enter its six-digit code, then change their temporary password. Keep setup keys private. Codes cannot be reused. Five failed attempts lock the account for 15 minutes. Sessions last eight hours; incomplete MFA expires in ten minutes.

## Organization

Demo North/South units are examples, not official facilities. Add approved sub-districts under the district, facilities under the district/sub-district, and departments under a district/facility. Choose facility categories. Rename incorrect names. Units with child units, active staff or scoped users cannot be archived.

## Staff records

Use Add staff and choose a configured facility/department, cadre and grade. Collect only approved identifiers. Duplicate GHS/payroll numbers are rejected; same name at the same unit requires manual review. Review profiles before marking them verified. IDs are generated automatically. Current record versions prevent silent edit overwrites. Unit reassignment is intentionally blocked until the transfer approval workflow exists. Archive retains history and disables the linked employee account. No unarchive interface is supplied in this pilot.

## CSV

Download the template, enter full_name, job_title, cadre and unit_id, and use exact configured vocabulary. Unit cards display import IDs. Dates use YYYY-MM-DD. UTF-8 CSV limit: 500 rows/2 MB. Any validation error rejects all rows. Imports require HR verification. Exports honor filters and scopes, use a limited directory field set and neutralize leading formula characters. Sensitive full-profile exports are not provided.

## Accounts

HR administrators invite accounts; no public signup. Select the matching scope for head roles or select an existing staff member for an employee account. Share temporary passwords privately. Disabling/resetting revokes sessions. Reset preserves MFA. Lost MFA requires identity verification and trusted infrastructure recovery. Technical platform administrators manage technical accounts only and cannot read personnel APIs.

## Employees and reports

Employees see only their own profile and may change their password/sign out. Leave, document and correction workflows are later phases. Contact HR for these actions during evaluation. Dashboards use current scoped database records. Licence alerts include expired licences and those due in 90 days; they do not determine employment decisions. Current reports support CSV and browser printing, not generated PDF/Excel. Audit access is restricted to HR administrators/auditors and avoids copying confidential changed values.
