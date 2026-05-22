# MS-03 — Raw storage on HDFS (layout, registry, integrity)

## Goal

Own **where** raw bytes live and how they are **referenced** by the rest of the system.

## Scope

- HDFS (or course-approved equivalent) client wrapper: upload/download/delete policy (prefer **no deletes** for audit; use tombstones if needed)
- Path conventions + versioning (`raw/v1/...`) — see `../contracts/public-interfaces.md`
- Sidecar `metadata.json` stored next to raw object
- Integrity: content hash (recommended), size checks

## Out of scope

- HTTP downloading (`MS-02`)
- Parsing HTML (`MS-04`)

## Task checklist (programming)

- [x] **T03.1** Implement `put_raw_object(local_path|bytes, hdfs_target_path) -> PutResult`
- [x] **T03.2** Implement `write_metadata_sidecar(metadata: dict, hdfs_dir) -> path`
- [x] **T03.3** Implement `read_raw_bundle(hdfs_dir) -> (bytes, metadata dict)` for downstream extractors
- [x] **T03.4** Enforce “no error page stored as success” at the storage boundary (reject obviously invalid content types / known error markers—coordinate rules with `MS-02`)
- [x] **T03.5** Register each stored object in DB (`MS-05` table `raw_documents`) *or* emit an event consumed by `MS-05` (pick one pattern early) — **événements** via `register_raw_document_listener`

## Definition of Done (DoD)

- Given a fake HTML file + metadata, the system stores it in HDFS and can retrieve it bit-identically.
- Path layout is stable and documented.
- Failures produce actionable errors (permission, quota, missing namenode, etc.).

## Integration notes

- `MS-02` calls this module after a successful validated download.
- `MS-04` reads through this module (do not let parsers reach HDFS ad hoc).

## Freeze outputs

- HDFS path contract + sidecar schema version.
