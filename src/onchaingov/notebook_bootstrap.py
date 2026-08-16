"""Jupyter notebook bootstrap."""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))
