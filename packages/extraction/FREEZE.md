# FREEZE — MS-04 Extraction v1

## Interface

- `parse_raw_document(content, metadata) -> ParseResult`
- `parse_batch(limit=...) -> ParseBatchReport`

## Parsers v1

- `kbo` + `enterprise_detail` — champs généraux, dirigeants, NACE, liens
- Autres sources — parseur générique (`partial=true`)

## États MS-05

- Entrée : `QUEUED_PARSE` (claim → `PARSING`)
- Succès : `STRUCTURED` + `append_snapshot`
- Échec : `FAILED_PARSE`

## Découverte

- Candidats émis vers `packages.discovery.apply_discovery_from_parse` après parse OK.
