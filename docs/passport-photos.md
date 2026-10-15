# Staff passport photographs

HR administrators and HR officers can add an optional passport photograph when registering or editing a staff member. Choose a JPEG or PNG up to 2 MB; the form shows a preview. Save the record to upload it. A staff member can be registered without a photograph and receives an initials avatar.

The staff profile displays the photograph. To replace it, choose **Edit profile**, select the new image and save. Concurrent replacements are rejected: reopen the form to review the latest photo before retrying. Each accepted replacement retains an immutable private version and an audit entry. Earlier versions are retained privately for the institution's approved retention process; no public history or deletion endpoint is provided.

Authorized employees can view their own photo; scoped heads can view photographs for staff in their organizational subtree; HR and the director retain their existing staff scope. Platform administrators and auditors have no photo access. Uploading and replacing are restricted to HR. Archiving a staff record removes its normal photo access.

Photos use the existing private S3-compatible storage and bucket configuration. Images are returned through an authenticated same-origin API with no-store headers; the API never returns object keys or public/signed photo URLs. Files are decoded and validated, limited to 16 megapixels, correctly oriented, reduced to at most 600 × 800 pixels and re-encoded as JPEG. Original camera/location metadata is stripped. These limits support profile display rather than certifying a photograph against an official identity-document standard.

If private storage is temporarily unavailable, the personnel record remains saved. The form keeps the saved staff ID so retrying does not create a duplicate person. Reopen the saved profile to upload the photo later if needed. Unsaved previews use temporary browser memory and are released when the form closes.

Alembic revision `05c436c0d031` adds `staff_photo_versions`. Existing employees/accounts are preserved and no sample photos or staff are added. The release health version is `0.3.1`. Tests cover optional/missing photos, metadata stripping/resizing, staff scope and denied roles, CSRF, archived staff, invalid/spoofed/oversized files, stale replacement versions and storage failure preservation.
