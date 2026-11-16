"""Location shared by the Windows installer and runtime settings."""
from hashlib import sha256
import os
from pathlib import Path


def installation_key(project: Path) -> str:
    normalized = str(project.resolve())
    if os.name == "nt":
        normalized = normalized.casefold()
    return sha256(normalized.encode("utf-8")).hexdigest()[:24]


def installation_dir(project: Path) -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not local:
        return None
    return Path(local) / "AI-Up" / "installations" / installation_key(project)
