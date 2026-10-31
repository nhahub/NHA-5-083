# Global Restaurant Explorer Platform

> **Status:** Draft v0.2, a living document. We work iteratively (Agile), so items marked **TBD** are pending timeboxed spikes and may change during implementation. See `docs/PROJECT_PLAN.md` for how decisions are made.
> **Last updated:** 2026-10-30
> **Repository:** <https://github.com/nhahub/NHA-5-083>

> **Naming note:** the final name is TBD. "Global" overstates our data coverage (see section 4), and the name should not duplicate existing public projects (see `docs/LITERATURE_REVIEW.md`).

## 1. What is this?

A data engineering project that ingests restaurant data from several sources, cleans and reconciles it through Bronze, Silver, and Gold layers, stores it in a MySQL database on Microsoft Azure, and exposes it through a web app.

The data pipeline is the core of the project. The web app is the layer users interact with.

## 2. Where to find each academy deliverable

| Academy requirement | File(s) |
| --------------------- | --------- |
| **Project Planning and Management** (objectives, scope, methodology, roles, sprints, risks, change log) | [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) |
| **Literature Review** (related work, data sources review, technical background, positioning, references) | [`docs/LITERATURE_REVIEW.md`](docs/LITERATURE_REVIEW.md) |
| **Requirements Gathering** (stakeholders, user stories, use cases, functional and non-functional requirements) | [`docs/SRS.md`](docs/SRS.md) |
| **System Analysis and Design** | |
| - Problem statement and objectives | [`docs/SRS.md`](docs/SRS.md), sections 1 |
| - Use case diagram and descriptions | [`docs/SRS.md`](docs/SRS.md), section 4 |
| - Software architecture, component diagram, tech stack | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), sections 2, 4, 13 |
| - ERD, logical and physical schema | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), section 9 |
| - DFD, sequence, activity, state, class diagrams | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), sections 3, 6-8, 10 |
| - Deployment diagram, API outline | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), sections 12, 15 |
| - UI/UX wireframes and guidelines | `docs/UI_UX.md` (planned) |
| **Implementation: source code** | `pipeline/`, `api/`, `web/`, `sql/` |
| Coding standards and naming conventions | [`docs/CODE_STYLE.md`](docs/CODE_STYLE.md) |
| Version control, branching, collaboration | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Testing and validation plan | `docs/TESTING.md` (planned) |
| Deployment and execution instructions | This file, section 7 |

## 3. Features

| # | Feature | Summary |
|---|---------|---------|
| 1 | Multi-criteria search and filtering | Country, city, locality, cuisine, price range, minimum rating |
| 2 | Interactive map | Restaurants as markers (Leaflet), details on click, clustering |
| 3 | NLP search | Free text is turned into validated search parameters through a Hugging Face model, then run as parameterized SQL |

Out of scope for now: owner accounts, B2B matching, in-app reviews (see future work in `docs/SRS.md`).

## 4. Data sources

| Source | Role | Status |
| -------- | ------ | -------- |
| Zomato restaurant dataset (Kaggle) | Baseline dataset | Decided |
| Additional restaurant source (Overture Maps Places, Foursquare OS Places, or OpenStreetMap) | Extra coverage, including Egypt | **TBD** (Spike S1) |
| Geographic data (boundaries, localities) | District and locality context | **TBD** (Spike S1) |

Coverage note: the Zomato dataset is heavily concentrated in India and, as far as we know, does not include Egypt. Example queries using Cairo need an additional source. Licenses and attribution requirements are tracked in `docs/DATA_SOURCES.md` (planned) and `docs/ATTRIBUTION.md` (planned).

## 5. Architecture at a glance

```dsconfig
Sources -> Python ingestion -> Bronze (raw files in Azure Blob)
        -> Clean, standardize, validate -> Silver (MySQL tables) + quarantine table
        -> SQL transformations -> Gold (search tables, views, indexes)
        -> FastAPI backend -> React web app (filters, map, NLP search)

Apache Airflow orchestrates the pipeline. Hugging Face provides the NLP model/API.
```

Details and diagrams: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 6. Tech stack

| Layer | Technology | Priority |
| ------- | ------------ | ---------- |
| Pipeline | Python, Pandas, SQL | Must |
| Database | MySQL on Azure Database for MySQL Flexible Server | Must |
| Raw storage | Azure Blob Storage | Must |
| Orchestration | Apache Airflow (local first; Azure Linux VM if time allows) | Must (DAG), Should (VM) |
| Backend | FastAPI | Must |
| Frontend | React, Leaflet | Must |
| NLP | Hugging Face Inference Providers, with rule-based fallback | Must |
| Hosting | Azure Static Web Apps (frontend), Azure App Service (backend) | Must |
| Secrets | Azure Key Vault (or protected app settings) | Should |
| Monitoring and networking | Azure Monitor, Application Insights, Virtual Network | Could |

## 7. Getting started

> **TBD.** Completed as implementation lands. The final version must let a new person run the project from this section alone.

- **Prerequisites:** Python version, Node version, MySQL version, Docker (for local Airflow)
- **Clone:**

  ```bash
  git clone https://github.com/nhahub/NHA-5-083.git
  cd NHA-5-083
  ```

- **Configuration:** copy `.env.example` to `.env` and fill in database, Blob Storage, and Hugging Face values. Never commit `.env`.
- **Database setup:** run the scripts in `sql/` in order (TBD)
- **Run the pipeline:** TBD
- **Run the backend:** TBD
- **Run the frontend:** TBD
- **Deployed application URL:** TBD

## 8. Repository structure (proposed)

```dsconfig
/
├── README.md
├── CONTRIBUTING.md
├── .env.example
├── docs/
│   ├── PROJECT_PLAN.md
│   ├── LITERATURE_REVIEW.md
│   ├── SRS.md
│   ├── ARCHITECTURE.md
│   └── CODE_STYLE.md
├── pipeline/
│   ├── dags/          (Airflow DAG definitions only)
│   ├── ingestion/
│   ├── transform/
│   └── quality/
├── sql/               (numbered schema and transformation scripts)
├── api/               (FastAPI backend)
├── web/               (React frontend)
└── tests/
```

## 9. Team

| Name | Role |
| ------ | ------ |
| Ziad Ahmed El Shamy | TBD |
| Ali Ahmed Ali Kassem | TBD |
| Yehia Nader Ali | TBD |
| Abdulrahman Salem | TBD |
| Ahmed Hany | TBD |
| Ziad Salah ElKady | TBD |

## 10. Data licensing and attribution

This project uses third-party data. Each source has its own license and attribution rules. Verify the terms from each provider before redistributing any data. Required notices will be kept in `docs/ATTRIBUTION.md`.

## 11. License

TBD.
