"""Run with system Python, even when runtime dependencies are unavailable."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audit3.diagnostics import main

if __name__ == "__main__":
    raise SystemExit(main())
