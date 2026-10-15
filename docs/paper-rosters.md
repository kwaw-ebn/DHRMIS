# Paper duty roster uploads — 0.4.2

Open **Duty rosters → Uploaded paper rosters → Upload roster copy**. Select the facility/department, title and roster period, then choose a PDF scan or a clear JPEG/PNG photo (maximum 10 MB per file). Use one multipage PDF or upload separate pages with distinct titles. The date controls above the section filter copies whose roster period overlaps the selected dates; an additional workplace filter is available.

HR and scoped sub-district/facility/department heads can upload and archive copies within their scope. Directors can read. Staff can read their own workplace copies; department staff can also read the parent facility/office roster, but cannot read other department copies. Technical administrators and auditors have no roster-file access. Uploaders should include only the roster for the selected workplace, since that workplace’s staff can read it.

Files use the existing private document storage with opaque object keys and short-lived, authenticated download links. Metadata listings never expose object keys. JPEG/PNG images are verified, rotated to their intended orientation and re-encoded without EXIF/camera metadata; dimensions are bounded to 25 megapixels/6000 pixels per side. PDF header/trailer checks reject obviously incomplete PDFs; this is not a malware scan or a guarantee of PDF content. Downloads are attachments. Files and metadata are audited. Duplicate copies for the same unit and period are blocked. Failed metadata commits attempt private-object cleanup.

Copies are immutable. To correct one, archive it with a reason and upload a corrected copy. Archiving hides it from staff access while retaining the private original/history; a download link already issued can remain valid for up to 60 seconds. Archived originals are not deleted. No upload, download or archive changes staff accounts, attendance or assignments.

A scanned/photo roster is a reference copy. It does not extract shifts, perform OCR, verify attendance or run automatic leave/overlap checks. Individual shift records remain available for those checks.

Migration `d82136f88282` adds `roster_uploads` after `05c436c0d031`. It was checked locally with Alembic and tested on the isolated Neon branch before deployment. Production uses the existing startup Alembic upgrade path. No demonstration roster or staff records are created in production.
