# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Crosstalk Core Engine: Discovery, Sanitized Handover, Steering & Soft Archive.

Stdlib-only transport and safety layer bridging top-level Antigravity conversations
across Desktop (`antigravity`), CLI (`antigravity-cli`), and registered workspace
projects with CSRF/secret/.dirtyroom/ sanitization, hop bounds, cycle rejection,
and Tier-1 `.agents/artifacts/crosstalk/` baton persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from harness.delivery.crosstalk_db import (
    call_conversation_service,
    call_ls_service,
    infer_surface_name,
    inspect_conversation_steps,
    is_sandbox_refusal,
    query_conversation_summaries,
    resolve_app_data_roots,
    resolve_ls_credentials,
)
from harness.delivery.git_hygiene import configure_git_exclude
from harness.delivery.projects import list_registered_projects, resolve_project_target
from harness.telemetry.redaction import sanitize_crosstalk_payload
from harness.utils.context import get_active_conversation_id
from harness.utils.state import atomic_write_json, sanitize_conv_id

MAX_CROSSTALK_HOPS: int = 2
HARD_MAX_CROSSTALK_HOPS: int = 3
CROSSTALK_LEDGER_SUBDIR: str = ".agents/artifacts/crosstalk"
CROSSTALK_TAG_PREFIX: str = "crosstalk"

_ENVELOPE_BLOCK_RE = re.compile(
    r"\[CROSSTALK-V1\][^\n]*\n(?P<body>[\s\S]*?)\n\[/CROSSTALK-V1\]",
)
_INLINE_HOP_RE = re.compile(r"\[CROSSTALK-HOP:\s*(\d+)\s*/\s*(\d+)\s*\]", re.IGNORECASE)
_INLINE_ROLE_RE = re.compile(r"\[CROSSTALK-ROLE:\s*([^\]\r\n]+?)\s*\]", re.IGNORECASE)
_DIRTYROOM_TEXT_RE = re.compile(r"(?:^|[\s\"'`(/\\])\.dirtyroom(?:[/\\]|$|\s|[\"'`),;:\]])", re.IGNORECASE)
_SENSITIVE_ARTIFACT_RE = re.compile(r"(?:^|[/\\])(?:\.env(?:\.[^/\\]+)?|[^/\\]+\.(?:pem|key))$", re.IGNORECASE)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fail_res(status: str, error: str, *, dry_run: bool = False, blocked: bool = False, sandbox_blocked: bool = False, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "success": False,
        "status": status,
        "blocked": blocked,
        "dry_run": dry_run,
        "sandbox_blocked": sandbox_blocked,
        "error": error,
    }
    out.update(extra)
    return out


def serialize_crosstalk_envelope(envelope: Dict[str, Any]) -> str:
    """Serializes a structured `[CROSSTALK-V1]` baton header block for prompt handoffs."""
    hop = int(envelope.get("hop") or 1)
    max_hops = int(envelope.get("max_hops") or MAX_CROSSTALK_HOPS)
    role_hint = str(envelope.get("role_hint") or "").strip()
    header_parts = ["[CROSSTALK-V1]", f"[CROSSTALK-HOP: {hop}/{max_hops}]"]
    if role_hint:
        header_parts.append(f"[CROSSTALK-ROLE: {role_hint}]")
    lineage = [str(x).strip() for x in (envelope.get("lineage") or []) if str(x).strip()]
    proj_lineage = [str(x).strip() for x in (envelope.get("project_lineage") or []) if str(x).strip()]
    artifacts = [str(x).strip() for x in (envelope.get("artifacts") or []) if str(x).strip()]
    return "\n".join([
        " ".join(header_parts),
        f"from_cid: {str(envelope.get('from_cid') or 'none').strip() or 'none'}",
        f"from_project: {str(envelope.get('from_project') or 'unknown').strip() or 'unknown'}",
        f"to_project: {str(envelope.get('to_project') or 'unknown').strip() or 'unknown'}",
        f"intent: {str(envelope.get('intent') or 'handoff').strip() or 'handoff'}",
        f"hop: {hop}/{max_hops}",
        f"role_hint: {role_hint or 'none'}",
        f"group_id: {str(envelope.get('group_id') or 'none').strip() or 'none'}",
        f"lineage: {','.join(lineage) if lineage else 'none'}",
        f"project_lineage: {','.join(proj_lineage) if proj_lineage else 'none'}",
        f"artifacts: {','.join(artifacts) if artifacts else 'none'}",
        "[/CROSSTALK-V1]",
    ])


