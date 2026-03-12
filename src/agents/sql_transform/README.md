# SQL Transform Agent

A PostgreSQL migration expert that converts Oracle SQL in MyBatis Mapper XML files to PostgreSQL using AI-powered transformation with parallel processing.

## Overview

The SQL Transform Agent automates the conversion of Oracle SQL statements to PostgreSQL within MyBatis Mapper XML files. It processes each SQL ID individually through a structured 4-phase conversion process, maintaining MyBatis dynamic SQL tags while transforming Oracle-specific syntax to PostgreSQL equivalents.

**Key Features:**
- Parallel processing by mapper file with configurable workers
- 4-phase systematic conversion rules
- MyBatis dynamic SQL preservation
- Metadata-driven parameter casting
- Comprehensive logging and reporting
- Resume capability for interrupted conversions
- Expert judgment for Oracle syntax not covered by General Rules
- SELF-CHECK before saving (Oracle remnants, parameter casting, XML escaping)

## Directory Structure

```
sql_transform/
├── README.md                 # This documentation
├── agent.py                  # Main agent configuration
├── prompt.md                 # Detailed conversion rules and instructions
├── oma_metadata.txt          # PostgreSQL metadata cache
└── tools/                    # Conversion tools
    ├── __init__.py
    ├── load_mapper_list.py    # Database operations for mapper files
    ├── split_mapper.py        # XML parsing and SQL extraction
    ├── convert_sql.py         # SQL conversion and storage
    ├── assemble_mapper.py     # Final XML assembly
    ├── save_conversion.py     # Reporting and status
    └── metadata.py            # PostgreSQL metadata extraction
```

## Tools

### Core Processing Tools

#### `load_mapper_list()`
Loads mapper file list from database (`source_xml_list` table).
- **Returns:** `{mappers: [{file_path, file_name, relative_path}]}`

#### `get_pending_transforms(sample=0)`
Gets SQL IDs where `transformed='N'` from `transform_target_list`.
- **`sample`**: If > 0, returns at most N items using representative sampling:
  1. One per sql_type (SELECT > INSERT > UPDATE > DELETE), spread across mappers
  2. Remaining slots filled by mapper round-robin
  3. If no pending items exist, picks N from all items and resets only those
- **Returns:** `{total, pending: {mapper_file: [{sql_id, sql_type, source_file, target_file}]}}`

#### `read_sql_source(mapper_file, sql_id)`
Reads the original SQL body from the extract/ file.
- **Input:** Mapper file name, SQL ID
- **Returns:** `{sql_id, sql_type, sql_body}`

#### `split_mapper(file_path)`
Splits a Mapper XML into individual SQL IDs, saves to database.
- **Input:** Full file path string
- **Returns:** `{mapper, namespace, sql_ids: [{id, type, sql, full_tag}]}`

#### `convert_sql(sql_id, converted_sql, mapper_file, notes)`
Saves conversion result to file and updates database flag (`transformed='Y'`).
- **Input:** SQL ID, converted PostgreSQL SQL, mapper file, conversion notes
- **Notes:** Use for complex conversions ("CONNECT BY converted", "MANUAL_REVIEW")

#### `assemble_mapper(mapper_file)`
Reads origin/ file, replaces SQL bodies with transform/ results, saves to merge/.
- **Input:** Mapper file name (e.g., 'SellerMapper.xml')
- **Behavior:** Only includes SQLs where `transformed='Y'`

### Metadata Tools

#### `metadata()`
Extracts PostgreSQL column metadata via psql and stores in `oma_control.db` (`pg_metadata` table).
- **Environment:** Uses `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`
- **Behavior:** Non-fatal - continues without metadata if connection fails
- **Returns:** `{status, row_count}` or `{status: 'skipped', error: '...'}`

#### `save_conversion()`
Generates final conversion report from database status.

## 4-Phase Conversion Rules Summary

The conversion process follows a strict 4-phase approach to prevent conflicts and ensure accurate transformation. Parameter casting and XML escaping rules apply throughout all phases.

### Phase 1: Structural Processing
- **Schema Removal:** `SCHEMA_NAME.TABLE_NAME` → `TABLE_NAME`
- **TABLE() Function:** `TABLE(func())` → `func()`
- **Stored Procedures:** `{call PROC()}` → `CALL PROC()`
- **Database Links:** Remove `@DBLINK` suffixes
- **Oracle Hints:** Remove all `/*+ ... */` hints
- **DUAL Table:** Remove `FROM DUAL`

### Phase 2: Syntax Conversions
- **Comma JOIN:** Convert to explicit `JOIN` syntax
- **Outer Join:** `(+)` → `LEFT/RIGHT JOIN`
- **Subquery Aliases:** Add mandatory aliases
- **Pagination:** `ROWNUM` → `LIMIT/OFFSET`

### Phase 3: Functions & Operators (40+ functions)
- **String:** `||` is valid PostgreSQL (do NOT convert to CONCAT)
- **Basic Functions:** `NVL()` → `COALESCE()`, `DECODE()` → `CASE WHEN`, `SUBSTR()` → `SUBSTRING()`, etc.
- **Date/Time:** `SYSDATE` → `CURRENT_TIMESTAMP`, `ADD_MONTHS()` → `+ INTERVAL`, `TO_DATE()` format conversion
- **Regex:** `REGEXP_LIKE` → `~`, `REGEXP_SUBSTR` → `SUBSTRING(...FROM...)`, `REGEXP_REPLACE`, `REGEXP_COUNT`
- **Sequences:** `SEQ_NAME.NEXTVAL` → `nextval('seq_name')`
- **Others:** `LENGTHB` → `OCTET_LENGTH`, `WM_CONCAT` → `STRING_AGG`, `MINUS` → `EXCEPT`

