"""Generate parameters.properties from XML bind variables + target DB metadata.

Scans transform XML files for #{param} patterns, matches against
oma_metadata.json for column types, generates type-appropriate default values.
Falls back to parameter name pattern matching when metadata unavailable.
"""
import re
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from utils.project_paths import DB_PATH, TRANSFORM_DIR, OUTPUT_DIR


_PARAM_PATTERN = re.compile(r'#\{([^},]+)')


def generate_parameters_file(output_path: str = "") -> dict:
    """Generate parameters.properties for test execution.

    Args:
        output_path: Where to write the file. Default: TRANSFORM_DIR/parameters.properties

    Returns:
        Dict with status, param_count, matched_count
    """
    if not output_path:
        output_path = str(TRANSFORM_DIR / "parameters.properties")

    # 1. Extract all #{param} from transform XMLs
    params = _extract_params_from_xmls()
    if not params:
        return {'status': 'empty', 'param_count': 0}

    # 2. Load metadata if available
    metadata = _load_metadata()

    # 3. Match params to column types and generate values
    # Priority: metadata type > SQL ::cast type > default '1'
    matched = 0
    cast_matched = 0
    param_values = {}
    for param_name in sorted(params):
        cast_type = params[param_name]  # ::type from SQL, or None

        # Try metadata match first
        col_type = _match_metadata(param_name, metadata)
        if col_type:
            param_values[param_name] = _value_from_type(col_type, param_name)
            matched += 1
        elif cast_type:
            # Use SQL ::cast type as hint
            param_values[param_name] = _value_from_cast(cast_type)
            cast_matched += 1
        else:
            param_values[param_name] = '1'

    # 4. Write parameters.properties
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w', encoding='utf-8') as f:
        f.write(f"# Auto-generated test parameters\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        default_count = len(param_values) - matched - cast_matched
        f.write(f"# Total: {len(param_values)} params (metadata: {matched}, cast: {cast_matched}, default: {default_count})\n\n")

        for name, value in sorted(param_values.items()):
            f.write(f"{name}={value}\n")

    print(f"  📝 parameters.properties: {len(param_values)}개 파라미터 (metadata: {matched})", flush=True)
    return {
        'status': 'success',
        'param_count': len(param_values),
        'matched_count': matched,
        'output_path': str(output),
    }


_PARAM_WITH_CAST = re.compile(r'#\{([^},]+?)(?:::(\w+))?\s*[},]')


def _extract_params_from_xmls() -> dict:
    """Extract #{param} names with optional ::type cast from transform XML files.

    Returns:
        Dict of {param_name: cast_type or None}
        If same param has multiple casts, last one wins.
    """
    params = {}
    if not TRANSFORM_DIR.exists():
        return params

    for xml_file in TRANSFORM_DIR.rglob("*.xml"):
        try:
            content = xml_file.read_text(encoding='utf-8')
            for match in _PARAM_WITH_CAST.finditer(content):
                param_name = match.group(1).strip()
                cast_type = match.group(2)  # None if no ::type
                # Handle nested property (item.name → item)
                if '.' in param_name:
                    param_name = param_name.split('.')[0].strip()
                if param_name and not param_name.startswith('_'):
                    # Keep cast_type if found (don't overwrite with None)
                    if param_name not in params or cast_type:
                        params[param_name] = cast_type
        except Exception:
            pass

    return params


def _load_metadata() -> dict:
    """Load target DB metadata from JSON or SQLite.

    Returns:
        Dict of {column_name_lower: data_type}
    """
    columns = {}

    # Try JSON first
    json_path = OUTPUT_DIR / "metadata" / "oma_metadata.json"
    if json_path.exists():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            for table_info in meta.values():
                for col_name, col_type in table_info.get('columns', {}).items():
                    columns[col_name.lower()] = col_type.lower()
            return columns
        except Exception:
            pass

    # Fallback: SQLite
    if DB_PATH.exists():
        try:
            with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT column_name, data_type FROM target_metadata")
                for col_name, col_type in cursor.fetchall():
                    columns[col_name.lower()] = col_type.lower()
        except Exception:
            pass

    return columns


def _match_metadata(param_name: str, metadata: dict) -> str:
    """Match parameter name to column type in metadata.

    Tries: exact match, camelCase→underscore, underscore→camelCase
    Returns data_type or empty string.
    """
    if not metadata:
        return ""

    name_lower = param_name.lower()

    # Exact match
    if name_lower in metadata:
        return metadata[name_lower]

    # camelCase → underscore (userId → user_id)
    underscore = re.sub(r'([A-Z])', r'_\1', param_name).lower().lstrip('_')
    if underscore in metadata:
        return metadata[underscore]

    # Partial match (param contains column or vice versa)
    for col_name, col_type in metadata.items():
        if len(name_lower) >= 3 and len(col_name) >= 3:
            if name_lower in col_name or col_name in name_lower:
                return col_type

    return ""


def _value_from_cast(cast_type: str) -> str:
    """Generate test value based on SQL ::cast type."""
    ct = cast_type.lower()

    if ct in ('date',):
        return '2025-01-01'
    if ct in ('timestamp', 'timestamptz'):
        return '2025-01-01 00:00:00'
    if ct in ('integer', 'int', 'int4', 'smallint', 'bigint', 'int8', 'serial'):
        return '1'
    if ct in ('numeric', 'decimal', 'double', 'float', 'real'):
        return '1'
    if ct in ('boolean', 'bool'):
        return 'true'
    # varchar, text, char — '1' works
    return '1'


def _value_from_type(data_type: str, param_name: str) -> str:
    """Generate test value based on column data type."""
    dt = data_type.lower()

    if any(t in dt for t in ['int', 'serial', 'smallint', 'bigint']):
        if 'id' in param_name.lower() or 'key' in param_name.lower() or 'seq' in param_name.lower():
            return '1'
        return '1'

    if any(t in dt for t in ['numeric', 'decimal', 'double', 'float', 'real']):
        if 'amount' in param_name.lower() or 'price' in param_name.lower():
            return '1000'
        return '1.0'

    if 'bool' in dt:
        return 'true'

    if 'timestamp' in dt:
        return '2025-01-01 00:00:00'

    if 'date' in dt:
        return '2025-01-01'

    if 'time' in dt and 'stamp' not in dt:
        return '00:00:00'

    # varchar, text, char, etc.
    name_lower = param_name.lower()
    if 'email' in name_lower:
        return 'test@example.com'
    if 'status' in name_lower:
        return 'ACTIVE'
    if 'type' in name_lower or 'cd' in name_lower or 'code' in name_lower:
        return '01'
    if 'yn' in name_lower:
        return 'Y'
    if 'name' in name_lower:
        return 'TEST'

    return 'TEST'


def _value_from_name(param_name: str) -> str:
    """Generate test value based on parameter name patterns (no metadata)."""
    lower = param_name.lower()

    # IDs and keys
    if any(p in lower for p in ['id', 'key', 'seq', 'no', 'num']):
        return '1'

    # Dates
    if any(p in lower for p in ['date', 'day', 'dt', 'ymd', 'yyyymmdd']):
        return '20250101'
    if any(p in lower for p in ['frdate', 'fromdate', 'startdate', 'frdt']):
        return '20250101'
    if any(p in lower for p in ['todate', 'enddate', 'todt']):
        return '20251231'
    if 'sysdate' in lower:
        return '20250101'

    # Numerics
    if any(p in lower for p in ['amount', 'price', 'amt']):
        return '1000'
    if any(p in lower for p in ['qty', 'cnt', 'count', 'quantity']):
        return '1'
    if any(p in lower for p in ['limit', 'size', 'pagesize']):
        return '10'
    if any(p in lower for p in ['offset', 'page']):
        return '0'
    if any(p in lower for p in ['days', 'months']):
        return '30'

    # Strings
    if 'status' in lower or 'wkstatus' in lower:
        return 'ACTIVE'
    if 'email' in lower:
        return 'test@example.com'
    if any(p in lower for p in ['yn', 'flag', 'yesno']):
        return 'Y'
    if any(p in lower for p in ['type', 'cd', 'code']):
        return '01'
    if 'name' in lower:
        return 'TEST'

    # Default
    return '1'
