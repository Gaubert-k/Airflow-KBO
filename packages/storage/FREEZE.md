# MS-03 — Contrat gelé (v1)

Tag suggéré : `freeze/MS-03-v1`

## Chemins HDFS (layout v1)

Racine : `{HDFS_RAW_ROOT}` (défaut `hdfs://localhost:9000/raw/v1`)

```
{raw_root}/source={source}/enterprise_number={10digits}/doc_type={doc_type}/run_id={uuid}/
  document.html | document.bin
  metadata.json
```

## Sidecar `metadata.json`

- `schema_version`: **1** (obligatoire après écriture)
- Champs requis : voir `doc.EN/contracts/public-interfaces.md`

## API publique (Python)

- `put_raw_object(local_path|bytes, hdfs_target_path) -> PutResult`
- `write_metadata_sidecar(metadata, hdfs_dir) -> str`
- `read_raw_bundle(hdfs_dir) -> (bytes, dict)`
- `store_raw_bundle(...)` — opération haut niveau pour MS-02
- `register_raw_document_listener` — événements pour MS-05

## Backend dev

Stub filesystem : `HDFS_LOCAL_ROOT` mappe les URI `hdfs://` vers le disque local.
