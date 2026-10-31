# Architecture and Design

> **Status:** Draft v0.2, a living document. Items marked **TBD** depend on spikes S1-S4 and may change. Diagrams use Mermaid and render on GitHub & local supported preview extensions.
> **Last updated:** 2026-10-30

## 1. Goals and constraints

- Reconcile several restaurant datasets into one trustworthy MySQL model hosted on Azure.
- Keep every pipeline step idempotent, observable, and re-runnable.
- Serve filters, map, and NLP search through a thin FastAPI backend.
- Keep the NLP provider swappable, with a rule-based fallback.
- Constraints: 6 students, build window about 15-30 Nov, Azure credits and cost limits, open or permitted data only (see `docs/PROJECT_PLAN.md`).

## 2. Architecture style

- **Data:** Medallion (Bronze, Silver, Gold) batch pipeline orchestrated by Apache Airflow.
- **Application:** three tiers (React presentation, FastAPI service layer, MySQL data layer) in a modular monolith backend. Microservices are unnecessary at this scale.
- **Principles:** idempotent tasks, provenance on every record, validate before load, quarantine instead of delete, configuration through environment variables, business logic kept out of DAG files.

## 3. System context (DFD Level 0)

```mermaid
flowchart LR
    SRC[("Data providers")]
    USER([End user])
    ADMIN([Admin or Data engineer])
    HF([Hugging Face Inference])
    SYS[["Restaurant Explorer Platform"]]
    SRC -->|"datasets and files"| SYS
    USER -->|"filters, map actions, text requests"| SYS
    SYS -->|"results, markers, interpreted filters"| USER
    ADMIN -->|"trigger and monitor runs"| SYS
    SYS -->|"run status, rejected records"| ADMIN
    SYS -->|"user text"| HF
    HF -->|"structured parameters"| SYS
```

## 4. Component view

```mermaid
flowchart TB
    subgraph SRC["Sources"]
        Z["Zomato dataset (baseline)"]
        O["Additional source (TBD, S1)"]
        G["Geographic data (TBD, S1)"]
    end
    subgraph PIPE["Data pipeline (Python, Pandas, SQL)"]
        ING["Ingestion"]
        BR[("Bronze: Azure Blob")]
        CLN["Clean, standardize, validate"]
        SIL[("Silver: MySQL tables")]
        QUA[("data_quality_issues")]
        GLD[("Gold: MySQL views and indexes")]
        ING --> BR
        BR --> CLN
        CLN -->|valid| SIL
        CLN -->|invalid| QUA
        SIL --> GLD
    end
    AF["Apache Airflow"]
    subgraph APP["Application"]
        WEB["React and Leaflet"]
        API["FastAPI backend"]
        NLPA["NLP adapter and rule-based fallback"]
        WEB -->|HTTPS| API
        API --> NLPA
    end
    HF(["Hugging Face Inference"])
    Z --> ING
    O --> ING
    G --> ING
    AF -.->|schedules| ING
    API --> GLD
    NLPA --> HF
```

## 5. Medallion layers

| Layer | Stored in | Contents | Rules |
| ------- | ----------- | ---------- | ------- |
| Bronze | Azure Blob Storage | Original files organized by source, ingestion date, and batch ID, plus batch metadata | Never modified; enables reprocessing |
| Silver | MySQL | Cleaned and standardized restaurants, cities, countries, localities, cuisines; quarantine table | Validated, deduplicated, standardized names |
| Gold | MySQL | Search table, aggregate views, map points, indexes | Built from Silver by SQL; optimized for the app |

## 6. Data flow (DFD Level 1: pipeline)

```mermaid
flowchart LR
    A["1. Fetch source files"] --> B["2. Store Bronze files and batch record"]
    B --> C["3. Parse and map to common schema"]
    C --> D["4. Standardize names, cuisines, currencies"]
    D --> E["5. Validate ratings, costs, coordinates"]
    E -->|pass| F["6. Upsert into Silver tables"]
    E -->|fail| H["Write to data_quality_issues"]
    F --> G["7. Refresh Gold views and indexes"]
    G --> I["8. Write pipeline_runs summary"]
    H --> I
```

