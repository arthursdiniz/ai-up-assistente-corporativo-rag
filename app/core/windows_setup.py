"""Location shared by the Windows installer and runtime settings."""
from hashlib import sha256
import os
from pathlib import Path


def installation_dir(project: Path) -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not local:
        return None
    key = sha256(str(project.resolve()).casefold().encode("utf-8")).hexdigest()[:24]
    return Path(local) / "AI-Up" / "installations" / key
