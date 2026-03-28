"""Project utilities for path resolution"""
import os
from pathlib import Path


def find_project_root() -> Path:
    """Find project root by looking for src directory"""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").exists() and (parent / "src").is_dir():
            return parent
    raise RuntimeError("Project root not found - src directory missing")


# Project paths
PROJECT_ROOT = find_project_root()
SRC_DIR = PROJECT_ROOT / "src"

# OUTPUT_DIR: env var > default (PROJECT_ROOT/output)
# DB lives inside OUTPUT_DIR — no circular dependency
OUTPUT_DIR = Path(os.environ.get("OMA_OUTPUT_DIR", str(PROJECT_ROOT / "output")))
DB_PATH = OUTPUT_DIR / "oma_control.db"
REPORTS_DIR = OUTPUT_DIR / "reports"
LOGS_DIR = OUTPUT_DIR / "logs"
STRATEGY_DIR = OUTPUT_DIR / "strategy"

# XML processing folders (grouped under xmls/)
XMLS_DIR = OUTPUT_DIR / "xmls"
EXTRACT_DIR = XMLS_DIR / "extract"
TRANSFORM_DIR = XMLS_DIR / "transform"
ORIGIN_DIR = XMLS_DIR / "origin"
MERGE_DIR = XMLS_DIR / "merge"

TEST_DIR = OUTPUT_DIR / "test"

# Model configuration
# ⚠️ Prompt Caching 미지원 모델 사용 시 API 비용 5~10배 증가 주의
DEFAULT_MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
# DEFAULT_MODEL_ID = "global.anthropic.claude-sonnet-4-6"  # 캐싱 미지원 (2026-02-21)
# DEFAULT_MODEL_ID = "global.anthropic.claude-opus-4-6-v1[1m]"  # 캐싱 미지원 (2026-03-04)

# Lite model — 경량 판단용 (Facilitator, 요약 등)
DEFAULT_LITE_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


def _load_from_db(key: str) -> str | None:
    """Read a single property from the control DB, or None if unavailable."""
    if not DB_PATH.exists():
        return None
    try:
        import sqlite3
        with sqlite3.connect(str(DB_PATH), timeout=5) as conn:
            row = conn.execute("SELECT value FROM properties WHERE key=?", (key,)).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _load_model_id_by_key(env_key: str, db_key: str, default: str) -> str:
    """Load model ID: env var > DB > default"""
    env_val = os.environ.get(env_key)
    if env_val:
        return env_val
    db_val = _load_from_db(db_key)
    return db_val if db_val else default


MODEL_ID = _load_model_id_by_key("OMA_MODEL_ID", "OMA_MODEL_ID", DEFAULT_MODEL_ID)
LITE_MODEL_ID = _load_model_id_by_key("OMA_LITE_MODEL_ID", "OMA_LITE_MODEL_ID", DEFAULT_LITE_MODEL_ID)

# Reference directory
REFERENCE_DIR = SRC_DIR / "reference"

# Target DBMS configuration
_SUPPORTED_DBMS = {"postgresql", "mysql"}
_DBMS_DISPLAY_NAMES = {"postgresql": "PostgreSQL", "mysql": "MySQL"}
_DBMS_RULES_FILES = {
    "postgresql": "oracle_to_postgresql_rules.md",
    "mysql": "oracle_to_mysql_rules.md",
}


def get_target_dbms() -> str:
    """Get TARGET_DBMS_TYPE: env var > DB > default ('postgresql')"""
    env_val = os.environ.get("TARGET_DBMS_TYPE", "").lower().strip()
    if env_val in _SUPPORTED_DBMS:
        return env_val
    db_val = _load_from_db("TARGET_DBMS_TYPE")
    if db_val and db_val.lower().strip() in _SUPPORTED_DBMS:
        return db_val.lower().strip()
    return "postgresql"


def get_target_db_display_name(dbms: str | None = None) -> str:
    """Get display name for target DBMS (e.g., 'PostgreSQL', 'MySQL')"""
    dbms = dbms or get_target_dbms()
    return _DBMS_DISPLAY_NAMES.get(dbms, dbms.upper())


def load_prompt_text(prompt_path: Path, dbms: str | None = None) -> str:
    """Load prompt file and replace {{TARGET_DB}} placeholder with actual target DB name."""
    text = prompt_path.read_text(encoding="utf-8")
    display_name = get_target_db_display_name(dbms)
    return text.replace("{{TARGET_DB}}", display_name)


def get_rules_path(dbms: str | None = None) -> Path:
    """Get conversion rules file path for target DBMS"""
    dbms = dbms or get_target_dbms()
    filename = _DBMS_RULES_FILES.get(dbms, _DBMS_RULES_FILES["postgresql"])
    return REFERENCE_DIR / filename
