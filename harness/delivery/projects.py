# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Antigravity Desktop Project Registry Management (WS4).

Inspects and idempotently registers workspace entries inside
`<config_dir>/projects/*.json` matching the canonical Antigravity schema.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional, Union
from urllib.parse import unquote, urlparse
import uuid

from harness.delivery.surfaces import resolve_canonical_config_dir
from harness.utils.state import atomic_write_text

_logger = logging.getLogger(__name__)


def resolve_projects_config_dir(config_dir: Optional[Union[str, Path]] = None) -> Path:
    """Resolve canonical config directory honoring explicit arg, AGYIS_CONFIG_DIR, and PSL_CONFIG_DIR."""
    if config_dir is not None and str(config_dir).strip():
        return Path(str(config_dir).strip()).expanduser().resolve()
    for env_key in ("AGYIS_CONFIG_DIR", "PSL_CONFIG_DIR"):
        env_val = os.environ.get(env_key)
        if env_val and env_val.strip():
            return Path(env_val.strip()).expanduser().resolve()
    return resolve_canonical_config_dir(None)


def normalize_folder_uri(uri_or_path: Union[str, Path]) -> str:
    """Normalize local paths and file:/// URIs into canonical `file:///abs/path/` form."""
    raw = str(uri_or_path).strip()
    if not raw:
        raise ValueError("Folder URI or path must not be empty")

    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme == "file":
        decoded_path = unquote(parsed.path or "")
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            decoded_path = f"//{parsed.netloc}{decoded_path}"
        if not decoded_path:
            raise ValueError(f"Invalid file URI: {raw}")
        resolved = Path(decoded_path).resolve()
        uri = resolved.as_uri()
    elif parsed.scheme and len(parsed.scheme) > 1:
        return raw if raw.endswith("/") else f"{raw}/"
    else:
        resolved = Path(raw).expanduser().resolve()
        uri = resolved.as_uri()

    return uri if uri.endswith("/") else f"{uri}/"


def extract_project_folder_uris(payload: Dict[str, Any]) -> List[str]:
    """Extract folderUri strings from gitFolder or bare resource entries in a project JSON payload."""
    if not isinstance(payload, dict):
        return []
    project_resources = payload.get("projectResources")
    if not isinstance(project_resources, dict):
        return []
    resources = project_resources.get("resources")
    if not isinstance(resources, list):
        return []

    uris: List[str] = []
    seen: set[str] = set()
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        candidates: List[Any] = []
        git_folder = resource.get("gitFolder")
        if isinstance(git_folder, dict):
            candidates.append(git_folder.get("folderUri"))
        candidates.append(resource.get("folderUri"))
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                val = candidate.strip()
                if val not in seen:
                    seen.add(val)
                    uris.append(val)
    return uris


