# Code Style Guide

## 1. Principles

1. **Readable over clever.** Someone else will read this at 2 a.m (maybe, maybe not).
2. **Consistent.** Follow the rules here, even where you prefer another style.
3. **Automated.** Formatters and linters enforce style; reviews focus on logic.
4. **Safe by default.** Parameterized SQL, no secrets in code, validated inputs.
5. **Re-runnable.** Pipeline code must be idempotent.

## 2. General rules

- Language for code, comments, and commits: English.
- Files use UTF-8, LF line endings, a final newline, and no trailing whitespace (enforced by `.editorconfig`).
- Comments explain *why*, not *what*. Delete commented-out code.
- No magic numbers or strings: use named constants or config.
- TODO comments include an owner or issue: `# TODO(#42): handle currency conversion`.
- Keep functions short and single-purpose. If a function needs a long comment to explain it, split it.

## 3. Python (pipeline and FastAPI)

**Tools:** Ruff for linting and formatting (replaces Black, isort, and flake8), pytest for tests.

| Topic | Rule |
| ------- | ------ |
| Style | PEP 8; line length 88 |
| Types | Type hints on all function signatures |
| Docstrings | Google style for public functions and classes (purpose, args, returns, raises) |
| Imports | Standard library, third party, local; sorted by Ruff; no wildcard imports |
| Logging | Use the `logging` module with module-level loggers; no `print` in committed code |
| Errors | Raise specific exceptions; never use a bare `except:`; log with context, then re-raise or handle |
| Config | Read from environment variables through one settings module; never hardcode credentials |
| Paths | Use `pathlib.Path`, not string concatenation |
| Pandas | Prefer vectorized operations; no chained assignment; name intermediate DataFrames clearly (`raw_df`, `clean_df`) |
| FastAPI | Pydantic models for request and response schemas; routers per resource; dependencies for DB sessions; return proper status codes |

**Example**

```python
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

MIN_RATING = 0.0
MAX_RATING = 5.0


def split_valid_ratings(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split rows into valid and invalid ratings.

    Args:
        df: Restaurants with a numeric `rating` column.

    Returns:
        A tuple of (valid_rows, invalid_rows).
    """
    is_valid = df["rating"].between(MIN_RATING, MAX_RATING)
    logger.info("Rating check: %d valid, %d invalid", is_valid.sum(), (~is_valid).sum())
    return df[is_valid], df[~is_valid]
```

## 4. SQL (MySQL)

| Topic | Rule |
| ------- | ------ |
| Keywords | UPPERCASE (`SELECT`, `JOIN`, `WHERE`) |
| Names | `snake_case`; tables plural (`restaurants`, `cities`); columns singular |
| Keys | Primary key `<table_singular>_id`; foreign keys use the same name as the referenced key |
| Gold objects | Prefix `gold_` for views and tables built for the app |
| Indexes | `idx_<table>_<columns>`; unique indexes `uq_<table>_<columns>` |
| Joins | Explicit `JOIN ... ON`; never implicit comma joins |
| Selecting | List columns explicitly; avoid `SELECT *` in application and Gold code |
| Layout | One clause per line, indented joins and conditions |
| Safety | Application code uses parameterized queries only; never build SQL by string formatting |
| Scripts | Numbered, re-runnable files in `sql/` (for example `001_create_tables.sql`, `002_create_gold_views.sql`); use `CREATE ... IF NOT EXISTS` and clear comments |

**Example**

```sql
SELECT
    r.restaurant_id,
    r.name,
    r.rating,
    c.city_name
FROM restaurants AS r
JOIN locations AS l ON l.location_id = r.location_id
JOIN cities AS c ON c.city_id = l.city_id
WHERE c.city_name = %(city)s
  AND r.rating >= %(min_rating)s
ORDER BY r.rating DESC
LIMIT %(limit)s;
```

## 5. JavaScript / TypeScript (React)

**Tools:** ESLint and Prettier. TypeScript is preferred (decision D-7); if we use JavaScript, keep the same naming rules.

| Topic | Rule |
| ------- | ------ |
| Formatting | Prettier: 2 spaces, single quotes, semicolons, trailing commas |
| Components | Function components with hooks; one component per file; `PascalCase` file and component names |
| Hooks | Custom hooks start with `use` (`useRestaurantSearch`) |
| Variables and functions | `camelCase`; constants `UPPER_SNAKE_CASE`; booleans start with `is`, `has`, or `should` |
| Types | Explicit prop and API response types; avoid `any` |
| State | Keep it local when possible; lift state only when shared |
| API calls | Centralized in an `api/` module; base URL from environment variable; handle loading and error states |
| Security | Never call the database from the browser; never place secrets in frontend code |
| Accessibility | Labels on inputs, alt text on images, keyboard-reachable controls |
| Styling | One approach for the project (decide in Sprint 0); no inline styles except for dynamic values |

## 6. Airflow DAGs

- DAG files only wire tasks together; business logic lives in `pipeline/` modules that DAGs import.
- `dag_id` in `snake_case` with a purpose (`restaurants_daily_etl`); tasks named by verb (`ingest_zomato`, `validate_silver`).
- Every task is idempotent: running it twice gives the same result.
- Set explicit `retries`, `retry_delay`, `catchup=False` (unless backfills are intended), and tags.
- No secrets in DAG files; use Airflow connections or environment variables.
- No heavy work at DAG parse time (no network or database calls at module level).

## 7. Naming conventions summary

| Item | Convention | Example |
| ------ | ----------- | --------- |
| Python files and functions | `snake_case` | `clean_restaurants.py`, `load_silver()` |
| Python classes | `PascalCase` | `SearchService` |
| Python constants | `UPPER_SNAKE_CASE` | `MAX_RATING` |
| SQL tables and columns | `snake_case` | `restaurant_cuisines` |
| React components | `PascalCase` | `RestaurantCard.tsx` |
| JS variables | `camelCase` | `selectedCity` |
| Branches | `type/area-description` | `feat/api-nl-search` |
| Env variables | `UPPER_SNAKE_CASE` | `MYSQL_HOST` |
| Airflow DAGs | `snake_case` | `restaurants_daily_etl` |

## 8. Testing conventions

- Python: pytest; files `test_<module>.py`; functions `test_<behavior>`; use small fixtures instead of real datasets.
- Test data-quality rules with both valid and invalid examples.
- Test the NLP layer with a fixed set of sample queries and expected parameters, including failures.
- Frontend: tests for key components and the API module (tool TBD).
- A bug fix includes a test that fails before the fix.

## 9. Security checklist

- [ ] No secrets, tokens, or `.env` in the repository
- [ ] All SQL parameterized
- [ ] Inputs validated at the API boundary
- [ ] Model output validated and never executed
- [ ] CORS and HTTPS configured
- [ ] Dependencies pinned (`requirements.txt` or lock file, `package-lock.json`)

## 10. Tooling configuration

**[`pyproject.toml`](./pyproject.toml)**, **[`.editorconfig`](./.editorconfig)**, **[`.prettierrc`](./.prettierrc.json)**, **[`.pre-commit-config.yaml`](./.pre-commit-config.yaml)**

## 11. Change log

| Date       | Change                                |
|------      |--------                               |
| 2026-10-30 | v0.2 created as an adoptable template |
