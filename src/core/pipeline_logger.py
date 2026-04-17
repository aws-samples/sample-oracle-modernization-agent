"""Thread-safe JSON Lines logger for pipeline steps."""
import json
import time
import threading
from pathlib import Path
from utils.project_paths import LOGS_DIR


class PipelineLogger:
    """Thread-safe JSON Lines logger for pipeline steps."""

    def __init__(self, step: str):
        self._step = step
        self._lock = threading.Lock()
        self._run_dir = LOGS_DIR / step / time.strftime('%Y%m%d_%H%M%S')
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self._run_dir / 'events.jsonl'
        self.log_event('run_start')

    def log_event(self, event: str, **kwargs) -> None:
        """Thread-safe JSON event append."""
        entry = {
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'step': self._step,
            'event': event,
            **kwargs
        }
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            with open(self._log_path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')

    def log_sql_result(self, mapper: str, sql_id: str, status: str,
                       duration_ms: int = 0, **kwargs) -> None:
        """SQL-level result logging."""
        self.log_event('sql_complete',
                       mapper=mapper, sql_id=sql_id, status=status,
                       duration_ms=duration_ms, **kwargs)

    def log_summary(self, **kwargs) -> None:
        """Run completion summary."""
        self.log_event('run_summary', **kwargs)

    def generate_summary_md(self) -> Path:
        """events.jsonl -> summary.md auto-generation."""
        events = []
        with open(self._log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))

        summary_path = self._run_dir / 'summary.md'
        md = _build_summary_md(events, self._step)
        summary_path.write_text(md, encoding='utf-8')
        return summary_path

    @property
    def run_dir(self) -> Path:
        return self._run_dir

    @property
    def log_path(self) -> Path:
        return self._log_path


def _build_summary_md(events: list, step: str) -> str:
    """Build summary.md markdown from events."""
    sql_events = [e for e in events if e.get('event') == 'sql_complete']
    summary = [e for e in events if e.get('event') == 'run_summary']

    total = len(sql_events)
    passed = sum(1 for e in sql_events if e.get('status') == 'success')
    failed = sum(1 for e in sql_events if e.get('status') == 'fail')
    skipped = sum(1 for e in sql_events if e.get('status') == 'skip')

    fail_categories = {}
    for e in sql_events:
        if e.get('status') == 'fail':
            cat = e.get('fail_category', 'unknown')
            fail_categories.setdefault(cat, []).append(e)

    md = f"# {step.title()} Run Summary\n\n"
    md += f"**Run**: {events[0].get('ts', '')} | **Total**: {total} | "
    md += f"**Pass**: {passed} | **Fail**: {failed} | **Skip**: {skipped}\n\n"

    if summary:
        s = summary[-1]
        dur = s.get('duration_ms', 0)
        md += f"**Duration**: {dur // 1000}s\n\n"

    if fail_categories:
        md += "## FAIL by Category\n\n"
        md += "| Category | Count | Representative Error |\n"
        md += "|----------|:-----:|---------------------|\n"
        for cat, items in sorted(fail_categories.items(), key=lambda x: -len(x[1])):
            rep = items[0].get('error', '')[:80]
            md += f"| {cat} | {len(items)} | {rep} |\n"
        md += "\n"

    fail_events = [e for e in sql_events if e.get('status') == 'fail']
    if fail_events:
        md += "## FAIL Details\n\n"
        md += "| Mapper | SQL ID | Category | sqlState | Parameters | Error |\n"
        md += "|--------|--------|----------|:--------:|------------|-------|\n"
        for e in fail_events:
            mapper = e.get('mapper', '')
            sql_id = e.get('sql_id', '')
            cat = e.get('fail_category', '')
            sql_state = e.get('sql_state', '')
            params = json.dumps(e.get('parameters', {}), ensure_ascii=False)[:50]
            error = e.get('error', '')[:60]
            md += f"| {mapper} | {sql_id} | {cat} | {sql_state} | {params} | {error} |\n"
        md += "\n"

    fix_events = [e for e in events if e.get('event') in ('agent_fix', 're_transform')]
    if fix_events:
        md += "## Fix History\n\n"
        md += "| SQL ID | fix_version | Notes |\n"
        md += "|--------|-------------|-------|\n"
        for e in fix_events:
            md += f"| {e.get('sql_id','')} | {e.get('fix_version','')} | {e.get('notes','')} |\n"

    return md
