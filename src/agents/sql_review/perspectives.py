"""Multi-perspective SQL review: Syntax + Equivalence agents run in parallel,
then an LLM Facilitator merges and validates results."""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock

from utils.project_paths import MODEL_ID, LITE_MODEL_ID, get_rules_path, load_prompt_text
from agents.sql_transform.tools.load_mapper_list import read_sql_source
from agents.sql_validate.tools.validate_tools import read_transform

logger = logging.getLogger(__name__)


def _load_prompt_with_rules(prompt_filename: str) -> list:
    """Load a perspective prompt + General Rules with cache points."""
    prompt_path = Path(__file__).parent / prompt_filename
    rules_path = get_rules_path()
    return [
        SystemContentBlock(text=load_prompt_text(prompt_path)),
        SystemContentBlock(cachePoint={"type": "default"}),
        SystemContentBlock(text=rules_path.read_text(encoding="utf-8")),
        SystemContentBlock(cachePoint={"type": "default"}),
    ]


def create_syntax_review_agent() -> Agent:
    """Create an agent focused on PostgreSQL syntax rule compliance."""
    model = BedrockModel(model_id=MODEL_ID, max_tokens=16000)
    return Agent(
        name="SyntaxReview",
        model=model,
        system_prompt=_load_prompt_with_rules("prompt_syntax.md"),
        tools=[read_sql_source, read_transform],
        callback_handler=None,
    )


def create_equivalence_review_agent() -> Agent:
    """Create an agent focused on Oracle-to-PostgreSQL functional equivalence."""
    model = BedrockModel(model_id=MODEL_ID, max_tokens=16000)
    return Agent(
        name="EquivalenceReview",
        model=model,
        system_prompt=_load_prompt_with_rules("prompt_equivalence.md"),
        tools=[read_sql_source, read_transform],
        callback_handler=None,
    )


