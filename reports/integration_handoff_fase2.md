# Meteotracker canonical interface

Read-only consumption contract for `bologna_urban_climate_integration`.
Do not copy these files into the integration repository; consume them in place.

```text
Meteotracker canonical interface
campaign_catalog:
    D:\projects\Meteotracker\outputs\campaign_catalog.csv
recommended:
    D:\projects\Meteotracker\outputs\recommended
repeated_segments:
    D:\projects\Meteotracker\outputs\repeated_routes\repeated_segments.csv
passages:
    D:\projects\Meteotracker\outputs\repeated_routes\segment_passages.csv
memberships:
    D:\projects\Meteotracker\outputs\repeated_routes\point_segment_memberships.csv
supporting_matches:
    D:\projects\Meteotracker\outputs\repeated_routes\point_segment_match_support.csv
geopackage:
    D:\projects\Meteotracker\outputs\repeated_routes\repeated_routes.gpkg
provenance:
    D:\projects\Meteotracker\outputs\campaign_catalog_provenance.json
    D:\projects\Meteotracker\outputs\repeated_routes\provenance.json
source_commit:
    f404ae3587033835285be87b5a633dd821938e47
matching_version:
    repeated_routes_schema_version_3
matching_config_fingerprint:
    a757e66cd0b075e9074ff0492d9ab10eb941d3f0659a9ec60dd99189e1117c51
qc_version:
    session_qc_v1
qc_config_fingerprint:
    0e06b2ee5397030ba4592eeaa1e86857cc5a32cfe127821946be60875641ebc4
generated_at:
    2026-09-16T20:55:32.299967+00:00
product_status:
    OFFICIAL
audit_root_not_for_consumption:
    D:\projects\Meteotracker\outputs\audit\
```

Identity key: `canonical_campaign_id` from `data/manifests/campaign_manifest.csv`.
Membership model: many-to-many `(repeated_segment_id, segment_passage_id, source_file, source_row)`.
Pending raw (not canonical): `8-1/` and `9-8/` listed in catalog provenance as `PENDING_RAW_NOT_IN_MANIFEST`.
