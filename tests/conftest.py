"""Configuration pytest : racine du dépôt sur sys.path (imports core/ui/data)."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