### Phase 4: Advanced Patterns
- **Hierarchical:** `CONNECT BY` → `WITH RECURSIVE`
- **MERGE:** Convert to `INSERT ... ON CONFLICT`
- **Complex Pagination:** 3-depth ROWNUM → `LIMIT/OFFSET`

### Reference Rules (applied throughout all phases)
- **Parameter Casting:** Cast parameters based on target column types using `lookup_column_type()`
- **XML Escaping:** Preserve existing CDATA and escape sequences
- **MyBatis Tags:** Preserve all dynamic SQL tags as-is

## Execution Flow

### 1. Extract Phase
- Load mapper files from database
- Split each mapper XML into individual SQL IDs
- Store SQL metadata in `transform_target_list` table
- Extract PostgreSQL metadata (optional)

### 2. Transform Phase (Parallel Processing)
- Group SQL IDs by mapper file
- Process mappers in parallel with configurable workers
- For each SQL ID:
  - Read original SQL from extract/ folder
  - Apply 4-phase conversion rules
  - Save converted SQL to transform/ folder
  - Update database status (`transformed='Y'`)

### 3. Assembly Phase
- Merge converted SQLs back into complete mapper XMLs
- Save final files to merge/ folder
- Generate conversion report

## Database Tables

### `source_xml_list`
Stores mapper file metadata:
- `file_path`: Full path to original mapper XML
- `file_name`: Mapper filename
- `relative_path`: Relative path from project root

### `transform_target_list`
Tracks conversion status for each SQL ID:
- `mapper_file`: Mapper filename
- `sql_id`: Unique SQL identifier within mapper
- `sql_type`: Type (select, insert, update, delete)
- `source_file`: Path to extracted SQL file
- `target_file`: Path to converted SQL file
- `transformed`: Status flag ('Y'/'N')

### `pg_metadata`
PostgreSQL column metadata for accurate casting:
- `table_name`: PostgreSQL table name
- `column_name`: Column name
- `data_type`: PostgreSQL data type

## Output Folders

### `origin/`
Original mapper XML files for reference.

### `extract/`
Individual SQL files extracted from mappers:
- Organized by mapper name
- One file per SQL ID
- Contains original Oracle SQL

### `transform/`
Converted PostgreSQL SQL files:
- Same structure as extract/
- Contains transformed SQL
- Only created for successfully converted SQLs

### `merge/`
Final assembled mapper XML files:
- Complete MyBatis mappers with converted SQL
- Ready for PostgreSQL deployment
- Only includes successfully transformed SQLs

## Run Command

```bash
python3 src/run_sql_transform.py --reset --workers 8
```

### Command Options

- `--reset`: Full reset - drops database tables and clears output folders
- `--workers N`: Number of parallel workers (default: 8)
- `--sample N`: Transform only N representative SQLs (0 = all)

### Execution Examples

```bash
# Full reset and conversion with 8 workers
python3 src/run_sql_transform.py --reset --workers 8

# Sample transform: 5 representative SQLs to verify strategy quality
python3 src/run_sql_transform.py --sample 5

# Resume interrupted conversion with 4 workers
python3 src/run_sql_transform.py --workers 4
```

## Model Configuration

- **Model:** Claude Sonnet 4.5 (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`)
- **Max Tokens:** 64,000
- **Prompt Caching:** Enabled for performance optimization
- **Parallel Agents:** Multiple model instances for concurrent processing

## Logging and Monitoring

### Log Structure
- **Location:** `logs/transform/`
- **Format:** One log file per mapper (`{mapper_name}.log`)
- **Real-time:** Console monitoring shows key activities

### Progress Display
- **Rich progress bar**: Real-time bar with SQL count, percentage, elapsed time
- **Result panel**: Rich panel with transformed/remaining/failed summary
- Log files per mapper in `logs/transform/`

## Error Handling

- **Non-fatal Metadata:** Continues without PostgreSQL metadata if connection fails
- **Resume Capability:** Processes only pending (`transformed='N'`) SQL IDs
- **Detailed Logging:** Individual mapper logs for troubleshooting
- **Graceful Degradation:** Skips problematic SQLs with MANUAL_REVIEW flag

## Pipeline Position

```
Transform → Review (다관점) → Validate → Test → Merge
  변환       Syntax+Equiv    의미 검증   DB 실행   XML 조립
             ↓ FAIL (구체적 피드백)
          Transform 재호출
```

After Transform, the Review Agent runs multi-perspective review (Syntax + Equivalence agents in parallel). FAIL results trigger re-transformation with specific issue feedback from both perspectives.

## Best Practices

1. **Start with Reset:** Use `--reset` for clean conversions
2. **Monitor Logs:** Watch console output for real-time progress
3. **Adjust Workers:** Reduce workers if experiencing resource constraints
4. **Review Flags:** Check for MANUAL_REVIEW flags in complex conversions
5. **Validate Results:** Test converted SQLs in PostgreSQL environment
6. **Backup Originals:** Keep original mapper files for reference