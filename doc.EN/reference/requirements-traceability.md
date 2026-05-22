# Requirements traceability (PDF → microservice owner)

Legend: **Owner** is the microservice responsible for meeting the requirement first. Other services may consume the outcome.

| Requirement (paraphrased from the subject) | Owner |
|---|---|
| Read one or more CSV files of Belgian enterprise numbers | `MS-01` |
| Download public HTML pages; **no business extraction** during scraping | `MS-02` |
| Store raw pages on **HDFS** | `MS-03` |
| Never store error pages as valid raw documents | `MS-02` + `MS-03` |
| Mandatory metadata: timestamp, source, download status, HTTP code, proxy/IP, attempts, last update | `MS-02` |
| Each **source** is an independent acquisition unit (KBO page, Moniteur, BNB docs, statutes, powers, other related docs) | `MS-02`, orchestrated by `MS-10` |
| Trigger processing automatically after raw HTML lands in HDFS | `MS-10` + `MS-04` |
| Extract structured fields listed in the subject (managers, VAT activities, financials, links, establishments, publications, …) | `MS-04` |
| Persist structured data in a suitable DB | `MS-05` |
| Discover new enterprises from entity links; enqueue; history; seed vs discovered distinction | `MS-06` |
| Store provenance: source enterprise, discovered enterprise, reason | `MS-06` + `MS-05` |
| Regular status checks, rescraping, updating existing records | `MS-07` |
| Freshness policy (example: max ~2 weeks without revalidation/rescrape) | `MS-07` |
| Never hard-delete closed/struck-off companies; keep historical snapshots | `MS-05` + `MS-07` |
| Periodic analytics outputs (postal lists, activity clusters, rankings, evolution, open/closed, temporal) | `MS-08` |
| Real-time supervision dashboard (queues, stages, errors, proxy failures, performance) | `MS-09` |
| Proxy list references (external sites) | `MS-02` (implementation detail) |

If a requirement spans multiple owners, the **integration contract** is defined in `../contracts/public-interfaces.md`.
