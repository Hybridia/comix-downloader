"""
Loader for ``secrets.json`` — site-specific credentials kept out of the
project's main ``config.json`` (which is checked into git) and out of
the version-controlled tree (``secrets.json`` is in ``.gitignore``).

Each provider that needs auth keys looks itself up by name, e.g.
``get_provider_secrets("toomics")`` → ``{"cookie": "...", "user_agent": "..."}``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

# Project root = parent of "src/"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SECRETS_PATH = _PROJECT_ROOT / "secrets.json"


class SecretsError(RuntimeError):
    """Raised when required credentials are missing or malformed."""


def secrets_path() -> Path:
    """Path the secrets file is loaded from."""
    return Path(os.environ.get("COMIX_SECRETS_PATH", _DEFAULT_SECRETS_PATH))


def load_secrets() -> dict:
    """Return the parsed ``secrets.json``, or ``{}`` if it doesn't exist."""
    p = secrets_path()
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SecretsError(f"Failed to read {p}: {e}") from e
    if not isinstance(data, dict):
        raise SecretsError(f"{p} must contain a JSON object at the top level")
    return data


def get_provider_secrets(name: str) -> Optional[dict]:
    """Return the secrets block for ``name`` (e.g. ``"toomics"``), or ``None``."""
    block = load_secrets().get(name)
    if block is None:
        return None
    if not isinstance(block, dict):
        raise SecretsError(
            f"`{name}` entry in {secrets_path()} must be a JSON object"
        )
    return block


def save_provider_secrets(name: str, values: dict) -> None:
    """
    Persist a ``{name: {...}}`` block, merging into anything already in
    ``secrets.json`` so other providers' keys aren't clobbered. Writes
    atomically (tmp + rename) and locks file mode to 0600.
    """
    p = secrets_path()
    data = load_secrets() if p.exists() else {}
    block = data.get(name) if isinstance(data.get(name), dict) else {}
    block = dict(block)
    block.update(values)
    # Drop empty values so they don't shadow defaults later.
    block = {k: v for k, v in block.items() if v not in (None, "")}
    if block:
        data[name] = block
    else:
        data.pop(name, None)

    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass  # filesystem may not support chmod (e.g. NTFS)
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