def _run_git_query(workspace: Path, git_args: List[str]) -> Optional[str]:
    """Run a read-only local git query and return stripped stdout on exit 0."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(workspace), *git_args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.debug("Git query %s failed in %s: %s", git_args, workspace, exc)
    return None


def _detect_default_branch(workspace: Path) -> str:
    """Detect repository defaultBranch locally without network calls."""
    if _run_git_query(workspace, ["rev-parse", "--is-inside-work-tree"]) != "true":
        return "main"

    origin_head = _run_git_query(workspace, ["symbolic-ref", "refs/remotes/origin/HEAD"])
    if origin_head:
        branch_part = origin_head.rsplit("/", 1)[-1].strip()
        if branch_part:
            return branch_part

    for ref_name, branch_name in (
        ("refs/heads/develop", "develop"),
        ("refs/remotes/origin/develop", "develop"),
        ("refs/heads/main", "main"),
        ("refs/remotes/origin/main", "main"),
        ("refs/heads/master", "master"),
        ("refs/remotes/origin/master", "master"),
    ):
        if _run_git_query(workspace, ["rev-parse", "--verify", "--quiet", ref_name]) is not None:
            return branch_name

    current_branch = _run_git_query(workspace, ["branch", "--show-current"])
    if current_branch:
        return current_branch

    return "main"


def _extract_git_metadata(payload: Dict[str, Any]) -> tuple[Optional[str], bool]:
    """Return (default_branch, is_git_folder) from projectResources.resources."""
    project_resources = payload.get("projectResources")
    if not isinstance(project_resources, dict):
        return None, False
    resources = project_resources.get("resources")
    if not isinstance(resources, list):
        return None, False

    is_git_folder = False
    default_branch: Optional[str] = None
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        git_folder = resource.get("gitFolder")
        if isinstance(git_folder, dict):
            is_git_folder = True
            raw_branch = git_folder.get("defaultBranch")
            if default_branch is None and isinstance(raw_branch, str) and raw_branch.strip():
                default_branch = raw_branch.strip()
    return default_branch, is_git_folder


def list_registered_projects(config_dir: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
    """List registered Antigravity projects from `<config_dir>/projects/*.json`."""
    cfg_dir = resolve_projects_config_dir(config_dir)
    projects_dir = cfg_dir / "projects"
    if not projects_dir.is_dir():
        return []

    records: List[Dict[str, Any]] = []
    for entry in sorted(projects_dir.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix.lower() != ".json":
            _logger.debug("Skipping non-JSON file in projects directory: %s", entry)
            continue
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            _logger.debug("Skipping malformed project file %s: %s", entry, exc)
            continue

        if not isinstance(payload, dict):
            _logger.debug("Skipping non-object project file %s", entry)
            continue

        raw_uris = extract_project_folder_uris(payload)
        normalized_uris: List[str] = []
        seen_uris: set[str] = set()
        for raw_uri in raw_uris:
            try:
                norm = normalize_folder_uri(raw_uri)
            except ValueError as exc:
                _logger.debug("Skipping invalid folderUri '%s' in %s: %s", raw_uri, entry, exc)
                continue
            if norm not in seen_uris:
                seen_uris.add(norm)
                normalized_uris.append(norm)

        default_branch, is_git_folder = _extract_git_metadata(payload)
        raw_id = payload.get("id")
        project_id = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else entry.stem
        raw_name = payload.get("name")
        project_name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else ""

        records.append({
            "id": project_id,
            "name": project_name,
            "folder_uris": normalized_uris,
            "default_branch": default_branch,
            "file_path": str(entry.resolve()),
            "is_git_folder": is_git_folder,
        })

    records.sort(key=lambda item: (item["name"].lower(), item["id"]))
    return records


def ensure_project_registered(
    workspace_path: Union[str, Path],
    config_dir: Optional[Union[str, Path]] = None,
    name: Optional[str] = None,
    default_branch: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Idempotently ensure workspace_path is registered in `<config_dir>/projects/<uuid>.json`."""
    ws = Path(workspace_path).expanduser().resolve()
    target_uri = normalize_folder_uri(ws)
    resolved_name = name.strip() if isinstance(name, str) and name.strip() else ws.name

    if not ws.exists() or not ws.is_dir():
        return {
            "success": False,
            "action": "error",
            "error": f"Workspace directory does not exist: {ws}",
            "project_id": None,
            "name": resolved_name,
            "project_file": None,
            "folder_uri": target_uri,
            "default_branch": default_branch,
            "dry_run": dry_run,
        }

    cfg_dir = resolve_projects_config_dir(config_dir)
    for existing in list_registered_projects(config_dir=cfg_dir):
        if target_uri in existing["folder_uris"]:
            return {
                "success": True,
                "action": "already_registered",
                "project_id": existing["id"],
                "name": existing["name"],
                "project_file": existing["file_path"],
                "folder_uri": target_uri,
                "default_branch": existing["default_branch"],
                "dry_run": dry_run,
            }

    resolved_branch = (
        default_branch.strip()
        if isinstance(default_branch, str) and default_branch.strip()
        else _detect_default_branch(ws)
    )
    project_id = str(uuid.uuid4())
    projects_dir = cfg_dir / "projects"
    project_file = projects_dir / f"{project_id}.json"

    payload: Dict[str, Any] = {
        "id": project_id,
        "name": resolved_name,
        "projectResources": {
            "resources": [
                {
                    "gitFolder": {
                        "folderUri": target_uri,
                        "defaultBranch": resolved_branch,
                        "allowWrite": True,
                    }
                }
            ]
        },
        "permissionGrants": {
            "v2Migrated": True,
        },
        "settings": {},
        "isWorkspaceOnly": False,
    }

    if dry_run:
        return {
            "success": True,
            "action": "would_create",
            "project_id": project_id,
            "name": resolved_name,
            "project_file": str(project_file),
            "folder_uri": target_uri,
            "default_branch": resolved_branch,
            "dry_run": True,
        }

    projects_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(project_file, json.dumps(payload, indent=2) + "\n")

    return {
        "success": True,
        "action": "created",
        "project_id": project_id,
        "name": resolved_name,
        "project_file": str(project_file.resolve()),
        "folder_uri": target_uri,
        "default_branch": resolved_branch,
        "dry_run": False,
    }


