# Staff grades and personnel files

The pilot's grade choices are **Senior**, **Principal**, **Deputy Chief** and **Chief**, as requested. They are a configurable local vocabulary; no promotion, salary or eligibility rule is inferred. HR administrators can manage the vocabulary in Settings. Existing staff are not regraded automatically.

## One staff ID, one personnel file

On **Staff directory & files → Add staff**, enter **Staff ID / File number**. This same identifier is the personnel file number; there is no independent number that could diverge from the staff ID. Leading zeros are preserved. IDs are trimmed and normalized to uppercase, may contain letters, numbers, slashes, underscores and hyphens, and must be unique, including across archived records.

After registration the identifier is read-only. Ordinary profile edits cannot renumber a staff file. Existing IDs are preserved. Older API/import clients that omit an ID retain the previous generated-ID behavior, and that generated staff ID is also the file number. The CSV template now includes `staff_id`; duplicate IDs within a CSV are rejected before any rows are committed.

Search by staff ID/file number, name or job title, then open the staff profile. The **Personnel file** section groups documents and their versions, linked leave/movement/administrative requests, training/CPD, promotion and exit records, and performance reviews that the current user is permitted to see. Assignment history and the passport photograph remain part of the same profile. Transfers keep the same personnel identity and file number.

HR can add categorized PDF/JPEG/PNG documents (up to 10 MB), record optional expiry dates, add versions, verify documents and download them through the existing private authorization flow. Employees retain only their authorized personal-document access and permitted upload categories. Heads have no general personnel-document access. Technical administrators and auditors have no personnel-file access. File counts and appraisal summaries are filtered through the original module permissions; hidden appraisal records are not counted or exposed.

Private object keys continue to use opaque internal IDs. The displayed file number does not create a public storage folder or expose private object URLs. The index is computed from existing staff relationships, so each staff record automatically has one file without a separate file-creation step.

The file index displays at most 100 entries per section and indicates additional records; use the dedicated module to search the complete register. It is an index into the existing workflows, not a new approval authority or an automatic promotion system.

Release health version: `0.3.2`. No schema migration is required: `file_number` is a read-only alias for the existing unique `staff_id`. The live grade setting was updated only after confirming no existing staff had conflicting grades. No demo staff or personnel documents were created.
