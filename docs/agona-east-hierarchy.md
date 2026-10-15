# Agona East work locations — 0.4.1

The user supplied this operational hierarchy on 15 October 2026. These are real reference units, not synthetic personnel. DHD and its five existing departments are preserved.

| Sub-district | Facilities |
| --- | --- |
| Kwayanko | Kwayanko Health Centre; Kokoado CHPS; KTK CHPS; OTK CHPS; Suromanya CHPS |
| Asafo | Asafo Health Centre; Tawora CHPS; Kwansakrom CHPS; Brahabekum CHPS |
| Nsaba | Nsaba Health Centre; Ofoase CHPS; Duabone CHPS; Ninta/Nampong CHPS; Kwasi Paintsil CHPS |
| Mankrong | Mankrong Polyclinic; Esusau CHPS; Kenyankor CHPS; Oboyambo CHPS; Fante Badjiase |
| Duakwa/Mensakrom | Mensakrom Health Centre; Jacob CHPS; Mansofo CHPS; Namawora CHPS |

Fante Badjiase is treated as a separate facility, category Other, because no category was specified. There are five sub-districts and 23 facilities, plus the existing District Health Directorate office (DHD).

## Staff entry

Choose **Work location: sub-district / DHD**, then choose a facility within that sub-district. Changing the sub-district clears the previous facility selection. DHD selects the Directorate office and offers an optional department. A required selector prevents saving without a work location. Staff profiles and the directory display the location hierarchy. Existing staff assignments remain read-only on profile edits and require the approved posting/transfer process to change. Receiving-location selection in that process uses the same cascading control.

The database keeps the canonical facility/department `unit_id`; the sub-district is derived from its ancestry rather than storing two potentially conflicting fields. Server validation and role/subtree access restrictions remain in force. Staff registration remains restricted to HR; employees cannot reassign themselves.

## Configuration import

`backend/config/agona-east-units.sql` is an additive, audited import for this existing district. It was tested twice on the isolated Neon test branch to verify idempotency, then applied to the pilot. It preserves existing DHD departments and adds no employees or accounts. It aborts on conflicting archived/type/category records instead of overwriting them. It is not run on startup, so future HR changes are not automatically undone. No schema migration is required.
