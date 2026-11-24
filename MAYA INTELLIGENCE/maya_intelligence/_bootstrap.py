"""Bootstrap module to add JARVIS to sys.path so `import custom` works."""

import sys
from pathlib import Path

JARVIS_ROOT = Path(__file__).parent.parent.parent / "JARVIS"
if JARVIS_ROOT.exists() and str(JARVIS_ROOT) not in sys.path:
    sys.path.insert(0, str(JARVIS_ROOT))