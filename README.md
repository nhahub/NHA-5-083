# Global Restaurant Explorer (EatoSphere)

> **Status:** Increment 1 Complete (v1.0) · **Last updated:** 2026-11-26  
> **Repository:** <https://github.com/Ziad17-Ai/Global-Restaurant-Explorer-> (Academy ref: <https://github.com/nhahub/NHA-5-083>)

## 1. What is this?

A data engineering platform that programmatically ingests restaurant data on per-source schedules, cleans, standardizes, and validates it through **Bronze, Silver, and Gold** Medallion layers (with a 15% quarantine safety gate and incremental upserts), stores it in **MySQL 8.0 on Microsoft Azure**, and serves it through a **FastAPI** backend and an Editorial-themed **Streamlit 1.67.x** web app.

The data pipeline is the core of the project. The web app is the layer users interact with.

### Reference Live Deployment (`polandcentral`)
>
> **Note:** Azure Container Apps generates unique FQDNs per deployment. The links below point to the team's reference deployment; your own deployment will generate its own URLs (see [`docs/DEPLOY_AZURE.md`](docs/DEPLOY_AZURE.md)).
- **Streamlit Web App:** <https://ca-eatosphere-streamlit.politeriver-19c81647.polandcentral.azurecontainerapps.io>
- **FastAPI Backend & OpenAPI Docs:** <https://ca-eatosphere-backend.politeriver-19c81647.polandcentral.azurecontainerapps.io/docs>

---

## 2. Running & Deployment Guides

Execution and deployment instructions are separated into two dedicated runbooks:

| Guide | Audience & Purpose | Link |
| --- | --- | --- |
| **Run Locally** | Full-stack **Docker Compose** (MySQL, Airflow 3.x, FastAPI, Streamlit) & **Local Python** (with CSV fallback), workflow diagrams, tests, and local troubleshooting | [`docs/RUN_LOCAL.md`](docs/RUN_LOCAL.md) |
| **Deploy to Azure** | End-to-end **Microsoft Azure** production deployment (\$100 Student budget) via **Track A (Manual CLI)**, **Track B (Agentic/MCP)**, or **Track C (Manual Azure Portal Web UI)**, plus OIDC CI/CD and common errors & fixes | [`docs/DEPLOY_AZURE.md`](docs/DEPLOY_AZURE.md) |

---

## 3. Where to find each academy deliverable

| Academy requirement | File(s) |
| --- | --- |
| **Project Planning and Management** (objectives, incremental delivery, scope, methodology, roles, sprints, risks) | [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) |
| **Literature Review** (related work, data sources review, technical background, positioning, references) | [`docs/LITERATURE_REVIEW.md`](docs/LITERATURE_REVIEW.md) |
| **Requirements Gathering** (stakeholders, user stories, use cases, functional and non-functional requirements) | [`docs/SRS.md`](docs/SRS.md) |
| **System Analysis and Design** | |
| - Problem statement, objectives, use cases | [`docs/SRS.md`](docs/SRS.md), sections 1 & 4 |
| - Software architecture, capacity targets, component diagram, tech stack | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), sections 1, 2, 4, 13 |
| - ERD, logical and physical schema, enrichment rules | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), section 9 |
| - DFD, sequence, activity, schedule table, state, class diagrams | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), sections 3, 6–8, 10 |
| - Data sources, dynamic fetching, and per-source schedules | [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) |
| - Data quality rule catalogue and 15% safety gate | [`docs/DATA_QUALITY_RULES.md`](docs/DATA_QUALITY_RULES.md) |
| - Canonical cuisine vocabulary (130 cuisines in 15 groups) | [`docs/CUISINE_VOCABULARY.md`](docs/CUISINE_VOCABULARY.md) |
| - Secrets and non-secret configuration (`config/settings.toml`) | [`docs/SECRETS.md`](docs/SECRETS.md), [`.env.example`](.env.example) |
| - Deployment diagram, observability, API outline | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), sections 11, 12, 15 |
| - UI/UX design system and responsive/accessibility guidelines | [`docs/UI_UX.md`](docs/UI_UX.md) |
| **Implementation: source code** | `pipeline/`, `web/backend/`, `web/streamlit/`, `sql/`, `config/` |
| Coding standards and naming conventions | [`docs/CODE_STYLE.md`](docs/CODE_STYLE.md) |
| AI agent and contributor navigation guide | [`AGENTS.md`](AGENTS.md) |
| Version control, branching, collaboration | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Testing & CI quality gates | [`docs/TESTING.md`](docs/TESTING.md), [`.github/workflows/ci.yml`](.github/workflows/ci.yml) |
| Local execution runbook | [`docs/RUN_LOCAL.md`](docs/RUN_LOCAL.md) |
| Azure production deployment runbook | [`docs/DEPLOY_AZURE.md`](docs/DEPLOY_AZURE.md) |

