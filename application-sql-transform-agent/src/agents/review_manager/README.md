# ReviewManager Agent

## Purpose

ReviewManager handles SQL comparison, review, and approval workflows. It provides tools to compare Oracle and PostgreSQL SQL conversions, generate reports, and approve reviewed conversions.

## Responsibilities

- **Compare SQL conversions**: Show diffs between Oracle original and PostgreSQL converted SQL
- **Generate review reports**: Create comprehensive diff reports for manual review
- **Track review candidates**: Identify SQLs that need attention (failed validation/test, not tested)
- **Approve conversions**: Mark reviewed SQLs as approved in the database
- **Handle revisions**: Apply user-suggested improvements to converted SQL

## Tools

| Tool | Description | Use Case |
|------|-------------|----------|
| `get_review_candidates` | Get list of SQLs needing review | "Show me failed conversions" |
| `show_sql_diff` | Display diff between Oracle and PostgreSQL | "Compare selectUser conversion" |
| `generate_diff_report` | Generate comprehensive diff report | "Create conversion report" |
| `approve_conversion` | Approve a SQL conversion | "Approve this conversion" |
| `suggest_revision` | Apply user's improved SQL | "Use this better version instead" |

## Usage

### Standalone Execution

```python
from agents.review_manager.agent import create_review_manager_agent

agent = create_review_manager_agent()
result = agent("Show me all SQLs that failed validation")
```

### Through Orchestrator

The Orchestrator delegates review-related requests to ReviewManager:

```python
# User request: "Compare selectUser in UserMapper.xml"
# Orchestrator calls: delegate_to_review_manager(user_request)
# ReviewManager executes: show_sql_diff('UserMapper.xml', 'selectUser')
```

## Typical Workflows

### 1. Review Failed Conversions

```
User → "Show me failed validations"
     ↓
get_review_candidates('failed_validation')
     ↓
Show list to user
     ↓
User picks one → show_sql_diff(mapper_file, sql_id)
     ↓
User approves → approve_conversion(mapper_file, sql_id)
```

### 2. Generate Conversion Report

```
User → "Generate report for UserMapper"
     ↓
generate_diff_report('UserMapper.xml')
     ↓
Create: reports/diff_report_UserMapper.md
```

### 3. Apply Revision

```
User → "The conversion is wrong, use CONCAT instead"
     ↓
Extract revised SQL from description
     ↓
suggest_revision(mapper_file, sql_id, revised_sql, reason)
     ↓
Confirm revision applied
```

## Architecture

```
ReviewManager Agent
├── prompt.md              # Agent instructions
├── agent.py               # Agent creation
├── README.md              # This file
└── tools/
    └── diff_tools.py      # 5 review tools
```

## Integration with OMA Pipeline

ReviewManager is **independent** of the main pipeline (analyze/transform/test). It provides a **separate review layer** for manual verification:

```
Pipeline Steps:
  analyze → transform → review (multi-perspective) → validate → test → merge
                                              ↓
                                   (Optional Review Layer)
                                              ↓
                                        ReviewManager
                                         ├─ Compare
                                         ├─ Approve
                                         └─ Revise
```

## Design Decisions

### Why Separate Agent?

- **Single Responsibility**: Orchestrator controls pipeline, ReviewManager handles review
- **Reduced Complexity**: Orchestrator prompt reduced from 157 lines to ~80 lines
- **Independent Testing**: ReviewManager can be tested without running the full pipeline
- **Clearer Role**: Review operations are distinct from pipeline control

### Why Not Merge with Validate Agent?

- **Different Concerns**:
  - Validate Agent: Automated functional equivalence checks
  - ReviewManager: Human-driven manual review and approval
- **Different Timing**: Validate runs in pipeline, ReviewManager is used on-demand
- **Different Audience**: Validate is for AI, ReviewManager is for humans

## Model Configuration

- **Model**: Claude Sonnet 4.5 (via Bedrock)
- **Max Tokens**: 16000 (sufficient for SQL diffs)
- **Prompt Caching**: Enabled (caches prompt.md)

## Error Handling

All tools return structured responses:

```python
# Success
{
    'status': 'success',
    'diff': '...',
    'mapper_file': 'UserMapper.xml',
    'sql_id': 'selectUser'
}

# Error
{
    'status': 'error',
    'message': 'Not found: UserMapper.xml/selectUser'
}
```

## Future Enhancements

- [ ] Bulk approval for low-risk conversions
- [ ] Automated risk scoring (high/medium/low)
- [ ] Integration with version control (git blame for SQL history)
- [ ] Side-by-side syntax highlighting for diffs

---

**Created**: 2026-03-03
**Version**: 1.0
**Status**: Production Ready
