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


def get_db_path() -> Path:
    """Get database path"""
    return CONFIG_DIR / "oma_control.db"


# Project paths
PROJECT_ROOT = find_project_root()
SRC_DIR = PROJECT_ROOT / "src"
CONFIG_DIR = SRC_DIR / "config"
OUTPUT_DIR = PROJECT_ROOT / "output"
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
DB_PATH = CONFIG_DIR / "oma_control.db"

# Model configuration
DEFAULT_MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
# DEFAULT_MODEL_ID = "global.anthropic.claude-sonnet-4-6"  # 프롬프트 캐싱 미지원으로 사용 금지 (2026-02-21)

def _load_model_id() -> str:
    """Load model ID: env var > DB > default"""
    env_val = os.environ.get("OMA_MODEL_ID")
    if env_val:
        return env_val
    if DB_PATH.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(DB_PATH))
            row = conn.execute("SELECT value FROM properties WHERE key='OMA_MODEL_ID'").fetchone()
            conn.close()
            if row:
                return row[0]
        except Exception:
            pass
    return DEFAULT_MODEL_ID

MODEL_ID = _load_model_id()
