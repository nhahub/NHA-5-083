# Project Plan

## 1. Purpose and objectives

**Problem.** Restaurant data is spread across datasets with inconsistent formats, missing values, duplicates, and different geographic representations, which makes it hard to search, compare, and explore across locations.

**Objectives**

1. Integrate restaurant data from multiple sources into one centralized MySQL database on Azure.
2. Build automated ETL pipelines using Bronze, Silver, and Gold layers.
3. Implement data-quality checks and quarantine invalid records instead of silently dropping them.
4. Deliver a web app with filtering, an interactive map, and natural-language search.
5. Orchestrate the pipeline with Apache Airflow.
6. Deploy the database and application on Microsoft Azure.
7. Document the system to the academy's standard.

**Success criteria**

- The pipeline runs end-to-end through Airflow and every rejected record is logged with a reason.
- At least two sources are integrated, with source kept per record.
- The three features work against real data through a public URL (or a demonstrated fallback if Azure access fails).
- A new team member can set up the project from the README alone.

## 3. Scope tiers (MoSCoW)

**Must (MVP)**

- M1: Zomato dataset through Bronze (Azure Blob), Silver (cleaned MySQL tables), and Gold (views/indexes)
- M2: At least one additional source integrated (decided in S1)
- M3: Data-quality rules with a quarantine table
- M4: FastAPI endpoints with parameterized queries
- M5: React filters and results list
- M6: Leaflet map with markers and details
- M7: NLP search through Hugging Face with validation and a rule-based fallback
- M8: One Airflow DAG that runs the pipeline (locally in Docker is acceptable)
- M9: MySQL on Azure, backend on App Service, frontend on Static Web Apps
- M10: Documentation, README, demo

**Should**

- Airflow deployed on an Azure Linux VM
- Incremental loads (process only new or changed records)
- Cross-source duplicate matching
- Azure Key Vault for secrets
- Tests for transformation and quality rules
- Pipeline monitoring page

**Could**

- Virtual Network and private networking
- Azure Monitor and Application Insights
- Arabic NLP queries
- Further sources, historical snapshots
- UI polish

**Cut rule:** if Must items are behind at the end of Sprint 1, cut from Should first. Feature freeze is 28 Nov.

**Out of scope:** owner accounts, B2B matching, in-app reviews, additional business types.

## 4. Methodology: Agile (Scrum-lite)

- **Sprints:** one week each, with a planning session at the start (30 min), a short mid-week sync, and a review plus retrospective at the end.
- **Backlog:** a GitHub Projects board with one card per task; priorities match the MoSCoW tiers; requirement IDs from `docs/SRS.md`.
- **Spikes:** timeboxed investigations for open questions, with decision criteria and due dates. Results are recorded in a decision log.
- **Definition of Done:** merged by pull request with review, tests pass (where applicable), docs updated.
- **Living documents:** each document carries a status header and change log. Unresolved items are marked TBD.

## 5. Team and responsibilities

| Member | Role |
| -------- | ------ |
| Ziad Ahmed El Shamy | TBD |
| Ali Ahmed Ali Kassem | TBD |
| Yehia Nader Ali | TBD |
| Abdulrahman Salem | TBD |
| Ahmed Hany | TBD |
| Ziad Salah ElKady | TBD |

**Suggested role areas to assign in Sprint 0** (each person owns one area and one test area):

1. Ingestion and Bronze layer (Python, Blob Storage)
2. Cleaning, Silver layer, quality rules
3. Database schema, Gold layer, indexes (MySQL)
4. FastAPI backend and NLP adapter
5. React frontend and Leaflet map
6. Airflow, Azure deployment, CI

Everyone contributes to documentation and testing.

## 6. Spikes (open decisions)

| ID | Question | Due | Decision criteria | Fallback |
| ---- | ---------- | ----- | ------------------- | ---------- |
| S1 | Which additional source(s) and geographic data? | 17 Nov | Rows and category completeness for target cities (including Egypt), valid coordinates, license, ingestion effort | Overture Maps only |
| S2 | Airflow: local Docker only, or Azure VM too? | Local by 18 Nov; VM decision 21 Nov | Setup time, reliability, cost, demo value | Airflow in Docker for the demo; scripts stay scheduler-agnostic |
| S3 | Which Hugging Face model and provider? | 18 Nov | Correct extraction rate on 30-50 sample queries, JSON reliability, latency, free-tier limits, language support | Rule-based parser using the controlled vocabulary |
| S4 | Azure access, credits, and cost | 31 Oct / first days of Sprint 1 | Do all members have working subscriptions? What does MySQL Flexible Server plus VM cost? Budget alerts set | Local MySQL and Docker for the demo; document the limitation |