def _uri_to_local_path(uri: str) -> Optional[str]:
    """Converts a file:// folderUri to a resolved local filesystem path string, else None."""
    parsed = urlparse(uri)
    if parsed.scheme.lower() != "file":
        return None
    decoded_path = unquote(parsed.path or "")
    if parsed.netloc and parsed.netloc.lower() != "localhost":
        decoded_path = f"//{parsed.netloc}{decoded_path}"
    if not decoded_path:
        return None
    try:
        return str(Path(decoded_path).resolve())
    except OSError:
        return decoded_path.rstrip("/") or "/"


def _uri_basename(uri: str) -> str:
    """Extracts repository basename from a folderUri."""
    parsed = urlparse(uri)
    path_part = unquote(parsed.path or "").rstrip("/")
    if not path_part:
        return ""
    return Path(path_part).name


def _resolved_project_payload(
    rec: Dict[str, Any],
    *,
    matched_by: str,
    status: str = "resolved",
    dry_run: bool = False,
    ensure_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Formats a normalized resolution dict for a matched or registered project."""
    uris = list(rec.get("folder_uris") or [])
    ws_path = _uri_to_local_path(uris[0]) if uris else None
    out: Dict[str, Any] = {
        "success": True,
        "status": status,
        "matched_by": matched_by,
        "project_id": rec["id"],
        "name": rec.get("name") or (Path(ws_path).name if ws_path else rec["id"]),
        "workspace_path": ws_path,
        "folder_uris": uris,
        "default_branch": rec.get("default_branch"),
        "project": rec,
        "candidates": [rec],
        "dry_run": dry_run,
    }
    if ensure_result is not None:
        out["ensure_result"] = ensure_result
    return out


def resolve_project_target(
    target: Union[str, Path],
    config_dir: Optional[Union[str, Path]] = None,
    ensure: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Resolves a project UUID, workspace path, file:// URI, or repo basename slug
    against registered Antigravity projects in `<config_dir>/projects/*.json`.
    """
    raw = str(target or "").strip()
    if not raw:
        return {
            "success": False,
            "status": "invalid",
            "target": raw,
            "error": "Target project must not be empty.",
            "project_id": None,
            "name": None,
            "workspace_path": None,
            "folder_uris": [],
            "default_branch": None,
            "project": None,
            "candidates": [],
            "dry_run": dry_run,
        }

    cfg_dir = resolve_projects_config_dir(config_dir)
    registered = list_registered_projects(config_dir=cfg_dir)

    # 1. Exact / case-insensitive project_id (UUID) match
    raw_lower = raw.lower()
    id_matches = [rec for rec in registered if rec["id"].lower() == raw_lower]
    if len(id_matches) == 1:
        return _resolved_project_payload(id_matches[0], matched_by="project_id", dry_run=dry_run)
    if len(id_matches) > 1:
        return {
            "success": False,
            "status": "ambiguous",
            "target": raw,
            "error": f"Ambiguous project ID '{raw}' matched {len(id_matches)} records.",
            "project_id": None,
            "name": None,
            "workspace_path": None,
            "folder_uris": [],
            "default_branch": None,
            "project": None,
            "candidates": id_matches,
            "dry_run": dry_run,
        }

    try:
        uuid.UUID(raw)
        is_uuid = True
    except ValueError:
        is_uuid = False
    if is_uuid:
        return {
            "success": False,
            "status": "not_found",
            "target": raw,
            "error": f"No registered Antigravity project found for ID '{raw}'.",
            "project_id": None,
            "name": None,
            "workspace_path": None,
            "folder_uris": [],
            "default_branch": None,
            "project": None,
            "candidates": [],
            "dry_run": dry_run,
        }

    is_path_hint = (
        isinstance(target, Path)
        or raw in (".", "..")
        or raw.startswith(("file://", "/", "./", "../", "~/"))
        or os.sep in raw
    )

    def _try_register_or_report_unregistered(local_dir: Path, norm_uri: str) -> Dict[str, Any]:
        if ensure:
            ens = ensure_project_registered(local_dir, config_dir=cfg_dir, dry_run=dry_run)
            if ens.get("success"):
                rec = {
                    "id": ens["project_id"],
                    "name": ens["name"],
                    "folder_uris": [ens["folder_uri"]],
                    "default_branch": ens.get("default_branch"),
                    "file_path": ens.get("project_file"),
                    "is_git_folder": True,
                }
                return _resolved_project_payload(
                    rec,
                    matched_by="path_ensured",
                    status=str(ens.get("action") or "created"),
                    dry_run=dry_run,
                    ensure_result=ens,
                )
            return {
                "success": False,
                "status": "error",
                "target": raw,
                "error": ens.get("error") or f"Failed to register workspace '{local_dir}'.",
                "project_id": None,
                "name": None,
                "workspace_path": str(local_dir),
                "folder_uris": [norm_uri],
                "default_branch": None,
                "project": None,
                "candidates": [],
                "dry_run": dry_run,
            }
        return {
            "success": False,
            "status": "unregistered",
            "target": raw,
            "error": f"Workspace '{local_dir}' exists on disk but is not registered in Antigravity projects.",
            "can_ensure": True,
            "project_id": None,
            "name": local_dir.name,
            "workspace_path": str(local_dir),
            "folder_uris": [norm_uri],
            "default_branch": None,
            "project": None,
            "candidates": [],
            "dry_run": dry_run,
        }

    # 2. Path / file:// URI match
    if is_path_hint:
        try:
            norm_uri = normalize_folder_uri(raw)
        except ValueError as exc:
            return {
                "success": False,
                "status": "invalid",
                "target": raw,
                "error": str(exc),
                "project_id": None,
                "name": None,
                "workspace_path": None,
                "folder_uris": [],
                "default_branch": None,
                "project": None,
                "candidates": [],
                "dry_run": dry_run,
            }

        path_matches = [rec for rec in registered if norm_uri in rec["folder_uris"]]
        if len(path_matches) == 1:
            return _resolved_project_payload(path_matches[0], matched_by="path", dry_run=dry_run)
        if len(path_matches) > 1:
            return {
                "success": False,
                "status": "ambiguous",
                "target": raw,
                "error": f"Ambiguous project path '{raw}' matched {len(path_matches)} registered projects.",
                "project_id": None,
                "name": None,
                "workspace_path": _uri_to_local_path(norm_uri),
                "folder_uris": [norm_uri],
                "default_branch": None,
                "project": None,
                "candidates": path_matches,
                "dry_run": dry_run,
            }

        local_str = _uri_to_local_path(norm_uri)
        if local_str:
            local_dir = Path(local_str)
            if local_dir.is_dir():
                return _try_register_or_report_unregistered(local_dir, norm_uri)

        return {
            "success": False,
            "status": "not_found",
            "target": raw,
            "error": f"Project path does not exist and is not registered: {raw}",
            "project_id": None,
            "name": None,
            "workspace_path": local_str,
            "folder_uris": [norm_uri],
            "default_branch": None,
            "project": None,
            "candidates": [],
            "dry_run": dry_run,
        }

    # 3. Repository name or folder basename slug match
    exact_matches = [
        rec for rec in registered
        if rec["name"] == raw or any(_uri_basename(u) == raw for u in rec["folder_uris"])
    ]
    slug_matches = exact_matches or [
        rec for rec in registered
        if rec["name"].lower() == raw_lower or any(_uri_basename(u).lower() == raw_lower for u in rec["folder_uris"])
    ]
    if len(slug_matches) == 1:
        return _resolved_project_payload(slug_matches[0], matched_by="slug", dry_run=dry_run)
    if len(slug_matches) > 1:
        return {
            "success": False,
            "status": "ambiguous",
            "target": raw,
            "error": f"Ambiguous project target '{raw}' matched {len(slug_matches)} registered projects.",
            "project_id": None,
            "name": None,
            "workspace_path": None,
            "folder_uris": [],
            "default_branch": None,
            "project": None,
            "candidates": slug_matches,
            "dry_run": dry_run,
        }

    # 4. Fallback: existing relative directory matching target name
    cand_dir = Path(raw).expanduser()
    if cand_dir.is_dir():
        resolved_dir = cand_dir.resolve()
        return _try_register_or_report_unregistered(resolved_dir, normalize_folder_uri(resolved_dir))

    return {
        "success": False,
        "status": "not_found",
        "target": raw,
        "error": f"No registered Antigravity project found matching '{raw}'.",
        "project_id": None,
        "name": None,
        "workspace_path": None,
        "folder_uris": [],
        "default_branch": None,
        "project": None,
        "candidates": [],
        "dry_run": dry_run,
    }


__all__ = [
    "ensure_project_registered",
    "extract_project_folder_uris",
    "list_registered_projects",
    "normalize_folder_uri",
    "resolve_project_target",
    "resolve_projects_config_dir",
]
