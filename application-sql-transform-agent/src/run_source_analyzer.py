#!/usr/bin/env python3
"""Run Source Analyzer Agent"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.source_analyzer.agent import run_analysis

def run():
    """Entry point for orchestrator."""
    run_analysis()

if __name__ == "__main__":
    run_analysis()
