# Literature Review

> **Status:** Draft v0.3, a living document.  
> **Last updated:** 2026-10-30

## 1. Purpose and scope

This review answers three questions:

1. What products and projects already solve similar problems?
2. What data sources exist, and what are their strengths, limits, and licensing constraints?
3. What technical approaches support our pipeline: layered storage, reconciling heterogeneous sources, orchestration, and translating natural language into structured filters?

It then identifies the project’s gap and positioning.

## 2. Related work

### 2.1 Consumer place-discovery products

Large platforms such as Google Maps, Zomato, and TripAdvisor already allow users to search restaurants by location, cuisine, rating, price, and other attributes. These products rely on proprietary data, user-generated content, and continuously maintained operational infrastructure.

**Implication:** A search-only application is not a meaningful differentiator. Our contribution is the data engineering: multi-source ingestion, reconciliation, quality management, provenance, and a documented reproducible pipeline. The project demonstrates our ability to build a data product; it does not aim to compete directly with established consumer platforms.

### 2.2 Commercial location-intelligence tools

Commercial tools such as xmap.ai, Maptitude, and TargomoLOOP, along with free tools such as HorecaStore’s Restaurant Site Finder, provide competitor mapping, catchment analysis, and site-selection features for food businesses.

These products generally target business users, use proprietary methodologies, and do not expose the underlying ingestion, matching, or quality-control processes. They are useful as benchmarks for expected functionality, but not as reproducible references for pipeline design.

### 2.3 Open-source and student projects

