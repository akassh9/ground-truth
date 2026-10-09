"""Project paths and .env loading."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_env():
    """Copy KEY=value lines from .env into os.environ, without overriding what's already set."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), re.sub(r"\s+#.*$", "", value).strip())
