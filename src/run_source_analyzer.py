#!/usr/bin/env python3
"""Run Source Analyzer Agent"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.source_analyzer.agent import run_analysis
from core.db_migrate import ensure_schema
from core.html_report import generate_html_report

def run():
    """Entry point for orchestrator."""
    ensure_schema()
    run_analysis()
    generate_html_report()

if __name__ == "__main__":
    ensure_schema()
    run_analysis()
    generate_html_report()
