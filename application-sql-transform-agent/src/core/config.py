"""Unified config loader. Priority: env var > yaml > DB properties."""
import os
import re
from pathlib import Path

_config_cache = None


def load_config(config_path: Path | None = None) -> dict:
    """Load oma-config.yaml with env var override.

    Priority: env var > yaml > DB properties (existing compat).
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    config: dict = {}

    if config_path is None:
        from utils.project_paths import PROJECT_ROOT
        config_path = PROJECT_ROOT / 'oma-config.yaml'

    if config_path.exists():
        try:
            import yaml
        except ImportError:
            yaml = None
        if yaml:
            with open(config_path, encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}

    config = _resolve_env_vars(config)

    # env var overrides (backward compat with existing env vars)
    if os.environ.get('OMA_OUTPUT_DIR'):
        config.setdefault('project', {})['output_dir'] = os.environ['OMA_OUTPUT_DIR']
    if os.environ.get('TARGET_DBMS_TYPE'):
        config.setdefault('project', {})['target_dbms'] = os.environ['TARGET_DBMS_TYPE']
    if os.environ.get('OMA_MODEL_ID'):
        config.setdefault('project', {})['model_id'] = os.environ['OMA_MODEL_ID']

    _config_cache = config
    return config


def get_pipeline_config(step: str) -> dict:
    """Get config for a specific pipeline step."""
    config = load_config()
    pipeline = config.get('pipeline', {})
    step_config = pipeline.get(step, {})
    if isinstance(step_config, dict):
        return step_config
    return {}


def get_db_config() -> dict:
    """Get database connection config."""
    config = load_config()
    return config.get('database', {})


def reset_cache():
    """Reset config cache (for testing or config reload)."""
    global _config_cache
    _config_cache = None


def _resolve_env_vars(obj):
    """Recursively replace ${VAR} with os.environ[VAR]."""
    if isinstance(obj, str):
        return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), obj)
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_vars(v) for v in obj]
    return obj
