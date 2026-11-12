#!/usr/bin/env python3
"""Use .venv/bin/python scripts/validate_pending.py; no installation/downloads here."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audit3.validation import main

if __name__ == "__main__":
    raise SystemExit(main())