def parse_crosstalk_envelope(text: str) -> Optional[Dict[str, Any]]:
    """Parses a `[CROSSTALK-V1]` baton header (or inline hop/role markers) from prompt text."""
    if not text or not isinstance(text, str):
        return None
    m = _ENVELOPE_BLOCK_RE.search(text)
    if m:
        parsed: Dict[str, Any] = {
            "from_cid": None, "from_project": None, "to_project": None, "intent": "handoff",
            "hop": 1, "max_hops": MAX_CROSSTALK_HOPS, "role_hint": None, "group_id": None,
            "lineage": [], "project_lineage": [], "artifacts": [],
        }
        for raw_line in m.group("body").splitlines():
            if ":" not in raw_line:
                continue
            key, val = raw_line.split(":", 1)
            k, v = key.strip().lower(), val.strip()
            if k in ("from_cid", "from_project", "to_project", "intent", "role_hint", "group_id"):
                parsed[k] = None if (not v or v.lower() == "none") else v
            elif k == "hop":
                if "/" in v:
                    h_part, m_part = v.split("/", 1)
                    if h_part.strip().isdigit():
                        parsed["hop"] = int(h_part.strip())
                    if m_part.strip().isdigit():
                        parsed["max_hops"] = int(m_part.strip())
                elif v.isdigit():
                    parsed["hop"] = int(v)
            elif k == "max_hops" and v.isdigit():
                parsed["max_hops"] = int(v)
            elif k in ("lineage", "project_lineage", "artifacts") and v and v.lower() != "none":
                parsed[k] = [item.strip() for item in v.split(",") if item.strip()]
        return parsed

    hop_m, role_m = _INLINE_HOP_RE.search(text), _INLINE_ROLE_RE.search(text)
    if hop_m or role_m:
        return {
            "from_cid": None, "from_project": None, "to_project": None, "intent": "handoff",
            "hop": int(hop_m.group(1)) if hop_m else 1,
            "max_hops": int(hop_m.group(2)) if hop_m else MAX_CROSSTALK_HOPS,
            "role_hint": role_m.group(1).strip() if role_m else None,
            "group_id": None, "lineage": [], "project_lineage": [], "artifacts": [],
        }
    return None