---

## 4. Features

| # | Feature | Summary |
| --- | --- | --- |
| 1 | Multi-criteria search and filtering | Country, city, locality, canonical cuisine, cost for two (original currency + batch-pinned USD), price tier, minimum rating |
| 2 | Interactive map | Restaurants as markers (`st.map` / `st.pydeck_chart`), details on selection, paired with a tabular view |
| 3 | NLP search | Free text (and stateless multi-turn follow-ups) turned into validated `SearchParams` via a two-tier Hugging Face pipeline (`all-MiniLM-L6-v2` ONNX semantic hybrid always-on + optional `InferenceClient` LLM with 5s timeout and off-topic/location guardrails), executed as parameterized SQL |

Out of scope for now: owner accounts, B2B matching, in-app reviews, coordinate/locality imputation (see [`docs/SRS.md`](docs/SRS.md), section 9).

---

## 5. Data sources and incremental delivery

**Increment 1** delivers the end-to-end platform on the **Zomato** dataset (fetched programmatically via the Kaggle API on a `@weekly` change-checked schedule), while establishing the multi-source schema (`source_metadata`, `source_id`, `match_group_id`) for **Increment 2**.

| Source | Role | Cadence | Status |
| --- | --- | --- | --- |
| Zomato restaurant dataset (Kaggle API) | Baseline dataset (Increment 1) | `@weekly` (loads only on version/checksum change) | Decided ([`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)) |
| Additional restaurant source (Overture Maps Places, Foursquare OS Places, or OpenStreetMap) | Extra coverage, including Egypt (Increment 2) | Per-source (`@monthly` / extract-based) | **TBD** (Spike S1) |
| Geographic data (boundaries, localities) | District and locality context (Increment 2) | Manual / on provider update | **TBD** (Spike S1) |

Coverage note: the Zomato dataset (`9,551` rows, `9,052` geolocated `gold_map_points`) is concentrated in India and does not include Egypt; coverage is disclosed transparently in the UI ([`docs/UI_UX.md`](docs/UI_UX.md)).

---

## 6. Architecture at a glance

```dsconfig
Sources (Kaggle API, etc.)
  -> Check version & checksum (skip if unchanged)
  -> Bronze (append-only raw files in Azure Blob / local fallback)
  -> Clean, standardize (canonical cuisines, pinned FX USD), validate
  -> 15% quarantine safety gate -> Silver (incremental MySQL upserts) + data_quality_issues
  -> SQL transformations -> Gold (search tables, views, POINT SRID 4326 spatial index)
  -> FastAPI backend (/api/*, /api/health, /api/pipeline/status)
  -> Streamlit web app (filters, map, NLP search via web/streamlit/api_client.py)
```

Secrets arrive strictly via OS environment variables (`.env` locally, Azure Key Vault references in production), while non-secret tunables live in [`config/settings.toml`](config/settings.toml). Streamlit holds zero database credentials. Details and diagrams: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 7. Tech stack

| Layer | Technology | Priority |
| --- | --- | --- |
| Pipeline | Python 3.12+, Pandas, PyMySQL, SQL | Must |
| Database | MySQL 8.0 on Azure Database for MySQL Flexible Server (`Standard_B1ms`, TLS) | Must |
| Raw storage | Azure Blob Storage (`Standard_LRS`, local fallback in dev/CI) | Must |
| Orchestration | Azure Container Apps Scheduled Job (`@weekly` in prod); Apache Airflow 3.x (local Docker Compose) | Must |
| Backend | FastAPI | Must |
| Web presentation | Streamlit 1.67.x (Chrome, Edge, Firefox; PC & ~375 px mobile) | Must |
| NLP | Hugging Face `all-MiniLM-L6-v2` ONNX semantic hybrid (always-on, \$0) + `InferenceClient` LLM tier (5s timeout), off-topic guardrails, and multi-turn follow-up refinement | Must |
| Secrets & config | `.env` / GitHub Secrets / Azure Key Vault (RBAC + Managed Identity) + `config/settings.toml` + `constants.py` | Must |
| Hosting & CI/CD | Azure Container Apps (`WorkloadProfiles` Consumption), Azure Container Registry (`Basic`), GitHub Actions (OIDC) | Must |
| Monitoring | JSON structured logs, `/api/health`, `/api/pipeline/status`, Log Analytics | Must |

---

## 8. Repository structure

```text
/
├── README.md
├── AGENTS.md
├── CONTRIBUTING.md
├── pyproject.toml
├── docker-compose.yml
├── .env.example
├── .github/workflows/
│   ├── ci.yml                 (PR/push quality gates: ruff, mypy, pytest)
│   └── build-push-acr.yml     (OIDC build & push to Azure Container Registry)
├── config/
│   ├── settings.toml          (committed non-secret runtime settings)
│   └── cuisine_map.csv        (canonical cuisine mapping table)
├── docker/
│   └── mysql/                 (local Docker MySQL init scripts)
├── docs/
│   ├── RUN_LOCAL.md           (local Docker Compose & Python runbook)
│   ├── DEPLOY_AZURE.md        (Azure production deployment & troubleshooting runbook)
│   ├── TESTING.md             (testing strategy, quality gates, and E2E checklist)
│   ├── ARCHITECTURE.md
│   ├── CODE_STYLE.md
│   ├── CUISINE_VOCABULARY.md
│   ├── DATA_QUALITY_RULES.md
│   ├── DATA_SOURCES.md
│   ├── LITERATURE_REVIEW.md
│   ├── PROJECT_PLAN.md
│   ├── SECRETS.md
│   ├── SRS.md
│   └── UI_UX.md
├── pipeline/
│   ├── Dockerfile             (standalone ETL CLI image)
│   ├── Dockerfile.airflow     (Apache Airflow 3.x image)
│   ├── dags/                  (Airflow DAG definitions — wiring only)
│   ├── ingestion/
│   ├── transform/
│   ├── quality/
│   ├── settings.py
│   └── constants.py
├── sql/                       (numbered schema and Gold view/index scripts)
├── web/
│   ├── backend/               (FastAPI: Dockerfile, routers/, services/, repositories/, schemas/, settings.py, constants.py)
│   └── streamlit/             (Streamlit: Dockerfile, app.py, api_client.py, settings.py, constants.py, pages/, components/, .streamlit/)
└── tests/                     (pytest suite, including test_architecture.py and test_streamlit_smoke.py)
```

---

## 9. Team

| Name | Role |
| --- | --- |
| Ziad Ahmed El Shamy | TBD |
| Ali Ahmed Ali Kassem | TBD |
| Yehia Nader Ali | TBD |
| Abdulrahman Salem | TBD |
| Ahmed Hany | TBD |
| Ziad Salah ElKady | TBD |

---

## 10. Data licensing and attribution

This project uses third-party open data. Each source has its own license and attribution rules ([`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)). Verify the terms from each provider before redistributing any data. Source names and licenses are surfaced in the UI ([`docs/UI_UX.md`](docs/UI_UX.md)), and required notices will be compiled in `docs/ATTRIBUTION.md`.

## 11. License

See [`LICENSE.md`](LICENSE.md).
