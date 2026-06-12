"""oma — Application SQL Transform CLI (deterministic infrastructure).

Claude Code main session and subagents call this via Bash as the single entry point.
LLM work (transform/review/validate) is NOT done here — that's the CC subagent's job.
"""
import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oma", description="Application SQL Transform CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    from cli import cmd_status, cmd_db, cmd_analyze
    cmd_status.register(sub)
    cmd_db.register(sub)
    cmd_analyze.register(sub)
    # Future tasks add modules here:
    # cmd_merge.register(sub), cmd_test.register(sub),
    # cmd_report.register(sub), cmd_setup.register(sub)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
