-- User-supplied Agona East reference units, 2026-10-15.
-- Additive and idempotent. Existing assignments, departments and accounts stay intact.
DO $$
DECLARE
    district_id text;
    sub_id text;
    item record;
    facility jsonb;
    added integer := 0;
    affected integer;
    mapping jsonb := '{
      "Kwayanko Sub-district": [
        ["Kwayanko Health Centre","Health Centre"], ["Kokoado CHPS","CHPS"],
        ["KTK CHPS","CHPS"], ["OTK CHPS","CHPS"], ["Suromanya CHPS","CHPS"]
      ],
      "Asafo Sub-district": [
        ["Asafo Health Centre","Health Centre"], ["Tawora CHPS","CHPS"],
        ["Kwansakrom CHPS","CHPS"], ["Brahabekum CHPS","CHPS"]
      ],
      "Nsaba Sub-district": [
        ["Nsaba Health Centre","Health Centre"], ["Ofoase CHPS","CHPS"],
        ["Duabone CHPS","CHPS"], ["Ninta/Nampong CHPS","CHPS"], ["Kwasi Paintsil CHPS","CHPS"]
      ],
      "Mankrong Sub-district": [
        ["Mankrong Polyclinic","Polyclinic"], ["Esusau CHPS","CHPS"],
        ["Kenyankor CHPS","CHPS"], ["Oboyambo CHPS","CHPS"], ["Fante Badjiase","Other"]
      ],
      "Duakwa/Mensakrom Sub-district": [
        ["Mensakrom Health Centre","Health Centre"], ["Jacob CHPS","CHPS"],
        ["Mansofo CHPS","CHPS"], ["Namawora CHPS","CHPS"]
      ]
    }'::jsonb;
BEGIN
    SELECT id INTO STRICT district_id FROM organization_units
    WHERE kind='district' AND name='Agona East District Health Directorate' AND active=true;
    FOR item IN SELECT key,value FROM jsonb_each(mapping) LOOP
        SELECT id INTO sub_id FROM organization_units
        WHERE parent_id=district_id AND lower(name)=lower(item.key) AND kind='subdistrict';
        IF sub_id IS NULL THEN
            sub_id := gen_random_uuid()::text;
            INSERT INTO organization_units(id,name,kind,category,parent_id,active)
            VALUES(sub_id,item.key,'subdistrict',NULL,district_id,true);
            added := added+1;
        ELSIF NOT (SELECT active FROM organization_units WHERE id=sub_id) THEN
            RAISE EXCEPTION 'Existing sub-district % is archived; review manually',item.key;
        END IF;
        FOR facility IN SELECT value FROM jsonb_array_elements(item.value) LOOP
            IF EXISTS (SELECT 1 FROM organization_units WHERE parent_id=sub_id AND lower(name)=lower(facility->>0) AND (kind<>'facility' OR active=false OR category IS DISTINCT FROM facility->>1)) THEN
                RAISE EXCEPTION 'Conflicting existing facility %; review manually',facility->>0;
            END IF;
            INSERT INTO organization_units(id,name,kind,category,parent_id,active)
            SELECT gen_random_uuid()::text,facility->>0,'facility',facility->>1,sub_id,true
            WHERE NOT EXISTS (SELECT 1 FROM organization_units WHERE parent_id=sub_id AND lower(name)=lower(facility->>0));
            GET DIAGNOSTICS affected = ROW_COUNT;
            added := added+affected;
        END LOOP;
    END LOOP;
    IF added>0 THEN
        INSERT INTO audit_logs(id,actor_id,actor_name,action,entity_id,detail,created_at)
        VALUES(gen_random_uuid()::text,NULL,'Authorized district configuration','DISTRICT_UNITS_CONFIGURED',district_id,
          'User-supplied five sub-districts and 23 facilities; additive import. Fante Badjiase category Other pending confirmation. Added '||added||' units.',CURRENT_TIMESTAMP);
    END IF;
END $$;
