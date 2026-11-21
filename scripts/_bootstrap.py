"""Standalone verification scripts: locate source tree and isolate generated output."""
from pathlib import Path
import os
import sys


def setup():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    output = root / "artifacts" / "verify"
    output.mkdir(parents=True, exist_ok=True)
    os.chdir(root)  # Existing probes use web/... relative to repository, not shell cwd.
    return root, output
