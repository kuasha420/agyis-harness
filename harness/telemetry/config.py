"""
Configuration and Credential Store for PSL Telemetry Client (ADR-030).

Provides atomic, secure management of telemetry endpoint configuration,
workspace denylists, and authentication credentials.
"""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

DEFAULT_CONFIG: Dict[str, Any] = {
    "endpoint": "http://localhost:8000",
    "denylist": [],
    "mode": "opt-in",
}

DEFAULT_CREDENTIALS: Dict[str, Any] = {
    "token": None,
    "github_username": None,
    "updated_at": None,
}


def get_config_dir() -> Path:
    """Returns the configuration directory path.

    Supports PSL_CONFIG_DIR or PSL_HARNESS_STATE_DIR environment variables,
    falling back to ~/.config/psl.
    """
    custom = os.environ.get("PSL_CONFIG_DIR") or os.environ.get("PSL_HARNESS_STATE_DIR")
    if custom:
        return Path(custom).expanduser().resolve()
    return (Path.home() / ".config" / "psl").resolve()


def get_config_path() -> Path:
    """Returns the path to config.json."""
    return get_config_dir() / "config.json"


def get_credentials_path() -> Path:
    """Returns the path to credentials.json."""
    return get_config_dir() / "credentials.json"


def load_config() -> Dict[str, Any]:
    """Loads configuration dictionary with fallback defaults."""
    config = dict(DEFAULT_CONFIG)
    p = get_config_path()
    if p.is_file():
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                config.update(data)
    return config


def save_config(config: Dict[str, Any]) -> Path:
    """Atomically writes configuration to config.json."""
    p = get_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = p.parent / f"{p.name}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, p)
    return p


def load_credentials() -> Dict[str, Any]:
    """Loads credentials dictionary with fallback defaults."""
    creds = dict(DEFAULT_CREDENTIALS)
    p = get_credentials_path()
    if p.is_file():
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                creds.update(data)
    return creds


def save_credentials(credentials: Dict[str, Any]) -> Path:
    """Atomically writes credentials to credentials.json with mode 0o600."""
    p = get_credentials_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = p.parent / f"{p.name}.tmp.{os.getpid()}"
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8") as f:
        json.dump(credentials, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


def get_auth_token() -> Optional[str]:
    """Retrieves auth token from environment or stored credentials."""
    env_token = os.environ.get("PSL_AUTH_TOKEN")
    if env_token:
        return env_token.strip()
    creds = load_credentials()
    return creds.get("token")


def get_sync_endpoint() -> str:
    """Retrieves telemetry endpoint from environment or stored config."""
    env_endpoint = os.environ.get("PSL_SYNC_ENDPOINT")
    if env_endpoint:
        return env_endpoint.strip()
    cfg = load_config()
    return cfg.get("endpoint", "http://localhost:8000")


def is_workspace_denylisted(
    workspace_path: Union[str, Path],
    config: Optional[Dict[str, Any]] = None,
) -> bool:
    """Checks if workspace path is denylisted.

    Normalizes path, matches against config denylist entries by exact path,
    parent/subdirectory match, or fnmatch pattern.
    """
    if not workspace_path:
        return False
    if config is None:
        config = load_config()
    denylist = config.get("denylist", [])
    if not denylist:
        return False

    ws_path = Path(workspace_path).expanduser().resolve()
    ws_str = str(ws_path)

    for entry in denylist:
        if not isinstance(entry, str) or not entry.strip():
            continue
        entry_clean = entry.strip()

        # 1. Exact string match
        if ws_str == entry_clean:
            return True

        # 2. Raw glob pattern match
        if fnmatch.fnmatch(ws_str, entry_clean) or fnmatch.fnmatch(ws_path.name, entry_clean):
            return True

        # 3. Path normalization & parent/child hierarchy
        if not any(ch in entry_clean for ch in ("*", "?", "[", "]")):
            try:
                entry_path = Path(entry_clean).expanduser().resolve()
                if ws_str == str(entry_path):
                    return True
                if ws_path.is_relative_to(entry_path):
                    return True
                if fnmatch.fnmatch(ws_str, str(entry_path)):
                    return True
            except (ValueError, RuntimeError):
                pass

    return False


def _normalize_entry(p_str: str) -> str:
    if any(ch in p_str for ch in ("*", "?", "[", "]")):
        return p_str.strip()
    return str(Path(p_str).expanduser().resolve())


def add_to_denylist(path_str: str) -> bool:
    """Adds a path or pattern to the denylist in config.json. Returns True if added."""
    if not path_str or not path_str.strip():
        return False
    cfg = load_config()
    denylist = list(cfg.get("denylist", []))
    norm = _normalize_entry(path_str)
    if norm in denylist or path_str in denylist:
        return False
    denylist.append(norm)
    cfg["denylist"] = denylist
    save_config(cfg)
    return True


def remove_from_denylist(path_str: str) -> bool:
    """Removes a path or pattern from the denylist in config.json. Returns True if removed."""
    if not path_str or not path_str.strip():
        return False
    cfg = load_config()
    denylist = list(cfg.get("denylist", []))
    norm = _normalize_entry(path_str)
    new_denylist = [x for x in denylist if x != norm and x != path_str]
    if len(new_denylist) != len(denylist):
        cfg["denylist"] = new_denylist
        save_config(cfg)
        return True
    return False