| Stage | Responsibility | Idempotency approach |
| ------- | ---------------- | ---------------------- |
| Fetch and Bronze | Download or read sources; save with batch ID | Files keyed by source and batch |
| Standardize | Map each source schema to the common model | Deterministic mapping tables |
| Validate | Required fields, ranges, coordinate bounds, duplicates | Failures written, never dropped |
| Load | Upsert on a stable source key | Re-run yields the same state |
| Gold refresh | Rebuild or refresh views and indexes | Safe to repeat |
| Report | Row counts, quarantined counts by reason | One row per run |

## 7. Activity: scheduled pipeline run

```mermaid
flowchart TD
    S(["Scheduled trigger or manual run"]) --> F["Fetch source files"]
    F --> B["Write Bronze files and batch metadata"]
    B --> C["Clean and standardize"]
    C --> V{"Record valid?"}
    V -->|yes| L["Upsert into Silver"]
    V -->|no| Q["Write to data_quality_issues"]
    L --> G["Refresh Gold views and indexes"]
    Q --> G
    G --> R["Write pipeline_runs summary"]
    R --> E{"Any task failed?"}
    E -->|yes| T["Retry, then alert"]
    E -->|no| D(["Done"])
    T --> D
```

## 8. State: ingestion batch

```mermaid
stateDiagram-v2
    [*] --> Received
    Received --> Stored: raw file saved to Bronze
    Stored --> Cleaning
    Cleaning --> Loaded: all checks pass
    Cleaning --> PartiallyLoaded: some records quarantined
    Cleaning --> Failed: task error
    Failed --> Cleaning: retry
    Loaded --> [*]
    PartiallyLoaded --> [*]
```

## 9. Data model (draft ERD)

Based on the team's proposed tables. Open questions: price stored in local currency only or with a converted value, how to match the same restaurant across sources (`match_group_id`), and spatial indexing (see D-5).

```mermaid
erDiagram
    COUNTRY {
        int country_id PK
        string country_name
        string iso_code
        string currency_code
    }
    CITY {
        int city_id PK
        int country_id FK
        string city_name
    }
    LOCATION {
        int location_id PK
        int city_id FK
        string locality
    }
    RESTAURANT {
        int restaurant_id PK
        string source_restaurant_id
        int source_id FK
        int batch_id FK
        string name
        int location_id FK
        string address
        decimal latitude
        decimal longitude
        decimal avg_cost_for_two
        int price_range
        decimal rating
        int votes
        boolean has_table_booking
        boolean has_online_delivery
        int match_group_id
        datetime updated_at
    }
    CUISINE {
        int cuisine_id PK
        string cuisine_name
    }
    RESTAURANT_CUISINE {
        int restaurant_id FK
        int cuisine_id FK
    }
    SOURCE_METADATA {
        int source_id PK
        string source_name
        string license
        string url
    }
    INGESTION_BATCH {
        int batch_id PK
        int source_id FK
        int run_id FK
        string file_path
        int row_count
        string status
        datetime ingested_at
    }
    PIPELINE_RUN {
        int run_id PK
        string dag_id
        datetime started_at
        datetime ended_at
        string status
        int rows_loaded
        int rows_quarantined
    }
    DATA_QUALITY_ISSUE {
        int issue_id PK
        int batch_id FK
        int run_id FK
        string source_record_id
        string rule_name
        string reason
        string raw_payload
        datetime detected_at
    }
    COUNTRY ||--o{ CITY : has
    CITY ||--o{ LOCATION : has
    LOCATION ||--o{ RESTAURANT : contains
    RESTAURANT ||--o{ RESTAURANT_CUISINE : serves
    CUISINE ||--o{ RESTAURANT_CUISINE : classifies
    SOURCE_METADATA ||--o{ RESTAURANT : provides
    SOURCE_METADATA ||--o{ INGESTION_BATCH : supplies
    INGESTION_BATCH ||--o{ RESTAURANT : loads
    PIPELINE_RUN ||--o{ INGESTION_BATCH : executes
    INGESTION_BATCH ||--o{ DATA_QUALITY_ISSUE : produces
    PIPELINE_RUN ||--o{ DATA_QUALITY_ISSUE : logs
```

