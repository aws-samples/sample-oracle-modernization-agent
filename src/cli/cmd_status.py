"""oma status — pipeline step counts (StateManager wrapper)"""
import json
import sys


def register(sub):
    p = sub.add_parser("status", help="Show pipeline step counts")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.set_defaults(func=run)


def run(args) -> int:
    from utils.project_paths import DB_PATH
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH} — run 'oma setup' first", file=sys.stderr)
        return 1
    from core.state_manager import StateManager
    counts = StateManager(DB_PATH).get_step_counts()
    if args.as_json:
        print(json.dumps(counts, ensure_ascii=False))
    else:
        for k, v in counts.items():
            print(f"{k:24s} {v}")
    return 0