The public GitHub project `darshilparmar/zomato-ai-data-engineering-end-to-end-project` was reviewed as prior art. It implements a Zomato-themed batch data-engineering pipeline using Amazon S3, Snowflake, dbt, Airflow, and OpenAI-based enrichment, with Streamlit-based analytics. [41](https://github.com/darshilparmar/zomato-ai-data-engineering-end-to-end-project)

The repository’s public description confirms the S3-to-Snowflake-to-dbt-to-Airflow architecture and AI enrichment workflow. [41](https://github.com/darshilparmar/zomato-ai-data-engineering-end-to-end-project) Claims that it includes RAG, text-to-SQL, generated orders, order items, or reviews should be verified directly against the repository code and README before being cited in the final version.

It shares our general food-delivery and data-engineering theme, but differs from this project in several ways:

- It is built around a Snowflake warehouse, whereas this project uses MySQL on Azure.
- It emphasizes AI analytics over a searchable map application.
- It does not address our specific goal of reconciling an India-focused ratings dataset with Egyptian open place data.
- It does not emphasize per-record source provenance, quarantine workflows, or license-aware source integration.

We cite it as prior art and do not reuse its code, data, or project name.

### 2.4 Natural-language interfaces

LLM services, including models accessible through Hugging Face Inference Providers, can extract structured fields from free-text queries. Two broad design approaches exist:

- **Constrained extraction:** Map user input to a fixed schema of allowed filters, such as cuisine, area, minimum rating, price band, and delivery availability.
- **Open-ended query generation:** Ask the model to generate SQL or another executable query language directly.

We choose constrained extraction. It reduces prompt-injection, SQL-injection, hallucinated-column, and incorrect-query risks because the model fills a validated parameter structure rather than producing executable SQL.

## 3. Data sources review

| Source | What it offers | Update pattern | License / access | Limits for our use |
| --- | --- | --- | --- | --- |
| Zomato restaurant dataset on Kaggle | Approximately 9,551 restaurants with cuisines, cost for two, currency, ratings, votes, online-delivery and table-booking flags, and coordinates | Static snapshot | CC0 1.0 / Public Domain on the specific Kaggle upload used; confirm the exact uploader, URL, version, and retrieval date | Concentrated in India; no meaningful Egypt coverage; likely data-quality issues including encoding, mixed currencies, zero ratings for unrated venues, and potentially invalid coordinates |
| Overture Maps Places | Global places with names, categories, locations, addresses, contacts, and source metadata | Periodic releases; GeoParquet distribution through cloud storage | Multi-license: Foursquare-sourced records are Apache 2.0; other records are CDLA-Permissive 2.0. Retain per-record source and license information. | No review ratings; category quality varies; `operating_status` was initially set to `"open"` for all records in the September 2025 release |
| Foursquare OS Places | Large global POI dataset with more than 100 million places and over 1,000 categories | Monthly refresh | Apache 2.0 with attribution requirements; access requires registration and is available through Foursquare’s Places portal/Iceberg catalog and an approved Hugging Face route | No ratings; access is gated rather than anonymously downloadable; attribute completeness must be validated against the current schema |
| OpenStreetMap | Community-maintained places with free-form tags including cuisine, diet, opening hours, and contact details | Continuous edits; regional extracts refreshed regularly | ODbL: attribution required, and adapted databases must generally be shared under ODbL | Tag completeness in Egypt is uneven; tags require normalization and validation |
| Administrative boundaries | District, city, and governorate polygons for spatial grouping and filtering | Occasional | Depends on provider | Accuracy, recency, and administrative hierarchy vary by provider |
| Yelp Open Dataset | Businesses, ratings, review text, and related metadata | Static release | Educational/academic use only; commercial use and public redistribution are restricted | Coverage is limited to selected U.S. and Canadian metropolitan areas; not suitable for Egypt-focused coverage |
| Commercial APIs, e.g. Google Places | Rich, current place details, reviews, photos, and operational status | Live | Provider-specific terms may restrict storage, caching, redistribution, and display | Likely incompatible with a persistent warehouse or public redistribution without careful legal review |

### 3.1 Data-source findings

1. The Zomato baseline provides ratings and restaurant attributes but has little or no Egypt coverage.
2. Overture, Foursquare, and OpenStreetMap provide Egypt coverage but do not provide comparable review ratings.
3. Combining these sources requires schema alignment, category normalization, geographic validation, and duplicate/entity resolution.
4. License obligations differ substantially: OSM imposes share-alike requirements on adapted databases, Overture requires license preservation by source, Foursquare requires attribution, and Yelp restricts academic use and redistribution.

Therefore, source reconciliation, not search itself, is the central data-engineering problem in this project.

## 4. Technical background

### 4.1 Layered medallion pipelines

The medallion architecture separates data into Bronze, Silver, and Gold layers:

- **Bronze:** Immutable raw ingested data.
- **Silver:** Cleaned, standardized, deduplicated, and validated data.
- **Gold:** Consumption-ready data for search, maps, dashboards, or applications.

This separation improves reprocessing, traceability, and quality diagnostics. It also allows raw records to remain available for audit and reprocessing when transformation rules change. A primary technical reference for medallion architecture should be added before final submission.

### 4.2 Integrating heterogeneous sources

Determining whether records from different sources describe the same real-world place is an entity-resolution or record-linkage problem. Fellegi and Sunter’s 1969 paper, *“A Theory for Record Linkage,”* provides the classic probabilistic framework for deciding whether record pairs represent matches. [[33]](https://doi.org/10.1080/01621459.1969.10501049) [[34]](https://doi.org/10.1080/01621459.1969.10501049)

In practice, restaurant matching commonly combines:

- Normalized name similarity.
- Geographic proximity.
- Address and postcode agreement.
- Category or cuisine overlap.
- Phone-number and website evidence where available.

**Decision for this project:** Begin with transparent rule-based matching, using conservative thresholds and a quarantine queue for uncertain matches. Probabilistic matching can be introduced later if labeled evaluation data becomes available.

### 4.3 Workflow orchestration

Apache Airflow represents workflows as directed acyclic graphs (DAGs) of tasks with dependencies, schedules, retries, logs, and execution metadata. Airflow supports scheduled and manually triggered DAG runs, and its retry mechanism operates at the task level. [[17]](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html) [[20]](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html) [[24]](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html)

Recommended practices for this project:

- Keep individual tasks small and focused.
- Design tasks to be idempotent, so retries do not create duplicate records or inconsistent state.
- Keep business logic in version-controlled modules rather than embedding it directly in DAG files.
- Log row counts, rejection reasons, and quarantine outcomes after each ingestion and transformation stage.

### 4.4 Geospatial serving

Map display and area-based search require valid coordinates, consistent locality mapping, and efficient spatial filtering. Key requirements include:

- Validation of latitude and longitude ranges.
- Detection of null, zeroed, swapped, or implausible coordinates.
- Mapping points to districts, cities, and governorates.
- Indexing for bounding-box and radius queries.
- Clear handling of places with missing or ambiguous locations.

**Decision for this project:** TBD; see `docs/ARCHITECTURE.md`, decision D-5.

### 4.5 Safe natural-language search

Allowing an LLM to generate executable SQL creates correctness and security risks, including invalid columns, unsafe operators, prompt injection, and unintended data exposure.

Our approach is:

1. Parse the user’s request with an LLM.
2. Require the model to return a fixed JSON filter schema.
3. Validate field names, types, ranges, and allowed values.
4. Translate validated filters into parameterized SQL.
5. Return an explicit error when the request cannot be safely interpreted.

Evaluation will use a labeled set of natural-language queries, expected filters, and expected result behavior.

## 5. Gap and positioning

Restaurant discovery is a mature consumer problem, and competitor mapping is a mature commercial problem. The remaining gap addressed by this project is not a new consumer interface, but a transparent and reproducible multi-source data pipeline.

Our contribution is:

- Layered ingestion with immutable raw data.
- Reconciliation of ratings-rich but geographically limited data with coverage-rich but rating-poor open data.
- Quarantine and data-quality tracking.
- Per-record source provenance and license tracking.
- Airflow-based orchestration.
- A constrained natural-language-to-filter interface.
- Deployment on Azure using MySQL, Blob Storage, and web application services.

We do not claim to outperform commercial location-intelligence products. We claim an auditable pipeline, documented data-quality limitations, and an honest account of source coverage and licensing constraints.

## 6. References

1. Fellegi, I. P., & Sunter, A. B. (1969). A theory for record linkage. *Journal of the American Statistical Association*, 64(328), 1183–1210. <https://doi.org/10.1080/01621459.1969.10501049> [34](https://doi.org/10.1080/01621459.1969.10501049)
2. Overture Maps Foundation. (2025, September 24). *2025-09-24 release notes.* <https://docs.overturemaps.org/blog/2025/09/24/release-notes/> [2](https://docs.overturemaps.org/blog/2025/09/24/release-notes/)
3. Foursquare. (2025, October 8). *Evolving FSQ Open Source Places.* <https://foursquare.com/resources/blog/data/evolving-fsq-open-source-places/> [4](https://foursquare.com/resources/blog/data/evolving-fsq-open-source-places/)
4. Foursquare. *FSQ OS Places dataset.* Hugging Face. <https://huggingface.co/datasets/foursquare/fsq-os-places> [5](https://huggingface.co/datasets/foursquare/fsq-os-places)
5. OpenStreetMap Foundation. *Copyright and license.* <https://www.openstreetmap.org/copyright/> [30](https://www.openstreetmap.org/copyright/)
6. Yelp. *Yelp Open Dataset — data licensing.* <https://www.yelp.com/dataset/> [46](https://www.yelp.com/dataset/)
7. Yelp. *Yelp Dataset Terms of Use.* <https://s3-media0.fl.yelpcdn.com/assets/srv0/engineering_pages/f64cb2d3efcc/assets/vendor/Dataset_User_Agreement.pdf> [45](https://s3-media0.fl.yelpcdn.com/assets/srv0/engineering_pages/f64cb2d3efcc/assets/vendor/Dataset_User_Agreement.pdf)
8. Apache Airflow. *DAGs documentation.* <https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html> [17](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html)
9. Apache Airflow. *Best practices.* <https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html> [20](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)
10. Parmar, D. *zomato-ai-data-engineering-end-to-end-project.* GitHub. <https://github.com/darshilparmar/zomato-ai-data-engineering-end-to-end-project> [41](https://github.com/darshilparmar/zomato-ai-data-engineering-end-to-end-project)
11. Kaggle. *Zomato Restaurants Dataset.* Add the exact dataset URL, uploader, version, retrieval date, and license page.
12. Vendor pages: xmap.ai, Maptitude, TargomoLOOP, and HorecaStore Restaurant Site Finder. Add retrieval dates.
13. ***TODO:*** Add 3–5 academic or technical references on entity resolution, data quality, medallion architecture, and constrained structured extraction.

## 7. Change log

| Date | Change |
| --- | --- |
| 2026-10-30 | v0.1 created |
| 2026-10-30 | v0.2: aligned to team proposal: Zomato baseline, Airflow, Hugging Face, Azure |
| 2026-10-30 | v0.3: verified source licenses and access models; corrected Foursquare access description; qualified Yelp coverage claim; clarified Zomato dataset citation requirements; strengthened related-work and positioning sections |
