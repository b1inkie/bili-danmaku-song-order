"""Allow python tools/<tool>.py from any working directory without moving user paths."""
from pathlib import Path
import sys


def setup():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    return root
