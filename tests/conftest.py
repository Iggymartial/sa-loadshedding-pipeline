"""
conftest.py
Pytest auto-discovers this file. It adds extractor/ and loader/ to
sys.path so tests can do `import extract` and `import load` directly,
without turning the project into a formal installable Python package -
that would be overkill for a project this size.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "extractor"))
sys.path.insert(0, str(ROOT / "loader"))
