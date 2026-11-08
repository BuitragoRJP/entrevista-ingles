import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SKILL = PROJECT / ".claude" / "skills" / "entrevista-ingles"
sys.path.insert(0, str(SKILL / "scripts"))