**Normalization notes:** cuisines are a many-to-many relation (the source stores them as one comma-separated field). Countries, cities, and localities are split to avoid repeating text. Currency lives with the country.

**Gold objects (planned):** `gold_restaurant_search` (denormalized, indexed), `gold_map_points`, `gold_city_cuisine_stats`, `gold_locality_cost`, `gold_rating_distribution`.

**Indexes (planned):** composite on city, price_range, and rating; index on cuisine join keys; full-text on name; latitude and longitude (or a spatial column) for map bounds.

## 10. NLP search design

**Approach:** constrained extraction. The model fills a fixed parameter object and never writes SQL.

```
SearchParams {
  country?: string
  city?: string
  locality?: string
  cuisine?: string[]
  min_rating?: number
  min_cost_for_two?: number
  max_cost_for_two?: number
  price_range?: 1..4
  needs_clarification?: string
}
```

**Components**

- **Adapter interface:** `parse(query) -> SearchParams`, with a Hugging Face implementation and a rule-based implementation.
- **Validation:** output checked against the schema and the vocabulary of known countries, cities, localities, and cuisines. Unknown values are dropped or flagged.
- **Fallback:** on timeout, error, or invalid output, use the rule-based parser.
- **Clarification:** ambiguous or unsupported requests return a question for the user.
- **Cache:** repeated queries reuse parsed results.
- **Transparency:** the UI shows the interpreted filters.

```mermaid
sequenceDiagram
    participant U as User
    participant W as React app
    participant A as FastAPI backend
    participant N as NLP adapter
    participant H as Hugging Face
    participant D as MySQL
    U->>W: "affordable Italian in Cairo, rating above 4"
    W->>A: POST /api/search/nl
    A->>N: parse(query)
    N->>H: structured-output request
    alt valid response
        H-->>N: JSON parameters
        N->>N: validate against schema and vocabulary
    else failure, timeout, or invalid
        N->>N: rule-based fallback
    end
    N-->>A: SearchParams
    A->>D: parameterized query
    D-->>A: rows
    A-->>W: results and interpreted filters
    W-->>U: list and map markers
```

**Backend classes (outline)**

```mermaid
classDiagram
    class SearchParams {
        +str country
        +str city
        +str locality
        +List~str~ cuisine
        +float min_rating
        +float max_cost_for_two
    }
    class NLPAdapter {
        <<interface>>
        +parse(query) SearchParams
    }
    class HuggingFaceAdapter {
        +parse(query) SearchParams
    }
    class RuleBasedParser {
        +parse(query) SearchParams
    }
    class SearchService {
        +search(params) List
        +search_nl(query) List
    }
    class RestaurantRepository {
        +find(params) List
        +get(restaurant_id) Restaurant
    }
    NLPAdapter <|.. HuggingFaceAdapter
    NLPAdapter <|.. RuleBasedParser
    SearchService --> NLPAdapter
    SearchService --> RestaurantRepository
```

## 11. Security

- The React app never connects to MySQL; only the backend does.
- Parameterized queries only; model output is never executed.
- Secrets (database password, Hugging Face key, Blob keys) are stored in Azure Key Vault or protected app settings, loaded from environment variables, and never committed.
- HTTPS everywhere; CORS limited to the frontend origin.
- MySQL firewall rules allow only the App Service, the Airflow host, and named developer IPs. Private networking is a Could item.
- Airflow web interface restricted to team members.
- Rate limiting on the NLP endpoint to control cost.