def _extract_json(text: str) -> dict | None:
    """Extract the first JSON object from agent output text."""
    # Try parsing the whole text first
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting from markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Try finding a JSON object by braces
    brace_start = text.find("{")
    if brace_start >= 0:
        depth, i = 0, brace_start
        for i, ch in enumerate(text[brace_start:], brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[brace_start : i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break

    return None


def _run_single_perspective(agent_factory, mapper_file: str, sql_ids_str: str, perspective_name: str) -> dict:
    """Run a single perspective agent and extract its JSON output.

    Uses callback_handler=None to suppress streaming output (no stdout capture needed).
    Extracts text from AgentResult via str().
    """
    agent = agent_factory()
    result = agent(
        f"Review the following SQL IDs in {mapper_file}: {sql_ids_str}\n"
        f"For each: read_sql_source for original, read_transform for converted, "
        f"then check according to your review checklist. "
        f"Output your results as the specified JSON format."
    )
    output = str(result)
    parsed = _extract_json(output)
    if parsed and "results" in parsed:
        return parsed

    # Fallback: return FAIL with raw output as context
    return {
        "perspective": perspective_name,
        "results": {},
        "_parse_error": True,
        "_raw_output": output[-2000:] if len(output) > 2000 else output,
    }


def _normalize_issue(issue) -> dict:
    """Normalize an issue entry to {severity, description} dict.

    Handles both new format (dict with severity) and legacy format (plain string).
    Legacy string issues are treated as CRITICAL for backward compatibility.
    """
    if isinstance(issue, dict) and "severity" in issue:
        return issue
    # Legacy: plain string → treat as CRITICAL
    desc = issue if isinstance(issue, str) else str(issue)
    return {"severity": "CRITICAL", "description": desc}


_FACILITATOR_PROMPT = """\
You are a SQL review facilitator. Two review agents (Syntax, Equivalence) analyzed \
Oracle SQL conversions and produced CRITICAL findings.

Your job: evaluate each CRITICAL finding and determine if the reviewer's own description \
contradicts its CRITICAL severity. This happens when a reviewer:
- Identifies a suspicious pattern, analyzes it, then concludes it's actually correct
- Marks something CRITICAL but describes it as "functionally equivalent", "same behavior", \
"redundant but harmless", "actually correct", etc.
- Reports a redundant-but-harmless pattern (e.g., casting interval to interval) as CRITICAL

For each finding, output: "CRITICAL" (genuine problem) or "WARNING" (self-contradicting / harmless).

Output ONLY a JSON array of verdicts in the same order as the input findings.
Example: ["CRITICAL", "WARNING", "CRITICAL"]
"""


def _llm_validate_criticals(critical_issues: list[dict]) -> list[str]:
    """Use lite LLM to evaluate whether CRITICAL findings are genuinely critical.

    Returns a list of verdicts: "CRITICAL" or "WARNING" for each input issue.
    Falls back to all-CRITICAL if LLM call fails.
    """
    if not critical_issues:
        return []

    findings_text = "\n".join(
        f"{i+1}. {issue['description']}"
        for i, issue in enumerate(critical_issues)
    )

    try:
        model = BedrockModel(model_id=LITE_MODEL_ID, max_tokens=500)
        agent = Agent(
            model=model,
            system_prompt=_FACILITATOR_PROMPT,
            callback_handler=None,
        )
        result = agent(f"Evaluate these CRITICAL findings:\n\n{findings_text}")
        output_text = str(result).strip()
        # Extract JSON array — try raw parse, then fence extraction
        parsed = None
        try:
            parsed = json.loads(output_text)
        except (json.JSONDecodeError, ValueError):
            fence = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", output_text, re.DOTALL)
            if fence:
                try:
                    parsed = json.loads(fence.group(1).strip())
                except (json.JSONDecodeError, ValueError):
                    pass
        if isinstance(parsed, list) and len(parsed) == len(critical_issues):
            return [v if v in ("CRITICAL", "WARNING") else "CRITICAL" for v in parsed]
    except Exception as e:
        logger.warning("Facilitator LLM call failed, keeping all CRITICALs: %s", e)

    # Fallback: keep all as CRITICAL
    return ["CRITICAL"] * len(critical_issues)


def _apply_facilitator_judgment(issues: list[dict]) -> list[dict]:
    """Filter CRITICAL issues through LLM facilitator for self-contradiction check."""
    critical_indices = [i for i, issue in enumerate(issues) if issue["severity"] == "CRITICAL"]
    if not critical_indices:
        return issues

    critical_issues = [issues[i] for i in critical_indices]
    verdicts = _llm_validate_criticals(critical_issues)

    result = list(issues)
    for idx, verdict in zip(critical_indices, verdicts):
        if verdict == "WARNING":
            result[idx] = {
                **result[idx],
                "severity": "WARNING",
                "description": result[idx]["description"] + " [facilitator: downgraded]",
            }
    return result


def _facilitate(syntax_result: dict, equivalence_result: dict, sql_ids: list[str]) -> dict:
    """Deterministic facilitator: merge two perspective results into final review.

    Severity-aware judgment:
    - CRITICAL issues → FAIL (triggers re-transform)
    - WARNING only → PASS_WITH_WARNINGS (no re-transform, warnings recorded)
    - No issues → PASS

    Returns:
        {
            "overall": "PASS" or "PASS_WITH_WARNINGS" or "FAIL",
            "per_sql": {
                "<sql_id>": {
                    "result": "PASS" or "PASS_WITH_WARNINGS" or "FAIL",
                    "issues": [...],
                    "feedback": "human-readable summary for re-transform"
                }
            }
        }
    """
    syntax_results = syntax_result.get("results", {})
    equiv_results = equivalence_result.get("results", {})

    # If JSON parsing failed for either agent, mark all as FAIL
    syntax_parse_error = syntax_result.get("_parse_error", False)
    equiv_parse_error = equivalence_result.get("_parse_error", False)

    per_sql = {}
    has_any_fail = False
    has_any_warning = False

    for sql_id in sql_ids:
        issues = []
        has_critical = False
        has_warning = False

        # Collect syntax issues
        if syntax_parse_error:
            issues.append({"severity": "CRITICAL", "description": "[Syntax] Review agent output could not be parsed — manual review needed"})
            has_critical = True
        else:
            syn = syntax_results.get(sql_id, {})
            if syn.get("result") == "FAIL":
                for issue in syn.get("issues", []):
                    normalized = _normalize_issue(issue)
                    normalized["description"] = f"[Syntax] {normalized['description']}"
                    issues.append(normalized)
                    if normalized["severity"] == "CRITICAL":
                        has_critical = True
                    else:
                        has_warning = True
            elif not syn:
                issues.append({"severity": "CRITICAL", "description": f"[Syntax] No review result returned for {sql_id}"})
                has_critical = True

        # Collect equivalence issues
        if equiv_parse_error:
            issues.append({"severity": "CRITICAL", "description": "[Equivalence] Review agent output could not be parsed — manual review needed"})
            has_critical = True
        else:
            eq = equiv_results.get(sql_id, {})
            if eq.get("result") == "FAIL":
                for issue in eq.get("issues", []):
                    normalized = _normalize_issue(issue)
                    normalized["description"] = f"[Equivalence] {normalized['description']}"
                    issues.append(normalized)
                    if normalized["severity"] == "CRITICAL":
                        has_critical = True
                    else:
                        has_warning = True
            elif not eq:
                issues.append({"severity": "CRITICAL", "description": f"[Equivalence] No review result returned for {sql_id}"})
                has_critical = True

        # LLM facilitator: validate CRITICAL findings for self-contradiction
        issues = _apply_facilitator_judgment(issues)

        # Re-evaluate severity after downgrade
        has_critical = any(i["severity"] == "CRITICAL" for i in issues)
        has_warning = any(i["severity"] == "WARNING" for i in issues)

        # Determine per-SQL result based on severity
        if has_critical:
            sql_result = "FAIL"
            has_any_fail = True
        elif has_warning:
            sql_result = "PASS_WITH_WARNINGS"
            has_any_warning = True
        else:
            sql_result = "PASS"

        # Build human-readable feedback for re-transform (CRITICAL issues only)
        if has_critical:
            critical_descs = [i["description"] for i in issues if i["severity"] == "CRITICAL"]
            feedback = f"[{sql_id}] " + "; ".join(critical_descs)
        elif issues:
            warning_descs = [i["description"] for i in issues]
            feedback = f"[{sql_id}] WARNINGS: " + "; ".join(warning_descs)
        else:
            feedback = ""

        per_sql[sql_id] = {
            "result": sql_result,
            "issues": issues,
            "feedback": feedback,
        }

    if has_any_fail:
        overall = "FAIL"
    elif has_any_warning:
        overall = "PASS_WITH_WARNINGS"
    else:
        overall = "PASS"

    return {
        "overall": overall,
        "per_sql": per_sql,
    }


def run_multi_perspective_review(mapper_file: str, sql_ids_str: str) -> dict:
    """Run Syntax and Equivalence reviews in parallel, then merge results.

    Args:
        mapper_file: Mapper file name (e.g., 'SellerMapper.xml')
        sql_ids_str: Comma-separated SQL IDs (e.g., 'selectSeller, insertSeller')

    Returns:
        Facilitated result dict with overall and per_sql results.
    """
    sql_ids = [s.strip() for s in sql_ids_str.split(",") if s.strip()]

    with ThreadPoolExecutor(max_workers=2) as executor:
        syntax_future = executor.submit(
            _run_single_perspective,
            create_syntax_review_agent,
            mapper_file,
            sql_ids_str,
            "syntax",
        )
        equiv_future = executor.submit(
            _run_single_perspective,
            create_equivalence_review_agent,
            mapper_file,
            sql_ids_str,
            "equivalence",
        )

        syntax_result = syntax_future.result()
        equiv_result = equiv_future.result()

    return _facilitate(syntax_result, equiv_result, sql_ids)
