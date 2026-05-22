# Copy/paste prompt template (one microservice at a time)

Replace the placeholders, paste into your AI chat.

---

You are implementing **only** microservice **`MS-__`** for our student project (Belgian companies: scraping → HDFS → parsing → DB → Airflow orchestration → analytics → dashboard).

**Hard rules**

- Do **not** modify code owned by other microservices unless strictly necessary for compilation; if unavoidable, list every cross-edit explicitly.
- Follow the public contracts in `doc.EN/contracts/public-interfaces.md` as the source of truth.
- After changes, update only the relevant `MS-__` documentation if the scope/DoD changed.

**Inputs I provide**

- Repo path: `...`
- Current frozen tags/commits (if any): `...`

**Deliverables**

- Implement the task checklist in `doc.EN/microservices/MS-__-....md`
- Meet the Definition of Done in that file
- Add minimal tests/fixtures required by that MS file

**Output format**

1. Short plan (5–10 bullets)
2. Code changes (patches/files)
3. How to run/verify locally
4. Freeze notes: what interfaces are now stable

---