## 12. Deployment view

```mermaid
flowchart LR
    U([User browser])
    subgraph AZ["Microsoft Azure"]
        SWA["Static Web Apps: React"]
        APPS["App Service: FastAPI"]
        MYSQL[("Database for MySQL Flexible Server")]
        BLOB[("Blob Storage: Bronze")]
        VM["Linux VM: Apache Airflow"]
        KV["Key Vault"]
        MON["Monitor and Application Insights"]
    end
    HF([Hugging Face Inference])
    GH["GitHub and Actions"]
    U --> SWA
    SWA -->|HTTPS| APPS
    APPS --> MYSQL
    APPS --> HF
    APPS -.-> KV
    VM --> BLOB
    VM --> MYSQL
    VM -.-> KV
    APPS -.-> MON
    GH --> SWA
    GH --> APPS
```

| Azure service | Purpose | Priority |
| --------------- | --------- | ---------- |
| Database for MySQL Flexible Server | Main database | Must |
| Blob Storage | Bronze raw files | Must |
| App Service | FastAPI backend | Must |
| Static Web Apps | React frontend | Must |
| Linux VM | Airflow host | Should |
| Key Vault | Secrets | Should |
| Monitor and Application Insights | Monitoring | Could |
| Virtual Network | Private networking | Could |

If Azure access or cost blocks any Must item, the fallback is local MySQL and Docker for the demo, documented honestly (spike S4).

## 13. Technology stack

| Layer | Technology | Status |
| ------- | ------------ | -------- |
| Language | Python | Decided |
| Data processing | Pandas, SQL | Decided |
| Database | MySQL on Azure Flexible Server | Decided |
| Raw storage | Azure Blob Storage | Decided |
| Orchestration | Apache Airflow | Decided (hosting TBD, S2) |
| Backend | FastAPI | Decided |
| Frontend | React, Leaflet (JavaScript or TypeScript TBD) | Decided |
| NLP | Hugging Face Inference Providers | Decided (model TBD, S3) |
| Hosting | Static Web Apps, App Service, Linux VM | Decided (VM Should) |
| Version control | Git and GitHub | Decided |

## 14. UI/UX

Wireframes, color and typography guidelines, and accessibility notes will go in `docs/UI_UX.md` (planned). Initial screens: home with search, filters and results, map view, NLP search with interpreted filters, optional pipeline status page.

## 15. API outline (draft)

| Method and path | Purpose |
| ----------------- | --------- |
| GET `/api/restaurants` | Filtered, paginated search |
| GET `/api/restaurants/{id}` | Restaurant details |
| GET `/api/map/points` | Markers for the current filters or map bounds |
| POST `/api/search/nl` | Natural-language search |
| GET `/api/meta/countries`, `/cities`, `/cuisines` | Values for filter controls |
| GET `/api/pipeline/status` | Latest run and quality stats (Could) |

FastAPI generates interactive API documentation automatically, which can serve as the API documentation deliverable.

## 16. Open decisions

| ID | Decision | Depends on |
| ---- | ---------- | ------------ |
| D-1 | Additional source(s) | S1 |
| D-2 | Airflow hosting | S2 |
| D-3 | Hugging Face model and provider | S3 |
| D-4 | Cross-source matching method | Sprint 2 |
| D-5 | Spatial indexing in MySQL | Sprint 1 |
| D-6 | Currency handling | Sprint 1 |
| D-7 | JavaScript vs TypeScript | Sprint 0 |

## 17. Change log

| Date | Change |
|------|--------|
| 2026-10-30 | v0.1 created |
| 2026-10-30 | v0.2: medallion layers, team schema, FastAPI and React, Azure deployment; added activity, state, and class diagrams |