def validate_crosstalk_guards(
    *,
    hop: int,
    max_hops: int = MAX_CROSSTALK_HOPS,
    caller_cid: Optional[str] = None,
    target_cid: Optional[str] = None,
    from_project: Optional[str] = None,
    to_project: Optional[str] = None,
    lineage: Optional[Sequence[str]] = None,
    project_lineage: Optional[Sequence[str]] = None,
    artifacts: Optional[Sequence[str]] = None,
    raw_text: str = "",
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Enforces hop bounds, self-target/cycle bans, and `.dirtyroom/` outbound blocks."""
    if max_hops < 1 or max_hops > HARD_MAX_CROSSTALK_HOPS:
        return False, "hop_limit_exceeded", f"max_hops={max_hops} exceeds HARD_MAX_CROSSTALK_HOPS={HARD_MAX_CROSSTALK_HOPS}."
    if hop < 1 or hop > max_hops:
        return False, "hop_limit_exceeded", f"Crosstalk hop {hop}/{max_hops} exceeds hop budget (hard ceiling {HARD_MAX_CROSSTALK_HOPS})."

    c_cid, t_cid = (caller_cid or "").strip(), (target_cid or "").strip()
    if c_cid and t_cid and c_cid == t_cid:
        return False, "self_target", f"Self-target crosstalk blocked: target_cid '{t_cid}' matches caller_cid."

    cid_hist = [str(x).strip() for x in (lineage or []) if str(x).strip()]
    if t_cid and t_cid in cid_hist:
        return False, "cycle_detected", f"Crosstalk CID cycle detected: target '{t_cid}' is already in lineage {cid_hist}."

    from_norm, to_norm = (from_project or "").strip().lower(), (to_project or "").strip().lower()
    proj_hist = [str(x).strip().lower() for x in (project_lineage or []) if str(x).strip()]
    if to_norm and from_norm and from_norm != to_norm and to_norm in proj_hist:
        return False, "cycle_detected", f"Cross-project cycle blocked ({from_project} -> {to_project} revisits {proj_hist})."

    for art in artifacts or ():
        art_s = str(art or "").strip()
        if not art_s:
            continue
        if ".dirtyroom" in art_s.lower():
            return False, "dirtyroom_leakage", f"Outbound `.dirtyroom/` artifact blocked: '{art_s}'."
        if _SENSITIVE_ARTIFACT_RE.search(art_s):
            return False, "sensitive_artifact_blocked", f"Outbound sensitive artifact blocked: '{art_s}'."

    if raw_text and _DIRTYROOM_TEXT_RE.search(raw_text):
        return False, "dirtyroom_leakage", "Outbound payload references `.dirtyroom/` and was blocked cleanly."
    return True, None, None


def read_inbound_baton(workspace_path: Union[str, Path], conversation_id: str) -> Optional[Dict[str, Any]]:
    """Reads `<workspace>/.agents/artifacts/crosstalk/inbound_<cid>.json` if present."""
    cid = sanitize_conv_id(conversation_id, default="")
    if not cid:
        return None
    baton_path = Path(workspace_path) / CROSSTALK_LEDGER_SUBDIR / f"inbound_{cid}.json"
    if not baton_path.is_file():
        return None
    try:
        data = json.loads(baton_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _persist_crosstalk_ledger(
    workspace_path: Union[str, Path],
    direction: str,
    conversation_id: str,
    payload: Dict[str, Any],
) -> Path:
    """Atomically writes inbound/outbound Tier-1 ledger JSON and ensures git exclude hygiene."""
    ws = Path(workspace_path).resolve()
    safe_id = sanitize_conv_id(conversation_id)
    target_path = ws / CROSSTALK_LEDGER_SUBDIR / f"{direction}_{safe_id}.json"
    atomic_write_json(target_path, payload, indent=2)
    if (ws / ".git").exists():
        try:
            configure_git_exclude(ws)
        except (OSError, ValueError):
            pass
    return target_path


def _normalize_rpc_conversation(conv: Dict[str, Any], default_root: str, default_surf: str) -> Dict[str, Any]:
    """Projects a ConversationService Conversation object into normalized discovery shape."""
    meta = conv.get("metadata") if isinstance(conv.get("metadata"), dict) else {}
    ann = conv.get("annotations") if isinstance(conv.get("annotations"), dict) else {}
    state = conv.get("state") if isinstance(conv.get("state"), dict) else {}
    rpc_tags = list(dict.fromkeys([
        *(str(t) for t in (meta.get("tags") or []) if str(t).strip()),
        *(str(t) for t in (ann.get("tags") or []) if str(t).strip()),
    ]))
    title = str(ann.get("title") or state.get("summary") or "").strip()
    run_state = str(state.get("runState") or "RUN_STATE_IDLE").strip()
    update_time = str(state.get("updateTime") or meta.get("createTime") or "").strip()
    meta_parent = str(meta.get("parentConversationId") or "").strip()
    return {
        "conversation_id": str(conv.get("id") or "").strip(), "title": title,
        "preview": str(state.get("summary") or "").strip(), "step_count": 0,
        "last_modified_time": update_time, "workspace_uris": [], "status": run_state, "run_state": run_state,
        "source": "rpc", "project_id": str(meta.get("projectId") or "").strip(), "agent_name": "",
        "parent_conversation_id": meta_parent, "nesting_depth": 1 if meta_parent else 0,
        "not_fully_idle": run_state == "RUN_STATE_RUNNING", "killed": False,
        "last_user_input_time": "", "last_user_input_step_index": -1,
        "group_id": str(ann.get("conversationGroupId") or "").strip(),
        "app_data_dir": default_root, "surface": default_surf, "surfaces": [default_surf],
        "archived": bool(ann.get("archived", False)), "pinned": bool(ann.get("pinned", False)),
        "starred": bool(ann.get("starred", False)), "tags": rpc_tags, "fts_matched": False, "live_rpc": True,
    }


def discover_conversations(
    *,
    query: Optional[str] = None,
    target: Optional[Union[str, Path]] = None,
    project_id: Optional[str] = None,
    parent_conversation_id: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
    include_archived: bool = False,
    include_children: bool = False,
    surface: Optional[str] = None,
    limit: int = 50,
    config_dir: Optional[Union[str, Path]] = None,
    app_data_roots: Optional[Sequence[Union[str, Path]]] = None,
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
    timeout: float = 2.0,
) -> Dict[str, Any]:
    """Discovers conversations across Desktop + CLI SQLite (`conversation_summaries.db` + FTS5) and `ListConversations` RPC."""
    resolved_project_id, resolved_ws_path = project_id, None
    if target is not None and str(target).strip() and not resolved_project_id:
        t_res = resolve_project_target(target, config_dir=config_dir)
        if not t_res.get("success"):
            return _fail_res(
                t_res.get("status", "not_found"), t_res.get("error") or f"Unable to resolve target '{target}'.",
                candidates=t_res.get("candidates", []), count=0, conversations=[],
            )
        resolved_project_id, resolved_ws_path = t_res["project_id"], t_res.get("workspace_path")

    roots = resolve_app_data_roots(app_data_roots=app_data_roots, config_dir=config_dir)
    sqlite_rows, sqlite_counts = query_conversation_summaries(
        query=query, project_id=resolved_project_id, workspace_path=resolved_ws_path,
        parent_conversation_id=parent_conversation_id, include_children=include_children,
        surface=surface, limit=max(1, limit), app_data_roots=roots, config_dir=config_dir, timeout=min(float(timeout), 1.0),
    )
    merged: Dict[str, Dict[str, Any]] = {rec["conversation_id"]: rec for rec in sqlite_rows}
    surf_filter = "" if (surface or "").strip().lower() in ("", "all") else (surface or "").strip().lower()

    rpc_payload: Dict[str, Any] = {"pageSize": min(max(1, limit), 100), "includeArchived": bool(include_archived)}
    if resolved_project_id:
        rpc_payload["projectId"] = resolved_project_id
    if parent_conversation_id is not None:
        rpc_payload["parentConversationId"] = parent_conversation_id
    elif not include_children:
        rpc_payload["parentConversationId"] = ""
    if tags:
        rpc_payload["tags"] = [str(t) for t in tags if str(t).strip()]

    rpc_res = call_conversation_service("ListConversations", rpc_payload, ls_address=ls_address, csrf_token=csrf_token, timeout=timeout)
    rpc_count = 0
    if rpc_res["ok"] and isinstance(rpc_res["data"], dict):
        q_lower = query.strip().lower() if query and query.strip() else ""
        default_root, default_surf = (str(roots[0]), infer_surface_name(roots[0])) if roots else ("", "desktop")
        for conv in (rpc_res["data"].get("conversations") or []):
            if not isinstance(conv, dict):
                continue
            norm = _normalize_rpc_conversation(conv, default_root, default_surf)
            cid = norm["conversation_id"]
            if not cid or (surf_filter and surf_filter != "desktop" and cid not in merged):
                continue
            if q_lower and cid not in merged:
                if q_lower not in " ".join((cid, norm["title"], norm["preview"], norm["project_id"], " ".join(norm["tags"]))).lower():
                    continue
            rpc_count += 1
            existing = merged.get(cid)
            if existing is None:
                merged[cid] = norm
            else:
                existing["live_rpc"] = True
                for key in ("run_state", "archived", "pinned", "starred", "tags"):
                    existing[key] = norm[key]
                for key in ("title", "group_id", "project_id", "parent_conversation_id"):
                    if norm[key] and not existing.get(key):
                        existing[key] = norm[key]
                if norm["last_modified_time"] > existing.get("last_modified_time", ""):
                    existing["last_modified_time"] = norm["last_modified_time"]

    proj_names = {p["id"]: p["name"] for p in list_registered_projects(config_dir=config_dir) if p.get("name")}
    req_tags = {str(t).strip() for t in (tags or []) if str(t).strip()}
    filtered: List[Dict[str, Any]] = []
    for rec in merged.values():
        if (not include_archived and rec.get("archived")) or (req_tags and not req_tags.issubset(set(rec.get("tags") or []))):
            continue
        rec.setdefault("archived", False)
        rec.setdefault("tags", [])
        pid = rec.get("project_id") or ""
        if pid and pid in proj_names and not rec.get("project_name"):
            rec["project_name"] = proj_names[pid]
        filtered.append(rec)

    filtered.sort(key=lambda item: (item.get("last_modified_time") or "", item.get("conversation_id") or ""), reverse=True)
    final_items = filtered[: max(1, limit)]
    return {
        "success": True, "status": "ok", "count": len(final_items), "conversations": final_items,
        "surfaces_queried": [str(r) for r in roots], "sqlite_counts": sqlite_counts,
        "rpc": {
            "ok": rpc_res["ok"], "sandbox_blocked": rpc_res["sandbox_blocked"], "missing_env": rpc_res["missing_env"],
            "connection_refused": rpc_res["connection_refused"], "error": rpc_res["error"], "count": rpc_count,
        },
        "sandbox_blocked": rpc_res["sandbox_blocked"], "query": query, "project_id": resolved_project_id,
    }


def get_conversation(
    conversation_id: str,
    *,
    include_steps: bool = False,
    tail: int = 20,
    config_dir: Optional[Union[str, Path]] = None,
    app_data_roots: Optional[Sequence[Union[str, Path]]] = None,
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
    timeout: float = 2.0,
) -> Dict[str, Any]:
    """Fetches metadata via `ConversationService/GetConversation` + SQLite summary + optional transcript tail."""
    cid = (conversation_id or "").strip()
    if not cid:
        return _fail_res("invalid", "conversation_id must not be empty.", conversation_id=cid)

    roots = resolve_app_data_roots(app_data_roots=app_data_roots, config_dir=config_dir)
    sql_rows, _ = query_conversation_summaries(
        query=cid, include_children=True, limit=10, app_data_roots=roots, config_dir=config_dir, timeout=min(float(timeout), 1.0),
    )
    sql_match = next((r for r in sql_rows if r["conversation_id"] == cid), None)
    rpc_res = call_conversation_service("GetConversation", {"conversationId": cid}, ls_address=ls_address, csrf_token=csrf_token, timeout=timeout)

    conv_record: Optional[Dict[str, Any]] = dict(sql_match) if sql_match else None
    if rpc_res["ok"] and isinstance(rpc_res["data"], dict):
        rpc_conv = rpc_res["data"].get("conversation") if isinstance(rpc_res["data"].get("conversation"), dict) else rpc_res["data"]
        if isinstance(rpc_conv, dict) and (rpc_conv.get("id") or cid):
            default_root, default_surf = (str(roots[0]), infer_surface_name(roots[0])) if roots else ("", "desktop")
            norm = _normalize_rpc_conversation(rpc_conv, default_root, default_surf)
            if conv_record is None:
                conv_record = norm
            else:
                conv_record.update({k: norm[k] for k in ("run_state", "archived", "pinned", "starred", "tags", "live_rpc")})
                for k in ("title", "group_id", "project_id", "parent_conversation_id"):
                    if norm[k]:
                        conv_record[k] = norm[k]

    steps_info = inspect_conversation_steps(cid, tail=tail, app_data_roots=roots, config_dir=config_dir) if include_steps else None
    if conv_record is None and not (steps_info and steps_info.get("success")):
        return _fail_res(
            "sandbox_blocked" if rpc_res["sandbox_blocked"] else "not_found",
            rpc_res["error"] or f"Conversation '{cid}' not found.",
            conversation_id=cid, sandbox_blocked=rpc_res["sandbox_blocked"], missing_env=rpc_res["missing_env"], rpc=rpc_res,
        )
    return {
        "success": True, "status": "ok", "conversation_id": cid, "conversation": conv_record, "steps": steps_info,
        "rpc": {"ok": rpc_res["ok"], "sandbox_blocked": rpc_res["sandbox_blocked"], "missing_env": rpc_res["missing_env"], "error": rpc_res["error"]},
        "sandbox_blocked": rpc_res["sandbox_blocked"],
    }


def _load_checkpoint_attachment(
    source_ws: Optional[Path],
    caller_cid: Optional[str],
    checkpoint_path: Optional[Union[str, Path]],
) -> Tuple[Optional[str], str]:
    """Loads bounded checkpoint excerpt and workspace-relative pointer if requested."""
    cand: Optional[Path] = None
    if checkpoint_path is not None and str(checkpoint_path).strip():
        cand = Path(checkpoint_path).expanduser()
        if not cand.is_absolute() and source_ws is not None:
            cand = source_ws / cand
    elif source_ws is not None:
        cp_dir = source_ws / ".agents" / "artifacts" / "checkpoints"
        if caller_cid:
            safe = sanitize_conv_id(caller_cid, default="")
            if safe and (cp_dir / f"{safe}.md").is_file():
                cand = cp_dir / f"{safe}.md"
        if cand is None and (cp_dir / "latest.md").is_file():
            cand = cp_dir / "latest.md"

    if cand is None or not cand.is_file():
        return None, ""
    try:
        text = cand.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None, ""

    rel_or_path = str(cand)
    if source_ws is not None:
        try:
            rel_or_path = cand.resolve().relative_to(source_ws.resolve()).as_posix()
        except (ValueError, OSError):
            rel_or_path = str(cand)

    excerpt = text[:1200] + ("\n...[checkpoint truncated]" if len(text) > 1200 else "")
    return rel_or_path, excerpt


def handoff_conversation(
    target: Union[str, Path],
    brief: str,
    *,
    intent: str = "handoff",
    title: Optional[str] = None,
    caller_cid: Optional[str] = None,
    source_ws: Optional[Union[str, Path]] = None,
    from_project: Optional[str] = None,
    role_hint: Optional[str] = None,
    group_id: Optional[str] = None,
    hop: Optional[int] = None,
    max_hops: int = MAX_CROSSTALK_HOPS,
    lineage: Optional[Sequence[str]] = None,
    project_lineage: Optional[Sequence[str]] = None,
    model: str = "flash",
    tags: Optional[Sequence[str]] = None,
    artifacts: Optional[Sequence[str]] = None,
    include_checkpoint: bool = False,
    checkpoint_path: Optional[Union[str, Path]] = None,
    strict: bool = False,
    ensure_project: bool = False,
    config_dir: Optional[Union[str, Path]] = None,
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
    dry_run: bool = False,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Resolves target project, enforces hop/cycle/`.dirtyroom/` guards & secret redaction, and creates a linked conversation."""
    eff_caller_cid = (caller_cid or get_active_conversation_id() or "").strip() or None
    src_ws_path = Path(source_ws).expanduser().resolve() if source_ws is not None and str(source_ws).strip() else None

    target_res = resolve_project_target(target, config_dir=config_dir, ensure=ensure_project, dry_run=dry_run)
    if not target_res.get("success"):
        return _fail_res(
            target_res.get("status", "not_found"),
            target_res.get("error") or f"Unable to resolve target project '{target}'.",
            dry_run=dry_run, candidates=target_res.get("candidates", []), target=target_res,
        )

    target_project_id = target_res["project_id"]
    target_project_name = target_res.get("name") or str(target)
    tgt_ws_path = Path(target_res["workspace_path"]).resolve() if target_res.get("workspace_path") else None

    inbound = read_inbound_baton(src_ws_path, eff_caller_cid) if (src_ws_path and eff_caller_cid) else None
    src_project_label = (
        from_project
        or (inbound.get("to_project") if inbound else None)
        or (src_ws_path.name if src_ws_path else "")
        or "unknown"
    ).strip()
    eff_hop = hop if hop is not None else (int(inbound.get("hop", 0)) + 1 if inbound else 1)
    eff_max_hops = min(int(max_hops), int(inbound.get("max_hops", max_hops))) if inbound else int(max_hops)
    eff_group_id = (group_id or (inbound.get("group_id") if inbound else None) or "").strip() or None

    cid_lineage: List[str] = list(dict.fromkeys([
        *(str(x).strip() for x in ((inbound.get("lineage") or []) if inbound else ()) if str(x).strip()),
        *(str(x).strip() for x in (lineage or ()) if str(x).strip()),
        *([eff_caller_cid] if eff_caller_cid else []),
    ]))
    proj_lineage: List[str] = list(dict.fromkeys([
        *(str(x).strip() for x in ((inbound.get("project_lineage") or []) if inbound else ()) if str(x).strip()),
        *(str(inbound.get(k)).strip() for k in ("from_project", "to_project") if inbound and inbound.get(k)),
        *(str(x).strip() for x in (project_lineage or ()) if str(x).strip()),
        *([src_project_label] if not inbound and src_project_label != "unknown" else []),
    ]))

    art_list = [str(a).strip() for a in (artifacts or ()) if str(a).strip()]
    cp_excerpt = ""
    if include_checkpoint or checkpoint_path is not None:
        cp_ref, cp_excerpt = _load_checkpoint_attachment(src_ws_path, eff_caller_cid, checkpoint_path)
        if cp_ref and cp_ref not in art_list:
            art_list.append(cp_ref)

    combined_raw_body = (brief or "").strip()
    if cp_excerpt:
        combined_raw_body = f"{combined_raw_body}\n\n## Attached Checkpoint\n{cp_excerpt}".strip()

    allowed, reason, guard_err = validate_crosstalk_guards(
        hop=eff_hop, max_hops=eff_max_hops, caller_cid=eff_caller_cid,
        from_project=src_project_label, to_project=target_project_name,
        lineage=cid_lineage, project_lineage=proj_lineage, artifacts=art_list, raw_text=combined_raw_body,
    )
    if not allowed:
        return _fail_res("blocked", guard_err or "Crosstalk blocked.", dry_run=dry_run, blocked=True, reason=reason, target=target_res)

    sanitized_body, audit_summary = sanitize_crosstalk_payload(
        combined_raw_body, source_ws=src_ws_path, target_ws=tgt_ws_path, strict=strict,
    )
    if audit_summary.get("dirtyroom_detected"):
        return _fail_res(
            "blocked", "Outbound brief referenced `.dirtyroom/` and was blocked cleanly.",
            dry_run=dry_run, blocked=True, reason="dirtyroom_leakage", redaction=audit_summary, target=target_res,
        )

    next_proj_lineage = list(dict.fromkeys([*proj_lineage, target_project_name]))
    envelope = {
        "from_cid": eff_caller_cid, "from_project": src_project_label, "to_project": target_project_name,
        "intent": intent, "hop": eff_hop, "max_hops": eff_max_hops, "role_hint": role_hint,
        "group_id": eff_group_id, "lineage": cid_lineage, "project_lineage": next_proj_lineage, "artifacts": art_list,
    }
    envelope_header = serialize_crosstalk_envelope(envelope)
    full_prompt = f"{envelope_header}\n\n{sanitized_body}" if sanitized_body else envelope_header
    resolved_title = (title or f"[{intent}] {target_project_name}").strip()
    resolved_tags = list(dict.fromkeys([CROSSTALK_TAG_PREFIX, f"{CROSSTALK_TAG_PREFIX}:{intent}", *(str(t).strip() for t in (tags or ()) if str(t).strip())]))
    create_payload = {"projectId": target_project_id, "title": resolved_title, "model": model, "tags": resolved_tags, "prompt": [{"text": full_prompt}]}

    if dry_run:
        return {
            "success": True, "status": "dry_run", "blocked": False, "dry_run": True, "sandbox_blocked": False,
            "conversation_id": None, "group_id": eff_group_id, "title": resolved_title, "intent": intent,
            "hop": eff_hop, "max_hops": eff_max_hops, "target": target_res, "redaction": audit_summary,
            "envelope": envelope, "prompt_preview": full_prompt[:600], "rpc_payload": create_payload,
            "pill_markdown": None, "cli_command": None,
        }

    create_res = call_conversation_service("CreateConversation", create_payload, ls_address=ls_address, csrf_token=csrf_token, timeout=timeout)
    if not create_res["ok"] or not isinstance(create_res["data"], dict):
        return _fail_res(
            "rpc_error", create_res["error"] or "CreateConversation RPC failed.",
            sandbox_blocked=create_res["sandbox_blocked"], missing_env=create_res["missing_env"],
            connection_refused=create_res["connection_refused"], target=target_res, redaction=audit_summary, envelope=envelope,
        )

    conv_obj = create_res["data"].get("conversation") if isinstance(create_res["data"].get("conversation"), dict) else create_res["data"]
    new_cid = str(conv_obj.get("id") or "").strip()
    if not new_cid:
        return _fail_res("rpc_error", "CreateConversation succeeded without returning conversation.id.", target=target_res, redaction=audit_summary)

    group_warning: Optional[str] = None
    if eff_group_id:
        upd_res = call_conversation_service(
            "UpdateConversation", {"conversationId": new_cid, "annotations": {"conversationGroupId": eff_group_id}},
            ls_address=ls_address, csrf_token=csrf_token, timeout=timeout,
        )
        if not upd_res["ok"]:
            group_warning = upd_res["error"]

    baton_record: Dict[str, Any] = {
        "schema_version": "crosstalk.baton.v1", "conversation_id": new_cid, "from_cid": eff_caller_cid,
        "from_project": src_project_label, "to_project": target_project_name, "to_project_id": target_project_id,
        "intent": intent, "hop": eff_hop, "max_hops": eff_max_hops, "role_hint": role_hint, "group_id": eff_group_id,
        "title": resolved_title, "lineage": cid_lineage, "project_lineage": next_proj_lineage, "artifacts": art_list,
        "brief_preview": sanitized_body[:240], "redaction": audit_summary, "created_at": _utc_now_iso(), "consumed": False,
    }
    inbound_path = _persist_crosstalk_ledger(tgt_ws_path, "inbound", new_cid, baton_record) if (tgt_ws_path and tgt_ws_path.is_dir()) else None
    outbound_path = _persist_crosstalk_ledger(src_ws_path, "outbound", new_cid, baton_record) if (src_ws_path and src_ws_path.is_dir()) else None

    out: Dict[str, Any] = {
        "success": True, "status": "dispatched", "blocked": False, "dry_run": False, "sandbox_blocked": False,
        "conversation_id": new_cid, "group_id": eff_group_id, "title": resolved_title, "intent": intent,
        "hop": eff_hop, "max_hops": eff_max_hops, "target": target_res, "redaction": audit_summary, "envelope": envelope,
        "inbound_baton_path": str(inbound_path) if inbound_path else None,
        "outbound_ledger_path": str(outbound_path) if outbound_path else None,
        "pill_markdown": f"[{resolved_title}](conversation://{new_cid})",
        "cli_command": f"agy --conversation {new_cid}",
        "conversation": conv_obj,
    }
    if group_warning:
        out["group_warning"] = group_warning
    return out


def _resolve_agentapi_exe(explicit_exe: Optional[str] = None) -> Optional[str]:
    if explicit_exe and str(explicit_exe).strip():
        return str(explicit_exe).strip()
    env_exe = os.environ.get("ANTIGRAVITY_AGENTAPI_EXE")
    if env_exe and env_exe.strip():
        return env_exe.strip()
    return shutil.which("agentapi")


def _build_agentapi_send_cmd(
    exe: Optional[str],
    title: Optional[str],
    target_cid: str,
    message: str,
) -> Optional[List[str]]:
    """Builds the CLI command vector for standalone `agentapi` or `language_server agentapi`."""
    exe_str = str(exe).strip() if exe else ""
    if not exe_str:
        return None
    title_args = [f"--title={title.strip()}"] if title and title.strip() else []
    exe_path = Path(exe_str)
    is_ls_wrapper = exe_path.stem.lower().startswith("language_server") or "language_server" in exe_path.name.lower()
    subcmd = ["agentapi", "send-message"] if is_ls_wrapper else ["send-message"]
    return [exe_str, *subcmd, *title_args, target_cid, message]


def steer_conversation(
    target_cid: str,
    message: str,
    *,
    title: Optional[str] = None,
    caller_cid: Optional[str] = None,
    source_ws: Optional[Union[str, Path]] = None,
    target_ws: Optional[Union[str, Path]] = None,
    intent: str = "steer",
    hop: int = 1,
    max_hops: int = MAX_CROSSTALK_HOPS,
    lineage: Optional[Sequence[str]] = None,
    strict: bool = False,
    transport: str = "auto",
    ls_fallback_hook: Optional[Callable[[str, str, Dict[str, Any]], Dict[str, Any]]] = None,
    agentapi_exe: Optional[str] = None,
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
    dry_run: bool = False,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Sends a sanitized steering message via `agentapi` (`language_server agentapi send-message`) or `SendUserCascadeMessage` fallback."""
    t_cid = (target_cid or "").strip()
    if not t_cid:
        return _fail_res("invalid", "target_cid must not be empty.", dry_run=dry_run)

    eff_caller_cid = (caller_cid or get_active_conversation_id() or "").strip() or None
    src_ws_path = Path(source_ws).expanduser().resolve() if source_ws is not None and str(source_ws).strip() else None
    tgt_ws_path = Path(target_ws).expanduser().resolve() if target_ws is not None and str(target_ws).strip() else None

    allowed, reason, guard_err = validate_crosstalk_guards(
        hop=hop, max_hops=max_hops, caller_cid=eff_caller_cid, target_cid=t_cid, lineage=lineage, raw_text=message or "",
    )
    if not allowed:
        return _fail_res("blocked", guard_err or "Steer blocked.", dry_run=dry_run, blocked=True, reason=reason, conversation_id=t_cid)

    sanitized_msg, audit_summary = sanitize_crosstalk_payload(message or "", source_ws=src_ws_path, target_ws=tgt_ws_path, strict=strict)
    if audit_summary.get("dirtyroom_detected"):
        return _fail_res(
            "blocked", "Outbound steer message referenced `.dirtyroom/` and was blocked cleanly.",
            dry_run=dry_run, blocked=True, reason="dirtyroom_leakage", conversation_id=t_cid, redaction=audit_summary,
        )

    exe = _resolve_agentapi_exe(agentapi_exe)
    cmd = _build_agentapi_send_cmd(exe, title, t_cid, sanitized_msg)
    pill_markdown = f"[{(title or f'Conversation {t_cid[:8]}').strip()}](conversation://{t_cid})"
    cli_command = f"agy --conversation {t_cid}"

    if dry_run:
        return {
            "success": True, "status": "dry_run", "blocked": False, "dry_run": True, "sandbox_blocked": False,
            "conversation_id": t_cid, "transport": transport, "command": cmd, "redaction": audit_summary,
            "message_preview": sanitized_msg[:240], "pill_markdown": pill_markdown, "cli_command": cli_command,
        }

    agentapi_err: Optional[str] = None
    agentapi_sandbox = False
    if transport in ("auto", "agentapi") and cmd is not None:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=float(timeout), check=False)
            combined_out = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
            if proc.returncode == 0:
                return {
                    "success": True, "status": "sent", "blocked": False, "dry_run": False, "sandbox_blocked": False,
                    "conversation_id": t_cid, "transport_used": "agentapi", "stdout": proc.stdout, "stderr": proc.stderr,
                    "redaction": audit_summary, "pill_markdown": pill_markdown, "cli_command": cli_command,
                }
            agentapi_sandbox = is_sandbox_refusal(None, combined_out)
            agentapi_err = combined_out or f"agentapi exited with code {proc.returncode}"
        except (OSError, subprocess.SubprocessError) as exc:
            agentapi_sandbox = is_sandbox_refusal(None, str(exc))
            agentapi_err = str(exc)

        if transport == "agentapi" and ls_fallback_hook is None:
            return _fail_res(
                "transport_error", agentapi_err, sandbox_blocked=agentapi_sandbox,
                conversation_id=t_cid, transport_used="agentapi", redaction=audit_summary, cli_command=cli_command,
            )

    if ls_fallback_hook is not None:
        hook_res = ls_fallback_hook(t_cid, sanitized_msg, {"title": title, "intent": intent, "ls_address": ls_address, "csrf_token": csrf_token, "timeout": timeout})
        ok = bool(hook_res.get("success", hook_res.get("ok", False)))
        return {
            "success": ok, "status": "sent" if ok else "transport_error", "blocked": False, "dry_run": False,
            "sandbox_blocked": bool(hook_res.get("sandbox_blocked", False) or agentapi_sandbox),
            "conversation_id": t_cid, "transport_used": hook_res.get("transport_used", "ls_fallback_hook"),
            "redaction": audit_summary, "pill_markdown": pill_markdown, "cli_command": cli_command,
            "data": hook_res.get("data"), "error": hook_res.get("error") or (None if ok else agentapi_err),
        }

    addr, token = resolve_ls_credentials(ls_address, csrf_token)
    if addr and token and transport in ("auto", "ls_rpc"):
        ls_res = call_ls_service(
            "SendUserCascadeMessage", {"cascadeId": t_cid, "items": [{"text": sanitized_msg}]},
            ls_address=addr, csrf_token=token, timeout=timeout,
        )
        return {
            "success": ls_res["ok"], "status": "sent" if ls_res["ok"] else "rpc_error", "blocked": False, "dry_run": False,
            "sandbox_blocked": bool(ls_res["sandbox_blocked"] or agentapi_sandbox),
            "conversation_id": t_cid, "transport_used": "ls_rpc", "redaction": audit_summary,
            "pill_markdown": pill_markdown, "cli_command": cli_command, "data": ls_res["data"],
            "error": ls_res["error"] or (None if ls_res["ok"] else agentapi_err),
        }

    if agentapi_err:
        return _fail_res(
            "transport_error", agentapi_err, sandbox_blocked=agentapi_sandbox,
            conversation_id=t_cid, transport_used="agentapi", redaction=audit_summary, cli_command=cli_command,
        )
    return _fail_res(
        "unavailable", "No available steer transport (agentapi binary not found and LS credentials missing).",
        conversation_id=t_cid, redaction=audit_summary, cli_command=cli_command,
    )


def archive_conversation(
    conversation_id: str,
    *,
    archived: bool = True,
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
    dry_run: bool = False,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Soft-archives or unarchives a conversation via `ConversationService/UpdateConversation`."""
    cid = (conversation_id or "").strip()
    if not cid:
        return _fail_res("invalid", "conversation_id must not be empty.", dry_run=dry_run, conversation_id=cid, archived=bool(archived))

    payload = {"conversationId": cid, "annotations": {"archived": bool(archived)}}
    if dry_run:
        return {
            "success": True, "status": "dry_run", "conversation_id": cid, "archived": bool(archived),
            "dry_run": True, "sandbox_blocked": False, "rpc_method": "UpdateConversation", "rpc_payload": payload,
        }

    res = call_conversation_service("UpdateConversation", payload, ls_address=ls_address, csrf_token=csrf_token, timeout=timeout)
    return {
        "success": res["ok"],
        "status": ("archived" if archived else "unarchived") if res["ok"] else "rpc_error",
        "conversation_id": cid, "archived": bool(archived), "dry_run": False,
        "sandbox_blocked": res["sandbox_blocked"], "missing_env": res["missing_env"],
        "connection_refused": res["connection_refused"], "conversation": res["data"], "error": res["error"],
    }


__all__ = [
    "CROSSTALK_LEDGER_SUBDIR",
    "CROSSTALK_TAG_PREFIX",
    "HARD_MAX_CROSSTALK_HOPS",
    "MAX_CROSSTALK_HOPS",
    "archive_conversation",
    "call_conversation_service",
    "call_ls_service",
    "discover_conversations",
    "get_conversation",
    "handoff_conversation",
    "inspect_conversation_steps",
    "parse_crosstalk_envelope",
    "read_inbound_baton",
    "serialize_crosstalk_envelope",
    "steer_conversation",
    "validate_crosstalk_guards",
]
