"""Strategy Refine tools — add patterns, deduplicate, compact"""
import json
from pathlib import Path
from strands import tool
from utils.project_paths import PROJECT_ROOT

STRATEGY_FILE = PROJECT_ROOT / "output" / "strategy" / "transform_strategy.md"


@tool
def read_strategy() -> str:
    """Read current strategy file content.

    Returns:
        Strategy file content or error message
    """
    if not STRATEGY_FILE.exists():
        return "❌ Strategy file not found"
    return STRATEGY_FILE.read_text(encoding='utf-8')


@tool
def get_feedback_patterns(source: str = "all") -> str:
    """Collect raw fix patterns from signal files and fix_history logs.

    Args:
        source: 'validate', 'test', or 'all'

    Returns:
        JSON with raw patterns grouped by source
    """
    results = {}
    logs_dir = PROJECT_ROOT / "output" / "logs"

    # Signal files
    signal_map = {
        'validate': '.validate_signals',
        'test': '.transform_signals',
    }
    for src, fname in signal_map.items():
        if source not in ('all', src):
            continue
        sig = logs_dir / fname
        if not sig.exists():
            continue
        patterns = []
        for line in sig.read_text(encoding='utf-8').strip().split('\n'):
            parts = line.split('|')
            note = parts[-1].strip() if len(parts) >= 3 else ''
            if note and note not in patterns:
                patterns.append(note)
        if patterns:
            results[src] = patterns

    # Fix history logs
    fix_dir = logs_dir / "fix_history"
    if fix_dir.exists():
        fix_patterns = []
        for lf in sorted(fix_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
            content = lf.read_text(encoding='utf-8')
            for line in content.split('\n'):
                if line.startswith('Notes:') and line[6:].strip():
                    note = line[6:].strip()
                    if note not in fix_patterns:
                        fix_patterns.append(note)
                    break
        if fix_patterns:
            results['fix_history'] = fix_patterns

    if not results:
        return json.dumps({'status': 'empty', 'message': 'No patterns found'})
    return json.dumps({'status': 'ok', 'patterns': results}, ensure_ascii=False)


@tool
def write_strategy(content: str) -> str:
    """Overwrite the entire strategy file with new content.

    Use this after compaction or major restructuring.

    Args:
        content: Complete strategy markdown content

    Returns:
        Success message
    """
    STRATEGY_FILE.parent.mkdir(parents=True, exist_ok=True)
    STRATEGY_FILE.write_text(content, encoding='utf-8')
    size_kb = STRATEGY_FILE.stat().st_size / 1024
    return f"✅ Strategy saved ({size_kb:.1f}KB)"


@tool
def append_patterns(section: str, patterns_md: str) -> str:
    """Append formatted patterns to a specific section of the strategy file.

    Args:
        section: Section header to append to (e.g. '## 알려진 오류', '## Phase 3: Functions & Operators')
        patterns_md: Formatted markdown to append

    Returns:
        Success message
    """
    if not STRATEGY_FILE.exists():
        return "❌ Strategy file not found"

    content = STRATEGY_FILE.read_text(encoding='utf-8')

    if section not in content:
        return f"❌ Section '{section}' not found in strategy"

    # Replace placeholder or append
    placeholder = '*(없음)*' if section == '## 알려진 오류' else '*(패턴 없음)*'
    section_start = content.index(section)
    after = content[section_start + len(section):]

    # Find next ## section boundary
    next_section = after.find('\n## ')
    section_body = after[:next_section] if next_section > 0 else after

    if placeholder in section_body:
        new_body = section_body.replace(placeholder, patterns_md)
    else:
        insert_pos = next_section if next_section > 0 else len(after)
        new_body = after[:insert_pos] + '\n' + patterns_md + (after[insert_pos:] if next_section > 0 else '')
        content = content[:section_start + len(section)] + new_body
        STRATEGY_FILE.write_text(content, encoding='utf-8')
        return f"✅ Patterns appended to {section}"

    content = content[:section_start + len(section)] + new_body + (after[next_section:] if next_section > 0 else '')
    STRATEGY_FILE.write_text(content, encoding='utf-8')
    return f"✅ Patterns added to {section}"
