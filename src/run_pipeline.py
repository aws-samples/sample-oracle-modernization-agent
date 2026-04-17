"""MD-based pipeline runner. No LLM needed — sequential step execution."""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.pipeline_logger import PipelineLogger
from core.config import load_config


def parse_pipeline_md(md_path: Path) -> list[dict]:
    """Parse pipeline.md to extract step definitions."""
    steps = []
    for line in md_path.read_text(encoding='utf-8').splitlines():
        m = re.match(r'^\d+\.\s+(\w+)\s*\|\s*(.+?)\s*\|\s*(required|optional)', line)
        if m:
            steps.append({
                'name': m.group(1),
                'command': m.group(2).strip(),
                'required': m.group(3) == 'required',
            })
    return steps


def _inject_config_args(command: str, config: dict, step_name: str) -> list[str]:
    """Inject config values into command args."""
    parts = command.split()
    step_config = config.get('pipeline', {}).get(step_name, {})
    if isinstance(step_config, dict):
        if 'workers' in step_config and '--workers' not in command:
            parts.extend(['--workers', str(step_config['workers'])])
        if 'max_rounds' in step_config and '--max-rounds' not in command:
            parts.extend(['--max-rounds', str(step_config['max_rounds'])])
    return parts


def run(step_filter: str | None = None, skip_optional: bool = False):
    """Run pipeline steps from pipeline.md."""
    config = load_config()

    pipeline_config = config.get('pipeline', {})
    md_file = pipeline_config.get('definition', 'pipeline.md')

    from utils.project_paths import PROJECT_ROOT, SRC_DIR
    md_path = PROJECT_ROOT / md_file
    if not md_path.exists():
        print(f"pipeline.md not found: {md_path}", flush=True)
        return

    steps = parse_pipeline_md(md_path)
    if not steps:
        print("No steps found in pipeline.md", flush=True)
        return

    logger = PipelineLogger(step='pipeline')
    stop_on_fail = pipeline_config.get('stop_on_fail', True)

    total_start = time.time()
    completed = 0
    failed = 0

    for step in steps:
        if step_filter and step['name'] != step_filter:
            continue
        if skip_optional and not step['required']:
            logger.log_event('step_skipped', step_name=step['name'], reason='optional')
            print(f"  Skipped: {step['name']} (optional)", flush=True)
            continue

        print(f"\n{'='*60}", flush=True)
        print(f"  Step: {step['name']} ({'required' if step['required'] else 'optional'})", flush=True)
        print(f"{'='*60}", flush=True)

        logger.log_event('step_start', step_name=step['name'], command=step['command'])
        start = time.time()

        cmd = _inject_config_args(step['command'], config, step['name'])
        env = {**os.environ, 'PYTHONPATH': str(SRC_DIR)}

        result = subprocess.run(
            [sys.executable] + cmd,
            cwd=str(SRC_DIR),
            env=env,
        )

        duration_ms = int((time.time() - start) * 1000)
        status = 'success' if result.returncode == 0 else 'fail'

        logger.log_event('step_complete', step_name=step['name'],
                         status=status, duration_ms=duration_ms,
                         returncode=result.returncode)

        if status == 'success':
            completed += 1
            print(f"  {step['name']}: completed ({duration_ms // 1000}s)", flush=True)
        else:
            failed += 1
            print(f"  {step['name']}: FAILED (exit code {result.returncode})", flush=True)
            if step['required'] and stop_on_fail:
                logger.log_event('pipeline_stopped', reason=f"{step['name']} failed")
                print(f"\n  Pipeline stopped: {step['name']} is required and failed.", flush=True)
                break

    total_ms = int((time.time() - total_start) * 1000)
    logger.log_summary(steps_completed=completed, steps_failed=failed,
                       total_steps=len(steps), duration_ms=total_ms)
    summary_path = logger.generate_summary_md()

    print(f"\n{'='*60}", flush=True)
    print(f"  Pipeline: {completed} completed, {failed} failed ({total_ms // 1000}s)", flush=True)
    print(f"  Log: {logger.log_path}", flush=True)
    print(f"  Summary: {summary_path}", flush=True)
    print(f"{'='*60}", flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='MD-based pipeline runner')
    parser.add_argument('--step', type=str, help='Run specific step only')
    parser.add_argument('--skip-optional', action='store_true', help='Skip optional steps')
    args = parser.parse_args()
    run(step_filter=args.step, skip_optional=args.skip_optional)