**S3 method:** write the sample queries and expected parameters first, then score each candidate model on them. Choose on measured results.

## 7. Iteration plan

**Sprint 0: 30-31 Oct (documentation)**

- Tasks: finalize and submit the five documents; create repository skeleton and board; assign roles; check Azure access (S4).
- Deliverables: docs v0.2 submitted, repo structure, role assignments.

**Break: 1-14 Nov (optional, no hard deliverables)**

- Light prep only: install toolchains (Python, Node, Docker); one member verifies Azure credits and creates a resource group with a budget alert; one member inspects the Zomato file and lists its quirks (encoding, currencies, zero ratings, invalid coordinates).

**Sprint 1: 15-21 Nov (data foundation and search backbone)**

- Tasks: Zomato to Bronze, Silver, and MySQL (local first, then Azure); schema v1 scripts; quality rules and quarantine table; close S1 and start ingesting source 2; run S2 and S3; FastAPI filter endpoints; React skeleton with filters and list.
- Deliverables: pipeline works end-to-end for Zomato; Azure database reachable; filter search works on real data.

**Sprint 2: 22-28 Nov (product and deployment)**

- Tasks: second source integrated; Gold views and indexes; map; NLP endpoint with fallback; Airflow DAG scheduled; deploy frontend and backend to Azure; tests; Should items as capacity allows. **Feature freeze 28 Nov.**
- Deliverables: three features working on the deployed app.

**Final: 29-30 Nov (hardening and delivery)**

- Tasks: bug fixes only; finalize docs and README run instructions; demo rehearsal; record a backup demo video.
- Deliverables: final submission, demo, retrospective notes.

## 8. Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
| ---- | ------ | ------------ | -------- | ------------ |
| R1 | Only about two weeks of real build time because of midterms | High | High | Tiered scope, cut rule, feature freeze 28 Nov, optional break prep |
| R2 | Azure provisioning, credits, or cost problems | Medium | High | S4 first; budget alerts; local fallback for the demo |
| R3 | Zomato data quirks (encoding, mixed currencies, zero ratings, invalid coordinates) take longer than planned | High | Medium | Inspect during break; define rules early; quarantine table |
| R4 | No Egypt coverage in the baseline dataset, so Cairo demos return nothing | High | Medium | S1 must include a source covering Egypt, or use cities present in the data for demos |
| R5 | Hugging Face limits, latency, or model quality | Medium | Medium | Adapter pattern, caching, rule-based fallback |
| R6 | Airflow setup consumes disproportionate time | Medium | Medium | Local Docker first; VM only if time allows |
| R7 | License or terms violation | Low | High | Verify licenses (S1); keep attribution; no scraping against terms |
| R8 | Skill gaps (SQL, React, FastAPI, Azure) | High | Medium | Pairing, small first steps, shared notes |
| R9 | Scope creep | High | Medium | Scope baseline, MoSCoW, change log |
| R10 | Overlap with existing public projects | Medium | Medium | Cite and differentiate (see literature review); original code |

## 9. Communication and tooling

- Source control: GitHub with feature branches and pull requests (see `CONTRIBUTING.md`).
- Task tracking: GitHub Projects and Issues.
- Chat: TBD. Decisions made in chat are copied into the decision log.
- Coding standards: `docs/CODE_STYLE.md`.

## 10. Deliverables checklist

- [x] Project plan (this document)
- [x] Literature review
- [x] SRS and system design (requirements, use cases, architecture, data model)
- [ ] Bronze, Silver, Gold pipeline and database
- [ ] Airflow DAG
- [ ] Web application with three features
- [ ] Tests and quality report
- [ ] README with run instructions and deployed link
- [ ] Final presentation and demo

## 11. Change log

| Date | Change | Reason |
|------|--------|--------|
| 2026-10-30 | v0.1 created | Initial draft |
| 2026-10-30 | v0.2: stack aligned to team proposal; calendar and scope tiers added | Team proposal and deadline constraints |
