"""Central configuration. Everything is overridable through environment variables / .env."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional for unit tests
    pass

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = os.getenv("PARABANK_URL", "https://parabank.parasoft.com/parabank").rstrip("/")
RESULTS = ROOT / "results"
ARTIFACTS = RESULTS / "artifacts"
SOP_DIR = ROOT / "docs" / "sops"
DASHBOARD = ROOT / "dashboard"
SEED = int(os.getenv("DATA_SEED", "42"))
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
