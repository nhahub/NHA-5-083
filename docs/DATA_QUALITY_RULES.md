# Data Quality Rules

> **Status:** Draft v0.1, a living document. Rules are written for the Zomato source first and are extended when another source is added.
> **Last updated:** 2026-11-24

This is the catalogue of every data-quality rule the pipeline applies. Each rule name is a `snake_case` constant in code and the value written to `data_quality_issues.rule_name`. Thresholds are not hardcoded: they live in `config/settings.toml` under `[quality]` (see [`SECRETS.md`](SECRETS.md), section 3).

## 1. Severity levels

| Severity | Effect on the record | Logged to `data_quality_issues` | Counts toward the quality gate |
| --- | --- | --- | --- |
| `reject` | Not loaded into Silver; kept in quarantine with its raw payload | Yes | Yes |
| `warning` | Loaded into Silver after a documented fix (usually setting a value to `NULL`) | Yes | No |
| `transform` | Loaded; the value is standardized | No (counted in the run summary only) | No |

Batch-level failures (for example a missing column) stop the batch before any record is processed and mark the run as failed.

## 2. Quality gate

After validation and before the Silver load, the pipeline computes:

```text
quarantine_rate = rejected_records / records_read
```

- If `quarantine_rate` is greater than `max_quarantine_rate` (**0.15**, that is 15%), the gate fails: the batch is **not** loaded into Silver, Gold is **not** refreshed, the rejected records stay in quarantine for review, the run is recorded with status `quality_gate_failed`, and an alert is raised.
- Bronze files are kept, so the batch can be reprocessed after the rules or the source are fixed.
- Warnings do not count toward the rate.

## 3. Rule catalogue (Zomato)

Stages: **Ingest** (file level), **Standardize** (mapping and cleaning), **Validate** (record checks).

### 3.1 Batch-level rules

| Rule name | Stage | Check | Result |
| --- | --- | --- | --- |
| `schema_columns_missing` | Ingest | All expected source columns are present | Batch fails |
| `file_decode_failed` | Ingest | File decodes with the configured encoding | Batch fails |
| `batch_empty` | Ingest | At least one data row | Batch fails |

### 3.2 Record-level rules

| Rule name | Stage | Severity | Field(s) | Check | Config key | Reason text (example) |
| --- | --- | --- | --- | --- | --- | --- |
| `source_id_missing` | Validate | reject | `Restaurant ID` | Present and numeric | | `source restaurant id missing or not numeric` |
| `source_id_duplicate_in_batch` | Validate | reject | `Restaurant ID` | Unique within the batch (all copies rejected) | | `duplicate source restaurant id in batch` |
| `name_missing` | Validate | reject | `Restaurant Name` | Not blank after trimming | | `restaurant name missing` |
| `country_code_unknown` | Validate | reject | `Country Code` | Exists in the country lookup | | `unknown country code` |
| `city_missing` | Validate | reject | `City` | Not blank | | `city missing` |
| `rating_out_of_range` | Validate | reject | `Aggregate rating` | `NULL` or between `rating_min` and `rating_max` | `rating_min = 0.0`, `rating_max = 5.0` | `rating outside 0.0-5.0` |
| `votes_negative` | Validate | reject | `Votes` | Integer, zero or more | | `votes negative or not an integer` |
| `cost_negative` | Validate | reject | `Average Cost for two` | Zero or more | | `average cost for two negative` |
| `price_range_invalid` | Validate | reject | `Price range` | Integer between `price_range_min` and `price_range_max` | `price_range_min = 1`, `price_range_max = 4` | `price range outside 1-4` |
| `boolean_flag_invalid` | Validate | reject | `Has Table booking`, `Has Online delivery` | `Yes` or `No` | | `boolean flag not Yes or No` |
| `coordinates_missing` | Validate | warning | `Latitude`, `Longitude` | Neither value is `0` or blank | | `coordinates missing or zero; set to NULL` |
| `coordinates_out_of_range` | Validate | warning | `Latitude`, `Longitude` | Latitude within `latitude_abs_max`, longitude within `longitude_abs_max` | `latitude_abs_max = 90.0`, `longitude_abs_max = 180.0` | `coordinates out of range; set to NULL` |
| `cost_zero` | Validate | warning | `Average Cost for two` | Not `0` | | `average cost for two is zero; set to NULL` |
| `cuisine_missing` | Standardize | warning | `Cuisines` | At least one cuisine | | `no cuisine listed` |
| `cuisine_unmapped` | Standardize | warning | `Cuisines` | Label exists in the cuisine vocabulary | | `cuisine label not in vocabulary; kept as is` |
| `currency_label_mismatch` | Standardize | warning | `Currency`, `Country Code` | Label agrees with the country's ISO 4217 code | | `currency label disagrees with country; country currency used` |
| `text_mojibake_repaired` | Standardize | warning | Text fields | Known mis-encoded sequences | | `mis-encoded text repaired` |

Records with warnings about coordinates stay in Silver and remain searchable, but they are excluded from Gold map tables, which require a valid point (`CODE_STYLE.md`, section 4).

### 3.3 Standardization transforms (no issue logged)

| Transform | Rule |
| --- | --- |
| Unrated venues | Rating `0` with rating text `Not rated` becomes `NULL` (never `0`) |
| Currency | ISO 4217 code is taken from the country, not from the free-text currency label |
| USD amount | `avg_cost_for_two_usd` computed with the batch's pinned FX rate; `fx_rate` and `fx_rate_date` stored; the original amount and code are kept |
| Cuisines | Comma-separated field split, trimmed, and mapped to canonical names and groups (`CUISINE_VOCABULARY.md`) |
| Text | Trimmed, Unicode NFC-normalized |
| Booleans | `Yes` and `No` become `TRUE` and `FALSE` |
| Record hash | A hash of the standardized business fields is stored to detect unchanged records on re-load |

## 4. Reporting

- Every run writes one `pipeline_runs` row with `rows_read`, `rows_inserted`, `rows_updated`, `rows_unchanged`, `rows_quarantined`, `rows_warned`, `quarantine_rate`, and `status`.
- A per-rule breakdown (count by `rule_name` and `severity` for a run) is a query over `data_quality_issues`. It is exposed through `GET /api/pipeline/status` (Should, FR-A1).

## 5. Testing

Every rule has at least one valid and one invalid example in `tests/` (`CODE_STYLE.md`, section 9). The quality gate has tests just below and just above 15%.

## 6. Change log

| Date | Change |
| --- | --- |
| 2026-11-24 | v0.1 created: severity levels, 15% quality gate, Zomato rule catalogue, standardization transforms, per-rule reporting |
