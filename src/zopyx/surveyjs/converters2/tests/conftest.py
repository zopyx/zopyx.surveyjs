import sys
from pathlib import Path

# Add src to path for imports
SRC = Path(__file__).resolve().parents[4]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
