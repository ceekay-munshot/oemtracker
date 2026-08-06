#!/usr/bin/env python3
"""
run.py — repo-root entry point for the monthly pipeline (delegates to scripts/run.py).

    python run.py [--only siam,fada] [--period 2026-06] [--skip-seed] [--no-build]

See scripts/run.py for the full orchestration and options.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.run import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
