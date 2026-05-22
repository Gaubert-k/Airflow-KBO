# Project brief (English) — Belgian companies data platform

## Vision

Build a **distributed-style** platform to **scrape**, **orchestrate**, **process**, and **visualize** **public** data about **Belgian companies** (BCE/KBO, Moniteur belge, BNB / Centrale des bilans, legal publications).

Example entry points mentioned in the subject:

- KBO public pages (example pattern in the PDF): `https://kbopub.economie.fgov.be/kbopub/toonondernemingsps.html?...`
- BNB consultation portal: `https://consult.cbso.nbb.be/`

## Non-goals (clarifies boundaries)

- The scraper must **not** perform business extraction at download time.
- **Error pages must never** be stored as if they were valid documents.

## Functional domains (from the subject)

1. **Acquisition**: read enterprise numbers from CSV(s), fetch public HTML, **validate**, store **raw** documents on **HDFS**, record mandatory metadata.
2. **Extraction & structuring**: process HTML from HDFS into structured fields; persist into an **appropriate database**.
3. **Dynamic discovery**: when parsing finds links between entities, enqueue **new** enterprise numbers; keep provenance (source enterprise, discovered enterprise, reason); distinguish **seed** vs **discovered**.
4. **Lifecycle**: keep data fresh (example: **revalidate at least every 2 weeks**), support rescraping, status changes (inactive, struck off, merged, legal form changes). **Never delete** closed/struck-off companies; keep historical state and documents.
5. **Analytics**: periodic jobs producing business indicators (postal code lists, activity groupings, financial rankings, evolution stats, open/closed indicators, temporal analyses).
6. **Supervision**: a **real-time dashboard** showing pipeline stage, queues, successes/failures (scraping, parsing, validation), proxy/IP failures, and global performance.

## Orchestration expectation

The subject explicitly requires **automatic pipelines**, **dependencies between steps**, and **supervision**. In practice, **Apache Airflow** is the orchestration spine; microservices are the **implementations** invoked by tasks.
