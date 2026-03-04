"""Multi-perspective SQL review: Syntax + Equivalence agents run in parallel,
then a deterministic Facilitator merges results."""
import io
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock

from utils.project_paths import MODEL_ID
from agents.sql_transform.tools.load_mapper_list import read_sql_source
from agents.sql_validate.tools.validate_tools import read_transform


def _load_prompt_with_rules(prompt_filename: str) -> list:
    """Load a perspective prompt + General Rules with cache points."""
    prompt_path = Path(__file__).parent / prompt_filename
    rules_path = Path(__file__).parents[2] / "reference" / "oracle_to_postgresql_rules.md"
    return [
        SystemContentBlock(text=prompt_path.read_text(encoding="utf-8")),
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
    )


def create_equivalence_review_agent() -> Agent:
    """Create an agent focused on Oracle-to-PostgreSQL functional equivalence."""
    model = BedrockModel(model_id=MODEL_ID, max_tokens=16000)
    return Agent(
        name="EquivalenceReview",
        model=model,
        system_prompt=_load_prompt_with_rules("prompt_equivalence.md"),
        tools=[read_sql_source, read_transform],
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


# Lock to protect sys.stdout/sys.stderr redirection in multi-threaded context.
# Each perspective agent runs in its own thread — without this lock, concurrent
# stdout swaps can cause one thread to save the other's buffer as "original" stdout.
_stdio_lock = threading.Lock()


def _run_single_perspective(agent_factory, mapper_file: str, sql_ids_str: str, perspective_name: str) -> dict:
    """Run a single perspective agent and capture its JSON output."""
    buf = io.StringIO()
    with _stdio_lock:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = buf
        sys.stderr = buf
    try:
        agent = agent_factory()
        agent(
            f"Review the following SQL IDs in {mapper_file}: {sql_ids_str}\n"
            f"For each: read_sql_source for original, read_transform for converted, "
            f"then check according to your review checklist. "
            f"Output your results as the specified JSON format."
        )
    finally:
        with _stdio_lock:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    output = buf.getvalue()
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


def _facilitate(syntax_result: dict, equivalence_result: dict, sql_ids: list[str]) -> dict:
    """Deterministic facilitator: merge two perspective results into final review.

    Returns:
        {
            "overall": "PASS" or "FAIL",
            "per_sql": {
                "<sql_id>": {
                    "result": "PASS" or "FAIL",
                    "issues": [...],  # merged from both perspectives
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

    for sql_id in sql_ids:
        issues = []
        sql_result = "PASS"

        # Collect syntax issues
        if syntax_parse_error:
            issues.append("[Syntax] Review agent output could not be parsed — manual review needed")
            sql_result = "FAIL"
        else:
            syn = syntax_results.get(sql_id, {})
            if syn.get("result") == "FAIL":
                sql_result = "FAIL"
                for issue in syn.get("issues", []):
                    issues.append(f"[Syntax] {issue}")
            elif not syn:
                # Agent didn't report on this SQL ID
                issues.append(f"[Syntax] No review result returned for {sql_id}")
                sql_result = "FAIL"

        # Collect equivalence issues
        if equiv_parse_error:
            issues.append("[Equivalence] Review agent output could not be parsed — manual review needed")
            sql_result = "FAIL"
        else:
            eq = equiv_results.get(sql_id, {})
            if eq.get("result") == "FAIL":
                sql_result = "FAIL"
                for issue in eq.get("issues", []):
                    issues.append(f"[Equivalence] {issue}")
            elif not eq:
                issues.append(f"[Equivalence] No review result returned for {sql_id}")
                sql_result = "FAIL"

        if sql_result == "FAIL":
            has_any_fail = True

        # Build human-readable feedback for re-transform
        if issues:
            feedback = f"[{sql_id}] " + "; ".join(issues)
        else:
            feedback = ""

        per_sql[sql_id] = {
            "result": sql_result,
            "issues": issues,
            "feedback": feedback,
        }

    return {
        "overall": "FAIL" if has_any_fail else "PASS",
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
