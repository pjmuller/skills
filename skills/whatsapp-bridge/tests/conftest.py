"""Allow running these tests from the repository root env, which does not install this project."""
import sys
from pathlib import Path

root = str(Path(__file__).resolve().parents[1])
if root not in sys.path:
    sys.path.insert(0, root)
