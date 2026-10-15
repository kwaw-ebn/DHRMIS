# HR document register — 0.4.4

Open **Document register → Upload document**. Enter the document's **filing number before uploading**, then its title/category, document or meeting date, received/sent/filed date and optional sender, recipient, external letter reference and notes. The office is fixed to **Human Resources and Administration (HR)** under DHD. The server assigns this office; submitting another unit is rejected. Only HR can upload or archive new administrative documents. Existing private staff files and other unit/workforce features are unaffected.

Filing numbers are entered by HR, not automatically generated. They use 1–80 letters, digits, spaces or `/ _ . -`. The server trims and normalizes spacing and stores uppercase, preserving leading zeros. Each number is unique across the entire register, including archived records, and is permanent after registration. A letter's external reference remains a separate optional field. It is not used as the filing number automatically.

## Retrieval

Enter the complete filing number in **Filing number → Look up document**. Lookup is exact and case-insensitive; partial numbers, title searches and sender/recipient searches are not used. **Show all registered documents** returns the paginated register. The filing number appears prominently in the list and details. The legacy general-search API parameter is rejected with a filing-number instruction.

The rollout found no uploaded administrative records in production. For safe upgrades elsewhere, existing records are preserved with a blank filing number rather than inventing a code. HR can open their details and manually register an unused filing number once; version checks prevent stale assignments. New uploads always require a filing number. There is no renumbering endpoint for already registered files.

## Files and access

Categories include meeting minutes, incoming/outgoing letters, memos, circulars, reports, policies/guidelines and other administrative records. Incoming letters require a sender; outgoing letters require a recipient. Uploading an outgoing letter stores a copy and does not send it. Use the existing Correspondence register for workflow tasks and Personnel documents for confidential individual staff files.

Supported files: PDF, JPEG, PNG, Word DOCX and Excel XLSX, maximum 10 MB per file. Legacy DOC/XLS, encrypted Office packages and macro-enabled files are unsupported; export a PDF instead. For multipage scans, use one PDF. Files are immutable: archive an incorrect/superseded copy with a reason and upload the correction under a new, manually entered filing number. Private originals and audit history are retained; an already issued download link can remain valid for up to 60 seconds.

HR and the Director retain read access. Existing scoped management visibility/ownership rules remain for reading applicable records; ordinary employees, technical administrators and auditors cannot use this register. New uploads are located only in HR. Default access remains HR/Director and the uploader. Optional unit-management visibility follows existing organizational scopes and does not publish to ordinary employees. Heads no longer upload/archive administrative register records; their duty-roster and other unit features are unchanged.

Files use the existing private object storage with opaque keys and short-lived, authenticated attachment downloads. Object keys/checksums are not listed. Image metadata is stripped; Office package size/count, encryption, CRC and macro-indicator checks are applied. These checks are not malware scanning; Office content/metadata is retained. Access, uploads, downloads, filing registration and archiving are audited. Failed metadata commits attempt private-object cleanup.

Migration `021ff8cc873e` adds a nullable, uniquely indexed filing-number column after `89c9665285d7`, preserving existing records. New API uploads require the field. Local Alembic upgrade/check and an isolated Neon branch test precede normal production startup migration. No sample documents or accounts are created.
