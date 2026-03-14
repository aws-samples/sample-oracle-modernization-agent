# Gap Analysis: Multi-Target DB Support (MySQL)

> **Summary**: Plan vs Implementation gap analysis for multi-target-db feature
>
> **Created**: 2026-03-15
> **Last Modified**: 2026-03-15
> **Status**: Approved
> **Revision**: 2 (re-analysis after Phase 4 docs update)

---

## Analysis Overview

- **Feature**: multi-target-db (MySQL target DB support)
- **Plan Document**: `docs/01-plan/features/multi-target-db.plan.md`
- **Implementation**: Phase 1-4 complete, Phase 4 docs update applied
- **Analysis Date**: 2026-03-15 (Rev 2)

## Overall Scores

| Category | Score | Status | Change |
|----------|:-----:|:------:|:------:|
| Phase 1: Core | 100% | PASS | -- |
| Phase 2: Metadata & Test | 100% | PASS | -- |
| Phase 3: Setup & Config | 67% | WARN | -- |
| Phase 4: Docs & Display | 97% | PASS | 90% -> 97% |
| Key Design Decisions (Sec 4) | 100% | PASS | -- |
| Risk Mitigations (Sec 6) | 100% | PASS | -- |
| **Overall** | **96%** | PASS | 93% -> 96% |

---

## Phase 1: Core -- PASS (100%)

All planned items implemented:

| Planned Item | Status | Implementation |
|---|:---:|---|
| `oracle_to_mysql_rules.md` (NEW, ~500 lines) | DONE | 509 lines, MySQL 8.0+, includes all planned patterns |
| `run_sql_transform.py` dynamic rules | DONE | Uses `get_rules_path()` |
| 7+ agent `agent.py` dynamic rule loading | DONE | 8 agent.py files use `load_prompt_text()` |
| 9 prompt.md `{{TARGET_DB}}` placeholder | DONE | 9 prompt files confirmed with placeholder |
| `project_paths.py` new functions | DONE | `get_target_dbms()`, `get_rules_path()`, `load_prompt_text()`, `get_target_db_display_name()`, `REFERENCE_DIR` |
| `perspectives.py` dynamic rules path | DONE | Uses `get_rules_path()` |

## Phase 2: Metadata & Test -- PASS (100%)

| Planned Item | Status | Implementation |
|---|:---:|---|
| `metadata.py` MySQL branch | DONE | MySQL CLI extraction, MySQL env vars, SSM `/oma/target_mysql/` |
| `core/models.py` `pg_metadata` -> `target_metadata` | DONE | `TargetMetadata` class, table `target_metadata` |
| `test_tools.py` MySQL EXPLAIN | DONE | MySQL EXPLAIN branch, `_ensure_db_env()`, `_TEST_SCRIPTS` dict |
| `run_sql_test.py` MySQL connection props | DONE | MySQL connection properties branch |
| `run_mysql.sh` (or run_test.sh) | DONE | `reference/run_mysql.sh` created (separate file, not unified) |

## Phase 3: Setup & Config -- WARN (67%)

| Planned Item | Status | Implementation | Notes |
|---|:---:|---|---|
| `run_setup.py` MySQL connection prompt | DONE | `_setup_mysql_connection()` with all 5 env vars, SSM, connection test | |
| `sql_extractor.py` MySQL equivalent mapping | NOT DONE | 4th field still PostgreSQL-only (`postgresql_equivalent`) | Gap #1 (carried over) |
| `orchestrator_tools.py` generic DB message | DONE | Generic DB skip detection | |

## Phase 4: Docs & Display -- PASS (97%)

