# SQL Validate Agent

A specialized AI agent built with the Strands Framework to validate Oracle-to-PostgreSQL SQL conversions. The agent compares original Oracle SQL with converted PostgreSQL SQL, ensuring conversion quality and functional equivalence.

## Overview

The SQL Validate Agent focuses exclusively on functional equivalence between original Oracle SQL and converted PostgreSQL SQL. Rule compliance is handled by the Review Agent's multi-perspective review (Syntax + Equivalence agents, prior step).

- Verifying semantic correctness (same input → same output)
- Detecting Oracle/PostgreSQL behavioral differences ('', NULL, implicit casting)
- Fixing functional issues automatically
- Maintaining MyBatis XML integrity
- Prerequisite: only processes SQL where `reviewed='Y'` (Review passed)

**Model**: Claude Sonnet 4.5 (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`)

## Directory Structure

```
sql_validate/
├── README.md              # This documentation
├── __init__.py           # Package initialization
├── agent.py              # Agent factory and configuration
├── prompt.md             # System prompt with validation criteria
└── tools/
    ├── __init__.py       # Tools package initialization
    └── validate_tools.py # Core validation tools
```

## Tools

### Core Validation Tools

#### `get_pending_validations()`
- **Purpose**: Retrieves SQL IDs requiring validation
- **Filter**: `reviewed='Y' AND validated='N'` (only Review-passed SQL)
- **Fallback**: `transformed='Y' AND validated='N'` if reviewed column doesn't exist
- **Returns**: `{total, mappers_count, pending: {mapper_file: [sql_objects]}}`

#### `read_transform(mapper_file, sql_id)`
- **Purpose**: Reads converted PostgreSQL SQL from transform/ directory
- **Returns**: `{sql_id, sql_type, sql_body}`
- **Extracts**: SQL content from MyBatis XML tags

#### `set_validated(mapper_file, sql_id, result, notes)`
- **Purpose**: Marks validation complete and updates database
- **Parameters**: 
  - `result`: 'PASS' or 'FAIL'
  - `notes`: Validation details
- **Updates**: `validated='Y'` with timestamp

### Reused Tools from SQL Transform Agent

#### `read_sql_source(mapper_file, sql_id)`
- **Purpose**: Reads original Oracle SQL from extract/ directory
- **Returns**: `{sql_id, sql_type, sql_body}`

#### `convert_sql(sql_id, converted_sql, mapper_file, notes)`
- **Purpose**: Saves corrected PostgreSQL conversion
- **Usage**: Called when validation fails and fixes are needed

#### `lookup_column_type(table_name, column_name)`
- **Purpose**: Retrieves column metadata for casting verification
- **Returns**: Column data type information

## PASS/FAIL Criteria

### FAIL Conditions (Functional Equivalence)

#### 1. Oracle/PostgreSQL Behavioral Differences
- Oracle '' = NULL but PostgreSQL '' ≠ NULL
- DECODE matches NULL with = but CASE WHEN needs IS NULL
- Oracle OUTER JOIN (+) + WHERE may produce different results
- Oracle implicit type conversion vs PostgreSQL explicit casting

#### 2. Semantic Correctness
- Column output differs from original intent
- Data filtering produces different rows
- JOIN relationships yield different results
- Sort order changes
- Subquery logic altered

#### 3. MyBatis XML Integrity
- Malformed XML structure
- Missing or incorrect XML tags
- Parameter binding issues

### PASS Conditions
- Functionally equivalent logic (same input → same output)
- Oracle/PG behavioral differences properly handled
- Valid MyBatis XML structure

### NOT Checked (Review Agent's responsibility)
- Oracle syntax remnants (NVL, DECODE, SYSDATE)
- General Rules compliance
- || concatenation (valid in PostgreSQL)

## Execution Flow

### 1. Initialization
```python
agent = create_sql_validate_agent()
```

### 2. Per SQL ID Validation
```
1. read_sql_source(mapper_file, sql_id)     # Get Oracle original
2. read_transform(mapper_file, sql_id)      # Get PostgreSQL conversion
3. Compare using PASS/FAIL criteria
4. If PASS: set_validated(mapper_file, sql_id, 'PASS', notes)
5. If FAIL: 
   a. convert_sql(sql_id, corrected_sql, mapper_file, notes)
   b. set_validated(mapper_file, sql_id, 'FAIL', notes)
```

### 3. Parallel Processing
- Groups SQL IDs by file size (max 30KB per group)
- Processes multiple mappers concurrently
- Real-time log monitoring with status updates

## Run Command

```bash
python3 src/run_sql_validate.py --workers 8
```

### Parameters
- `--workers`: Number of parallel workers (default: 8)

### Output
- Real-time progress logs in `logs/validate/`
- Status indicators: ✅ PASS, 🔄 FIXED, ❌ ERROR
- Final summary with validation statistics

### Example Output
```
🔍 SQL Validate Agent 시작...

🔍 Pending: 1,247 SQL IDs across 23 mappers (workers=8)
📁 Logs: /path/to/logs/validate/

  [mapper1] 🔍 group 1/3 (15 SQLs)
  [mapper1] ✅ PASS mapper1/SELECT_USER_INFO
  [mapper2] 🔄 FIXED mapper2/UPDATE_STATUS - Oracle NVL converted
  
📊 결과: 1,247/1,247 SQL IDs validated
✅ 전체 검증 완료!
```

## Key Features

- **Automated Validation**: Compares Oracle vs PostgreSQL SQL automatically
- **Intelligent Fixing**: Automatically corrects common conversion issues
- **Parallel Processing**: Handles large datasets efficiently with configurable workers
- **Real-time Monitoring**: Live progress tracking with detailed logs
- **Database Integration**: Updates validation status in SQLite database
- **Error Recovery**: Handles database locks and connection issues gracefully