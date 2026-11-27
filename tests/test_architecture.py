"""Architecture boundary and static safety guardrail tests."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PIPELINE_DIR = ROOT_DIR / "pipeline"
BACKEND_DIR = ROOT_DIR / "web" / "backend"
STREAMLIT_DIR = ROOT_DIR / "web" / "streamlit"
SQL_DIR = ROOT_DIR / "sql"

RAW_HTML_ALLOWED: set[str] = {"web/streamlit/components/card_styles.py"}
SINGLE_SETTINGS_READERS: set[Path] = {
    (PIPELINE_DIR / "settings.py").resolve(),
    (BACKEND_DIR / "settings.py").resolve(),
    (STREAMLIT_DIR / "settings.py").resolve(),
}


def _iter_python_files(base_dir: Path) -> list[Path]:
    if not base_dir.exists():
        return []
    return sorted(p for p in base_dir.rglob("*.py") if "__pycache__" not in p.parts)


def _extract_imports(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def _has_prefix(imported: set[str], forbidden: set[str]) -> list[str]:
    hits: list[str] = []
    for mod in sorted(imported):
        for prefix in forbidden:
            if mod == prefix or mod.startswith(f"{prefix}."):
                hits.append(mod)
    return hits


def test_pipeline_import_isolation() -> None:
    """Ensure pipeline modules outside dags/ never import web, API, or Airflow."""
    forbidden = {"fastapi", "streamlit", "airflow", "sqlalchemy", "web"}
    dags_dir = (PIPELINE_DIR / "dags").resolve()
    violations: list[str] = []
    for py_file in _iter_python_files(PIPELINE_DIR):
        if dags_dir in py_file.resolve().parents:
            continue
        hits = _has_prefix(_extract_imports(py_file), forbidden)
        if hits:
            violations.append(f"{py_file.relative_to(ROOT_DIR)}: {hits}")
    assert not violations, f"Forbidden pipeline imports: {violations}"


def test_dags_import_isolation() -> None:
    """Ensure Airflow DAGs never import web apps or SQLAlchemy."""
    forbidden = {"fastapi", "streamlit", "sqlalchemy", "web"}
    violations: list[str] = []
    for py_file in _iter_python_files(PIPELINE_DIR / "dags"):
        hits = _has_prefix(_extract_imports(py_file), forbidden)
        if hits:
            violations.append(f"{py_file.relative_to(ROOT_DIR)}: {hits}")
    assert not violations, f"Forbidden DAG imports: {violations}"


def test_backend_import_isolation() -> None:
    """Enforce backend import boundaries across layers."""
    forbidden_all = {"streamlit", "airflow", "sqlalchemy", "pipeline"}
    forbidden_layers = {"pymysql"}
    violations: list[str] = []
    for py_file in _iter_python_files(BACKEND_DIR):
        imported = _extract_imports(py_file)
        hits = _has_prefix(imported, forbidden_all)
        if hits:
            violations.append(f"{py_file.relative_to(ROOT_DIR)}: {hits}")
        rel = py_file.relative_to(BACKEND_DIR)
        if rel.parts and rel.parts[0] in {"routers", "services"}:
            sql_hits = _has_prefix(imported, forbidden_layers)
            if sql_hits:
                violations.append(f"{py_file.relative_to(ROOT_DIR)}: {sql_hits}")
    assert not violations, f"Forbidden backend imports: {violations}"


def test_streamlit_import_isolation() -> None:
    """Enforce Streamlit import boundaries and single HTTP client module."""
    forbidden = {"pymysql", "sqlalchemy", "pipeline", "web.backend"}
    allowed_http_file = (STREAMLIT_DIR / "api_client.py").resolve()
    violations: list[str] = []
    for py_file in _iter_python_files(STREAMLIT_DIR):
        imported = _extract_imports(py_file)
        hits = _has_prefix(imported, forbidden)
        if hits:
            violations.append(f"{py_file.relative_to(ROOT_DIR)}: {hits}")
        if py_file.resolve() != allowed_http_file:
            http_hits = _has_prefix(imported, {"httpx", "requests"})
            if http_hits:
                rel_path = py_file.relative_to(ROOT_DIR)
                violations.append(
                    f"{rel_path} must not import HTTP clients: {http_hits}"
                )
    assert not violations, f"Forbidden Streamlit imports: {violations}"


def test_streamlit_no_raw_html_or_components() -> None:
    """Block unsafe_allow_html, st.html, and streamlit.components in Streamlit code."""
    violations: list[str] = []
    for py_file in _iter_python_files(STREAMLIT_DIR):
        rel = str(py_file.relative_to(ROOT_DIR)).replace("\\", "/")
        if rel in RAW_HTML_ALLOWED:
            continue
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.keyword)
                and node.arg == "unsafe_allow_html"
                and isinstance(node.value, ast.Constant)
                and node.value.value is True
            ):
                violations.append(f"{rel}: unsafe_allow_html=True")
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "st"
                and node.attr == "html"
            ):
                violations.append(f"{rel}: st.html()")
        if "streamlit.components" in _extract_imports(py_file):
            violations.append(f"{rel}: streamlit.components import")
    assert not violations, f"Disallowed raw HTML/components: {violations}"


def test_no_st_secrets_usage() -> None:
    """Ensure st.secrets is never referenced anywhere in the codebase."""
    violations: list[str] = []
    for base in (PIPELINE_DIR, ROOT_DIR / "web"):
        for py_file in _iter_python_files(base):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "st"
                    and node.attr == "secrets"
                ):
                    violations.append(str(py_file.relative_to(ROOT_DIR)))
    assert not violations, f"Disallowed st.secrets usage: {violations}"


def test_single_settings_reader() -> None:
    """Ensure only designated settings.py modules read env vars or settings.toml."""
    violations: list[str] = []
    for base in (PIPELINE_DIR, ROOT_DIR / "web"):
        for py_file in _iter_python_files(base):
            if py_file.resolve() in SINGLE_SETTINGS_READERS:
                continue
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "os"
                    and node.attr in {"environ", "getenv"}
                ):
                    rel_path = py_file.relative_to(ROOT_DIR)
                    violations.append(f"{rel_path}: os.{node.attr}")
            if "settings.toml" in source:
                rel_path = py_file.relative_to(ROOT_DIR)
                violations.append(f"{rel_path}: settings.toml read")
    assert not violations, f"Config read outside settings.py: {violations}"


def test_sql_scripts_hygiene() -> None:
    """Ensure numbered SQL scripts exist, use LF endings, and keep ; out of comments."""
    expected = ("000_reset.sql", "001_create_tables.sql", "002_create_gold_views.sql")
    for name in expected:
        sql_path = SQL_DIR / name
        assert sql_path.is_file(), f"Missing SQL script: {sql_path}"
        raw = sql_path.read_bytes()
        assert b"\r\n" not in raw, f"CRLF detected in {name}"
        text = raw.decode("utf-8")
        for idx, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("--"):
                assert ";" not in stripped, f"Semicolon in SQL comment {name}:{idx}"
