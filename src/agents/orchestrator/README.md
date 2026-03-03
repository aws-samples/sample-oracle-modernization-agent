# Orchestrator Agent

The Orchestrator Agent is an interactive AI assistant that manages and controls the OMA (Oracle Migration Assistant) pipeline for Oracle to PostgreSQL database migrations. It provides a conversational interface to monitor pipeline status, execute steps, and manage the entire migration workflow.

## Overview

The Orchestrator Agent serves as the central control point for the OMA pipeline, offering:
- Real-time pipeline status monitoring
- Interactive step execution
- Automated workflow management
- Comprehensive reporting and summaries
- Conversational interface for easy operation

## Directory Structure

```
orchestrator/
├── README.md                    # This documentation
├── __init__.py                  # Package initialization
├── agent.py                     # Main agent implementation
├── prompt.md                    # Agent system prompt
├── schemas.py                   # TypedDict schemas (9 schemas)
└── tools/
    ├── __init__.py              # Tools package initialization
    └── orchestrator_tools.py    # 14 tools (uses StateManager)
```

## Tools

The Orchestrator Agent provides 14 tools for pipeline management (uses StateManager for centralized state access):

### `check_setup()`
Validates the OMA environment setup and configuration.
- Checks for `oma_control.db` database existence
- Verifies required properties (JAVA_SOURCE_FOLDER, SOURCE_DBMS_TYPE, TARGET_DBMS_TYPE)
- Validates source folder accessibility
- Returns setup status and missing components

### `check_step_status()`
Monitors current pipeline progress and determines next steps.
- Tracks completion status for each pipeline stage
- Counts processed vs. total files
- Identifies the next recommended step
- Provides detailed progress metrics

### `reset_step(step_name)`
Resets a pipeline step by clearing completion flags in DB.
- Supported steps: `transform`, `review`, `validate`, `test`
- Clears DB flags (transformed='N', reviewed='N', validated='N', tested='N')
- Allows re-running steps from scratch
- Returns reset count

### `run_step(step_name)`
Executes individual pipeline steps with real-time feedback.
- Supported steps: `analyze`, `transform`, `review`, `validate`, `test`, `merge`
- Runs corresponding Python scripts with timeout protection
- Captures output and error information
- Returns execution status and results
- For test step: returns `needs_merge=True` if SQL files were modified

### `get_summary()`
Generates comprehensive pipeline reports.
- Complete status overview
- Output file counts by category
- Generated reports and logs summary
- Overall completion status

### `search_sql_ids(keyword)`
Searches SQL IDs by keyword in mapper_file or sql_id.
- Args: keyword (e.g., "User", "Order", "select")
- Returns matching SQL IDs grouped by mapper_file
- If keyword is empty, returns first 50 SQL IDs
- Use this when user wants to test a SQL but doesn't specify exact mapper/sql_id

### `run_single_test(mapper_file, sql_id)`
Tests a single SQL against PostgreSQL database.
- Args: mapper_file (e.g., "UserMapper.xml"), sql_id (e.g., "selectUserList")
- Creates temporary directory with single XML file
- Runs Java test against PostgreSQL
- Returns: `{status: 'SUCCESS'|'FAIL', error: '...'}`
- On success: automatically updates DB (tested='Y')
- Use this for testing specific SQL after modifications

### Additional Tools

#### `transform_single_sql(mapper_file, sql_id)`
- Transforms a specific SQL using Transform Agent

#### `validate_single_sql(mapper_file, sql_id)`
- Validates a specific SQL using Validate Agent

#### `test_and_fix_single_sql(mapper_file, sql_id)`
- Tests and fixes a specific SQL using Test Agent

#### `compact_strategy()`
- Compacts the strategy file by removing duplicates

#### `regenerate_strategy()`
- Regenerates the strategy file from scratch

#### `show_progress()`
- Shows real-time progress of pipeline execution

#### `delegate_to_review_manager(user_request)`
- Delegates review-related tasks to ReviewManager Agent
- ReviewManager provides 5 tools: show_sql_diff, generate_diff_report, get_review_candidates, approve_conversion, suggest_revision

## Pipeline Steps

The OMA pipeline follows a sequential workflow:

1. **analyze** → Source code analysis and SQL extraction
2. **transform** → SQL conversion from Oracle to PostgreSQL
3. **review** → General Rules compliance check (FAIL → re-transform)
4. **validate** → Functional equivalence verification
5. **test** → Automated testing of converted SQL against PostgreSQL
6. **merge** → Final output consolidation

Each step must complete successfully before proceeding to the next stage.

## Interactive Chatbot Mode

The Orchestrator Agent operates in an interactive conversational mode, allowing natural language commands:

- **Status Queries**: "현재 상태는?", "What's the current status?"
- **Step Execution**: "다음 단계 실행해줘", "Run the next step"
- **Pipeline Control**: "transform 단계 실행", "Execute validation"
- **Reporting**: "전체 요약 보여줘", "Show me the summary"

The agent automatically checks pipeline status on startup and provides contextual guidance.

## Example Commands

### Natural Language Interactions
```bash
# Status checking
"현재 파이프라인 상태를 확인해줘"
"What's the current pipeline status?"

# Step execution
"다음 단계를 실행해줘"
"Run the transform step"
"Execute validation"

# Step reset and re-run
"변환 단계 재수행해줘"
"Reset and re-run test step"

# Single SQL testing
"User 관련 SQL 테스트해봐"
"UserMapper.xml의 selectUserList 테스트해봐"
"Test SQL with keyword Order"

# Reporting
"전체 요약을 보여줘"
"Show me the complete summary"
"How many files were processed?"

# Pipeline control
"분석 단계부터 다시 시작해줘"
"Skip to the test phase"
"Run all remaining steps"
```

### Direct Tool Usage
```bash
# Check setup
"Check if the environment is ready"

# Monitor progress
"Show me the step status"

# Execute specific steps
"Run analyze step"
"Execute merge"

# Get comprehensive report
"Generate full summary"
```

## Run Command

Start the Orchestrator Agent with:

```bash
python3 src/run_orchestrator.py
```

### Interactive Session Example
```
🎯 OMA Orchestrator
   Oracle → PostgreSQL 마이그레이션 파이프라인 제어
   'quit' 또는 'exit'로 종료

📊 Status: analyzed=True, transformed=5/10, validated=3/10, tested=0/10, merged=0
➡️  Next: transform

🧑 > 다음 단계 실행해줘

🚀 Running: transform (src/run_sql_transform.py)...
✅ transform 완료

🧑 > 전체 상태 보여줘

============================================================
📊 OMA Pipeline Summary
============================================================
  Source Analyzed: ✅
  Transformed:    10/10
  Validated:      3/10
  Tested:         0/10
  Merged:         0 files
  Output:         {'origin': 15, 'extract': 10, 'transform': 10, 'merge': 0}
  Complete:       ❌ Next: validate
============================================================

🧑 > quit
👋 종료합니다.
```

## Exit Commands

To exit the interactive session, use any of:
- `quit`
- `exit` 
- `q`
- `Ctrl+C`

The agent will gracefully terminate and display a farewell message.