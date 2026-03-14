# SQL Test Agent

The SQL Test Agent validates transformed SQL statements by executing them against a PostgreSQL database using Java MyBatis reference programs. It operates in a two-phase approach: bulk testing followed by intelligent failure resolution.

## Overview

This agent ensures SQL transformations are functionally correct by:
- Running Java MyBatis executors against transformed XML files
- Identifying and analyzing test failures
- Automatically fixing SQL syntax and logic errors
- Validating fixes through re-execution

## Directory Structure

```
sql_test/
├── README.md           # This documentation
├── agent.py           # Agent configuration and setup
├── prompt.md          # System prompt for the agent
├── tools/
│   ├── __init__.py
│   └── test_tools.py  # Core testing tools
└── __init__.py
```

## Tools

### Core Testing Tools
- **`run_bulk_test`** - Executes Java MyBatis bulk testing on all transform/ XML files
- **`run_single_test`** - Runs Java test for a specific SQL ID (creates temp directory, runs test, updates DB on success)
- **`get_test_failures`** - Retrieves SQL IDs that failed testing (validated='Y' AND tested='N')

### Reused Tools (from other agents)
- **`read_sql_source`** - Reads original SQL source from mapper files
- **`read_transform`** - Reads transformed SQL from target files
- **`convert_sql`** - Converts and fixes SQL statements
- **`lookup_column_type`** - Looks up PostgreSQL column types for validation

## 2-Phase Execution

### Phase 1: Java Bulk Test
- Generates `reference/pg_connection.properties` (PostgreSQL connection info)
- Generates `output/transform/parameters.properties` (MyBatis bind variables) if not exists
- Executes `run_postgresql.sh` against the `output/transform/` directory
- Uses Java MyBatis executors to validate all transformed SQL statements
- Filters DB connection errors (infrastructure issues) from SQL syntax errors
- Updates database flags (`tested='Y'`) for successful tests
- Collects failure information for Phase 2
- Logs to `logs/test_execution.log`

### Phase 2: Agent Fixes Failures
- Analyzes failed SQL statements using AI reasoning (SQL syntax errors only)
- Reads original source and current transform for context
- Identifies root causes (syntax errors, type mismatches, ORDER BY alias issues, etc.)
- Applies fixes using `convert_sql` tool
- Validates fixes with `run_single_test`
- Maximum 2 attempts per SQL, then marks as MANUAL_REVIEW
- Processes multiple mappers concurrently (default 8 workers)
- Logs to `logs/test/[Mapper].log` and `logs/test_progress.log`

## Java Reference Programs

The agent relies on Java MyBatis reference programs located in the `reference/` directory:

- **`run_postgresql.sh`** - Bulk test executor script
- **`MyBatisSimpleExecutor.java`** - Single SQL test executor
- **MyBatis configuration and dependencies** - Located in `reference/lib/`

These programs execute the transformed SQL against PostgreSQL to validate:
- SQL syntax correctness
- Parameter binding
- Result set compatibility
- Database connectivity

## PostgreSQL Connection

The agent requires PostgreSQL connection information through either:

### Environment Variables
```bash
export PGHOST=your-postgres-host
export PGPORT=5432
export PGDATABASE=your-database
export PGUSER=your-username
export PGPASSWORD=your-password
```

### AWS Parameter Store
Connection parameters stored under `/oma/target_postgres/*`:
- `/oma/target_postgres/host`
- `/oma/target_postgres/port`
- `/oma/target_postgres/database`
- `/oma/target_postgres/username`
- `/oma/target_postgres/password`

The agent automatically retrieves Parameter Store values if environment variables are not set.

## Run Command

Execute the SQL Test Agent using:

```bash
# Run test (continues from last state)
python3 src/run_sql_test.py --workers 8

# Reset and re-run all tests
python3 src/run_sql_test.py --reset --workers 8
```

### Parameters
- `--workers` - Number of concurrent worker threads for Phase 2 (default: 8)
- `--reset` - Reset all tested flags (tested='N') before running

### Execution Flow
1. **Setup**: Generate `pg_connection.properties` and `parameters.properties`
2. **Phase 1**: Bulk Java testing of all transformed SQL files
3. **Progress Monitoring**: Real-time log monitoring with status updates
4. **Phase 2**: Concurrent agent-based failure resolution (if failures exist)
5. **Final Report**: Summary of tested vs. total SQL statements

### Output
- **Console**: Real-time progress and status updates
- **Logs**: 
  - `logs/test_execution.log` - Full execution log
  - `logs/test_progress.log` - Real-time progress (Phase 2)
  - `logs/test/[Mapper].log` - Mapper-specific fix logs
- **Database**: Updated `tested` flags in `transform_target_list` table

### Example Output
```
🧪 SQL Test 시작...

✅ Generated /path/to/reference/pg_connection.properties
ℹ️  Using existing /path/to/output/transform/parameters.properties

Phase 1: Java 일괄 테스트 실행...
  🔧 Executing: bash run_postgresql.sh /path/to/output/transform
  📂 Working directory: /path/to/reference
  ⏱️  Timeout: 600s

  📋 Java execution log (last 50 lines):
    ...

  📊 Parsing 70 test results...
    ✅ UserMapper-01-select-selectUserList.xml:selectUserList
    ✅ OrderMapper-01-select-selectOrderList.xml:selectOrderList
    ... and 65 more passed

  📊 Test results: 70 passed, 0 failed
  ✅ Passed: 70
  ❌ Failed: 0

============================================================
📊 결과: 70/70 SQL IDs tested (select only)
  ℹ️  16 non-select SQL IDs (N/A)
✅ 전체 테스트 완료!
📁 Log: logs/test_execution.log
============================================================
```

## Dependencies

- **Strands Framework** - Agent orchestration
- **Java 8+** - MyBatis executor runtime
- **PostgreSQL** - Target database for testing
- **SQLite** - Local database for tracking test status