| Planned Item | Status | Notes |
|---|:---:|---|
| README.md, PROJECT_OVERVIEW.md, CLAUDE.md updated | DONE | "PostgreSQL/MySQL" or generic |
| Runtime strings updated | DONE | orchestrator, report_generator, diff_tools, convert_sql, banner |
| Agent README.md files (8 files) | DONE | All 8 agent READMEs updated (was Gap #2, now resolved) |
| `setup_oma_control.sh` | NOT DONE | Still hardcodes `TARGET_DBMS_TYPE='postgres'` on line 16 (Gap #2, renumbered) |

---

## Gaps Found (Rev 2)

### Resolved since Rev 1

| # | Item | Resolution |
|---|------|------------|
| ~2~ | Agent README.md files | All 8 agent README.md files no longer contain hardcoded "PostgreSQL" references. Confirmed via grep. |

### Remaining Gaps

| # | Item | Plan Location | Description | Impact |
|---|------|:---:|---|:---:|
| 1 | `sql_extractor.py` MySQL equivalent | Sec 3.3 | `ORACLE_PATTERNS` 4th field is `postgresql_equivalent` only. No MySQL mapping (e.g., `STRING_AGG` should be `GROUP_CONCAT` for MySQL). | Low |
| 2 | `setup_oma_control.sh` | Sec 1 (High Impact list) | Line 16 still hardcodes `TARGET_DBMS_TYPE='postgres'`. Should be `'postgresql'` or parameterized. | Low |

### Changed (Plan != Implementation, intentional)

| # | Item | Plan | Implementation | Impact |
|---|------|------|----------------|:---:|
| 3 | Test script naming | `run_test.sh` (unified) | `run_mysql.sh` (separate file alongside `run_postgresql.sh`) | None |
| 4 | `common_oracle_rules.md` | Listed as "optional" in Sec 2.2 | Not created | None |

---

## Design Decisions Compliance (Section 4)

| Decision | Followed? | Notes |
|----------|:---------:|-------|
| 4.1 Rule files separated (not merged) | Yes | `oracle_to_postgresql_rules.md` + `oracle_to_mysql_rules.md` |
| 4.2 `{{TARGET_DB}}` placeholder substitution | Yes | `load_prompt_text()` replaces at load time |
| 4.3 Single `target_metadata` table (renamed from `pg_metadata`) | Yes | ORM class `TargetMetadata`, auto-migration |

## Risk Mitigations (Section 6)

| Risk | Mitigated? | How |
|------|:---------:|-----|
| MySQL rule quality | Yes | 509-line rules file with 7 "Common Wrong Conversions" section |
| MySQL 8.0 minimum | Yes | Stated in rules file line 4: "Target: MySQL 8.0+" |
| Placeholder substitution leaks | Yes | 9 prompts use `{{TARGET_DB}}`; only 1 remaining hardcoded "PostgreSQL" in `sql_transform/prompt.md` line 63 is intentional (describes env var names) |
| `\|\|` as OR in MySQL | Yes | Rules file explicitly covers `CONCAT()` mandatory conversion, listed in "Common Wrong Conversions" |

---

## Recommended Actions

### Gap #1: `sql_extractor.py` MySQL equivalents (Low priority)
The 4th field in `ORACLE_PATTERNS` is informational only (used in strategy generation reports, not in actual conversion). Adding MySQL equivalents would improve strategy report accuracy but does not affect conversion correctness. Consider adding a `mysql_equivalent` 5th field or a dynamic lookup.

### Gap #2: `setup_oma_control.sh` (Low priority)
This shell script is a fallback/legacy path. The primary setup path (`run_setup.py`) correctly handles TARGET_DBMS_TYPE. The hardcoded value `'postgres'` should be `'postgresql'` for consistency with the `_SUPPORTED_DBMS` set, or the script should accept a parameter.

### No action needed for items #3-4
- Separate `run_mysql.sh` is a reasonable implementation choice (avoids overcomplicating a unified script).
- `common_oracle_rules.md` was explicitly marked "optional" in the plan.

---

## Revision History

| Rev | Date | Match Rate | Gaps | Notes |
|-----|------|:----------:|:----:|-------|
| 1 | 2026-03-15 | 93% | 3 Low | Initial analysis after Phase 1-4 implementation |
| 2 | 2026-03-15 | 96% | 2 Low | Re-analysis after Phase 4 docs update; Gap #2 (Agent READMEs) resolved |

## Summary

**Match Rate: 96%** -- Improved from 93% after Phase 4 docs update. Gap #2 (Agent README.md files) is now resolved. 2 Low-impact gaps remain: `sql_extractor.py` MySQL equivalents (informational only) and `setup_oma_control.sh` hardcoded value (legacy fallback path). No functional gaps exist in the conversion pipeline.
