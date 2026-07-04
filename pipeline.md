# Pipeline: Oracle → Target DB (PostgreSQL / MySQL)

## Steps

| # | Step | Actor | Required | Output |
|---|------|-------|----------|--------|
| 1 | analyze | oma CLI (`oma analyze`) | Yes | source_xml_list, transform_target_list, strategy draft |
| 2 | transform | Subagent (oma-transformer) | Yes | transformed SQL in DB |
| 3 | review | Subagent (oma-reviewer) | Yes | PASS/FAIL per SQL (FAIL → re-transform, max 3 rounds) |
| 4 | validate | Subagent (oma-validator) | Yes | equivalence verification |
| 5 | merge | oma CLI (`oma merge`) | Yes | output/xmls/merge/*.xml |
| 6 | test | oma CLI (`oma test-exec`) | Optional* | PASS/FAIL/SKIP per SQL |
| 7 | report | oma CLI (`oma report`) | Optional | output/reports/oma_report.html |

*Test requires Target DB connection info (configured via `oma setup`).

## Notes

- Pipeline SSOT: `.claude/skills/oma-pipeline/SKILL.md`
- State SSOT: `output/oma_control.db`
- Review is mandatory — FAIL triggers re-transform loop with feedback
- Subagent dispatch: max 5 parallel, batched by mapper (split at 15 SQLs)
