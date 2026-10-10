# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

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
import subprocess
from typing import Any, Dict, Optional, Union

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

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


def get_data_dir() -> Path:
    """Returns the data directory path.

    Supports PSL_DATA_DIR or PSL_HARNESS_STATE_DIR environment variables,
    falling back to ~/.local/share/psl.
    """
    custom = os.environ.get("PSL_DATA_DIR") or os.environ.get("PSL_HARNESS_STATE_DIR")
    if custom:
        return Path(custom).expanduser().resolve()
    return (Path.home() / ".local" / "share" / "psl").resolve()


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
    """Returns the path to global config.json."""
    return get_config_dir() / "config.json"


def find_workspace_root(start_dir: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Searches upward from start_dir (default cwd) for .psl, .agents, or .git."""
    curr = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()
    while True:
        if (curr / ".psl").exists() or (curr / ".agents").exists() or (curr / ".git").exists():
            return curr
        parent = curr.parent
        if parent == curr:
            break
        curr = parent
    return None


def get_workspace_config_path(
    workspace_root: Optional[Union[str, Path]] = None,
) -> Optional[Path]:
    """Returns <workspace_root>/.psl/config.json if workspace root exists, else None."""
    ws = Path(workspace_root).resolve() if workspace_root else find_workspace_root()
    if ws is None:
        return None
    return ws / ".psl" / "config.json"


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively deep-merges override dictionary into base dictionary."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(
    workspace_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Loads configuration dictionary by deep-merging global and workspace configs.

    Precedence: defaults < global (~/.config/psl/config.json) < workspace (.psl/config.json).
    """
    config = dict(DEFAULT_CONFIG)
    global_p = get_config_path()
    if global_p.is_file():
        try:
            with open(global_p, "r", encoding="utf-8") as f:
                g_data = json.load(f)
                if isinstance(g_data, dict):
                    config = _deep_merge(config, g_data)
        except (json.JSONDecodeError, OSError):
            pass

    ws_p = get_workspace_config_path(workspace_root)
    if ws_p and ws_p.is_file():
        try:
            with open(ws_p, "r", encoding="utf-8") as f:
                ws_data = json.load(f)
                if isinstance(ws_data, dict):
                    config = _deep_merge(config, ws_data)
        except (json.JSONDecodeError, OSError):
            pass

    return config


def save_config(
    config: Dict[str, Any],
    scope: str = "global",
    workspace_root: Optional[Union[str, Path]] = None,
) -> Path:
    """Atomically writes configuration to config.json in global or workspace scope."""
    if scope == "workspace":
        ws = Path(workspace_root).resolve() if workspace_root else find_workspace_root()
        if ws is None:
            raise ValueError("Cannot save workspace config: workspace root not found.")
        p = ws / ".psl" / "config.json"
    elif scope == "global":
        p = get_config_path()
    else:
        raise ValueError(f"Invalid config scope: '{scope}'. Must be 'global' or 'workspace'.")

    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = p.parent / f"{p.name}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, p)
    return p


def get_credentials_path() -> Path:
    """Returns the path to credentials.json."""
    return get_config_dir() / "credentials.json"


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


def clear_credentials() -> Path:
    """Atomically clears stored credentials by resetting to defaults with mode 0o600."""
    return save_credentials(dict(DEFAULT_CREDENTIALS))


def get_auth_token() -> Optional[str]:
    """Retrieves auth token from environment or stored credentials."""
    env_token = os.environ.get("PSL_AUTH_TOKEN")
    if env_token:
        return env_token.strip()
    creds = load_credentials()
    return creds.get("token")


def get_sync_endpoint(
    endpoint: Optional[Union[str, Path]] = None,
    workspace_root: Optional[Union[str, Path]] = None,
) -> str:
    """Retrieves telemetry endpoint following the 5-tier resolution hierarchy.

    Precedence:
    1. Explicit endpoint argument.
    2. Environment variable PSL_SYNC_ENDPOINT.
    3. Workspace configuration (<workspace_root>/.psl/config.json).
    4. Global configuration (~/.config/psl/config.json).
    5. Default: http://localhost:8000.
    """
    if isinstance(endpoint, Path):
        workspace_root = endpoint
        endpoint = None
    elif isinstance(endpoint, str) and not endpoint.startswith("http://") and not endpoint.startswith("https://") and workspace_root is None:
        p_cand = Path(endpoint)
        if p_cand.exists() or "/" in endpoint or "\\" in endpoint:
            workspace_root = p_cand
            endpoint = None

    if endpoint and isinstance(endpoint, str) and endpoint.strip():
        return endpoint.strip()

    env_endpoint = os.environ.get("PSL_SYNC_ENDPOINT")
    if env_endpoint and env_endpoint.strip():
        return env_endpoint.strip()

    ws_p = get_workspace_config_path(workspace_root)
    if ws_p and ws_p.is_file():
        try:
            with open(ws_p, "r", encoding="utf-8") as f:
                ws_data = json.load(f)
                if isinstance(ws_data, dict) and ws_data.get("endpoint"):
                    return str(ws_data["endpoint"]).strip()
        except (json.JSONDecodeError, OSError):
            pass

    global_p = get_config_path()
    if global_p.is_file():
        try:
            with open(global_p, "r", encoding="utf-8") as f:
                g_data = json.load(f)
                if isinstance(g_data, dict) and g_data.get("endpoint"):
                    return str(g_data["endpoint"]).strip()
        except (json.JSONDecodeError, OSError):
            pass

    return DEFAULT_CONFIG.get("endpoint", "http://localhost:8000")


def resolve_db_path(
    db_path: Optional[Union[str, Path]] = None,
    must_exist: bool = False,
) -> Path:
    """Resolves path to SQLite telemetry database with strict zero-CWD probing.

    Resolution order:
    1. Explicit db_path if provided.
    2. Environment variable PSL_TELEMETRY_DB.
    3. Repository root REPO_ROOT / 'data/telemetry.db' if it exists.
    4. XDG data directory get_data_dir() / 'telemetry.db' if it exists.
    5. Default fallback: REPO_ROOT / 'data/telemetry.db' if inside repo checkout, else XDG path.

    Raises FileNotFoundError if must_exist is True and the target database does not exist.
    """
    resolved: Optional[Path] = None

    # 1. Explicit db_path
    if db_path is not None and str(db_path).strip():
        resolved = Path(db_path).expanduser().resolve()
    # 2. Environment variable PSL_TELEMETRY_DB
    elif os.environ.get("PSL_TELEMETRY_DB"):
        resolved = Path(os.environ["PSL_TELEMETRY_DB"]).expanduser().resolve()
    # 3. Repository root REPO_ROOT / "data/telemetry.db" if it exists
    elif (REPO_ROOT / "data" / "telemetry.db").is_file():
        resolved = (REPO_ROOT / "data" / "telemetry.db").resolve()
    # 4. XDG data directory get_data_dir() / "telemetry.db" if it exists
    elif (get_data_dir() / "telemetry.db").is_file():
        resolved = (get_data_dir() / "telemetry.db").resolve()
    # 5. Default fallback: REPO_ROOT / "data/telemetry.db" if inside repo checkout, else XDG path
    else:
        is_repo = (REPO_ROOT / ".git").exists() or (REPO_ROOT / "pipeline").is_dir()
        if is_repo:
            resolved = (REPO_ROOT / "data" / "telemetry.db").resolve()
        else:
            resolved = (get_data_dir() / "telemetry.db").resolve()

    if must_exist and not resolved.is_file():
        raise FileNotFoundError(
            f"Telemetry database not found at {resolved}. "
            "Provide --db <path> or run 'psl audit extract'"
        )

    return resolved


def get_gh_cli_token() -> Optional[str]:
    """Lifts GitHub authentication token using GitHub CLI (`gh auth token`).

    Returns token string if gh returns 0, else None.
    """
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"],
            timeout=5.0,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
        return None
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None


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
        config = load_config(workspace_root=workspace_path)
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
