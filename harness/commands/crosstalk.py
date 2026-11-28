# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Crosstalk CLI Command (`agyis crosstalk {list,search,status,inspect,widget,handoff,send,archive}`).

Bridges top-level Antigravity conversations across Desktop (`antigravity`), CLI
(`antigravity-cli`), and registered workspace projects with D6 hygiene/redaction,
hop/cycle guards, Generative UI widgets, and clickable `conversation://` pills.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

from harness.delivery.crosstalk import (
    CROSSTALK_LEDGER_SUBDIR,
    HARD_MAX_CROSSTALK_HOPS,
    MAX_CROSSTALK_HOPS,
    archive_conversation,
    discover_conversations,
    get_conversation,
    handoff_conversation,
    inspect_conversation_steps,
    read_inbound_baton,
    steer_conversation,
)
from harness.utils import theme
from harness.utils.context import get_active_conversation_id, get_active_workspace
from harness.utils.state import atomic_write_text
from harness.ux import (
    conversation_pill,
    is_desktop_surface,
    render_cli_fallback,
    render_crosstalk_widget,
    render_pill_strip,
)


def _emit_error(message: str, *, is_json: bool, **extra: Any) -> int:
    """Emit a structured JSON or themed stderr error and return exit code 1."""
    if is_json:
        payload: Dict[str, Any] = {"success": False, "status": "error", "error": message}
        payload.update(extra)
        print(json.dumps(payload, indent=2))
    else:
        sys.stderr.write(theme.badge("FAIL", f"Error: {message}", stream=sys.stderr) + "\n")
    return 1


def _resolve_ui_surface(explicit: Optional[str] = None) -> str:
    """Resolve effective UX surface string ('desktop' or 'cli')."""
    if explicit and explicit.strip().lower() != "auto":
        return "desktop" if is_desktop_surface(explicit) else "cli"
    return "desktop" if is_desktop_surface(None) else "cli"


def _resolve_ws_and_cfg(args: argparse.Namespace) -> Tuple[Path, Optional[Path]]:
    """Resolve workspace Path and optional config_dir from CLI namespace."""
    ws_arg = getattr(args, "workspace", None)
    ws = Path(ws_arg).expanduser().resolve() if ws_arg else get_active_workspace()
    cfg_arg = getattr(args, "config_dir", None)
    cfg = Path(cfg_arg).expanduser().resolve() if cfg_arg else None
    return ws, cfg


def _visibility_meta(args: argparse.Namespace) -> Tuple[str, str, bool, str]:
    """Compute (src_vis, tgt_vis, is_strict, visibility_label) from CLI args."""
    src_vis = str(getattr(args, "source_visibility", "private") or "private").strip().lower()
    tgt_vis = str(getattr(args, "target_visibility", "private") or "private").strip().lower()
    is_priv_to_oss = src_vis == "private" and tgt_vis == "oss"
    strict = bool(getattr(args, "strict", False)) or is_priv_to_oss
    if is_priv_to_oss:
        label = "Private -> OSS"
    elif src_vis == "oss" and tgt_vis == "oss":
        label = "OSS -> OSS"
    elif src_vis == "oss" and tgt_vis == "private":
        label = "OSS -> Private"
    else:
        label = "Private -> Private"
    return src_vis, tgt_vis, strict, label


def _handle_list_or_search(args: argparse.Namespace, *, action: str, is_json: bool) -> int:
    """Handle `agyis crosstalk list` and `agyis crosstalk search`."""
    _, cfg = _resolve_ws_and_cfg(args)
    if action == "search":
        query = getattr(args, "query_flag", None) or getattr(args, "query_arg", None)
    else:
        query = getattr(args, "query", None)

    project = getattr(args, "project", None)
    raw_surface = str(getattr(args, "surface", "all") or "all").strip().lower()
    query_surface = None if raw_surface == "all" else raw_surface
    include_archived = bool(getattr(args, "include_archived", False))
    include_children = bool(getattr(args, "include_children", False))
    limit = max(1, int(getattr(args, "limit", 20) or 20))

    res = discover_conversations(
        query=query,
        target=project,
        surface=query_surface,
        include_archived=include_archived,
        include_children=include_children,
        limit=limit,
        config_dir=cfg,
    )
    ui_surface = _resolve_ui_surface("auto")
    res["detected_surface"] = ui_surface

    if is_json:
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if not res.get("success"):
        return _emit_error(str(res.get("error") or "Failed discovering conversations."), is_json=False)

    convs = res.get("conversations") or []
    subtitle = f"Surface: {ui_surface} · Query: {query or '*'} · Filter: {raw_surface}"
    print(
        theme.banner(
            "Agyis Crosstalk Conversations",
            subtitle=subtitle,
            badge_label=f"{len(convs)} FOUND",
            status="PASS" if convs else "INFO",
        )
    )
    if res.get("sandbox_blocked"):
        print("  " + theme.badge("WARN", "LS HTTP blocked by sandbox; displaying local SQLite summary index."))
    if not convs:
        print("  " + theme.badge("INFO", "No matching conversations discovered."))
        print(theme.rule("━"))
        return 0

    rows: List[List[str]] = []
    for item in convs:
        cid = str(item.get("conversation_id") or "")
        title = str(item.get("title") or "").strip() or (f"Thread {cid[:8]}" if cid else "-")
        pill = conversation_pill(cid, title, surface=ui_surface) if cid else title
        surfs = ",".join(item.get("surfaces") or [item.get("surface") or "-"])
        proj = str(item.get("project_name") or item.get("project_id") or "-")[:24]
        run_state = str(item.get("run_state") or item.get("status") or "-").replace("RUN_STATE_", "")
        updated = str(item.get("last_modified_time") or "-")[:19]
        rows.append([pill, surfs, proj, run_state, updated])

    print(theme.format_table(["Conversation", "Surface", "Project", "State", "Updated"], rows))
    print(theme.rule("━"))
    return 0


def _read_status_baton(ws: Path, session_id: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Dict[str, int]]:
    """Read inbound baton (CID-scoped or inbound_latest.json) and ledger file counts."""
    baton: Optional[Dict[str, Any]] = read_inbound_baton(ws, session_id) if session_id else None
    xt_dir = ws / CROSSTALK_LEDGER_SUBDIR
    if baton is None:
        latest_file = xt_dir / "inbound_latest.json"
        if latest_file.is_file():
            try:
                parsed = json.loads(latest_file.read_text(encoding="utf-8", errors="replace"))
                if isinstance(parsed, dict):
                    baton = parsed
            except (OSError, json.JSONDecodeError, ValueError):
                baton = None

    counts = {"inbound": 0, "outbound": 0}
    if xt_dir.is_dir():
        try:
            for entry in xt_dir.iterdir():
                if not entry.is_file() or entry.suffix != ".json":
                    continue
                if entry.name.startswith("inbound_"):
                    counts["inbound"] += 1
                elif entry.name.startswith("outbound_"):
                    counts["outbound"] += 1
        except OSError:
            pass
    return baton, counts


def _handle_status(args: argparse.Namespace, *, is_json: bool) -> int:
    """Handle `agyis crosstalk status`."""
    ws, cfg = _resolve_ws_and_cfg(args)
    session_id = (getattr(args, "session", None) or get_active_conversation_id() or "").strip() or None
    ui_surface = _resolve_ui_surface(getattr(args, "surface", "auto"))
    limit = max(1, int(getattr(args, "limit", 5) or 5))

    baton, ledger_counts = _read_status_baton(ws, session_id)
    active_hop = int(baton.get("hop", 0) or 0) if baton else 0
    max_hops = int(baton.get("max_hops", MAX_CROSSTALK_HOPS) or MAX_CROSSTALK_HOPS) if baton else MAX_CROSSTALK_HOPS

    disc = discover_conversations(limit=limit, config_dir=cfg)
    recent_threads = disc.get("conversations") or [] if disc.get("success") else []

    out: Dict[str, Any] = {
        "success": True,
        "status": "ok",
        "workspace": str(ws),
        "session_id": session_id,
        "detected_surface": ui_surface,
        "active_hop": active_hop,
        "max_hops": max_hops,
        "hard_max_hops": HARD_MAX_CROSSTALK_HOPS,
        "inbound_baton": baton,
        "ledger_counts": ledger_counts,
        "recent_count": len(recent_threads),
        "recent_threads": recent_threads,
        "sandbox_blocked": bool(disc.get("sandbox_blocked")),
    }
    if is_json:
        print(json.dumps(out, indent=2))
        return 0

    print(
        theme.banner(
            "Agyis Crosstalk Status",
            subtitle=f"Workspace: {ws} · Surface: {ui_surface}",
            badge_label=f"HOP {active_hop}/{max_hops}",
            status="INFO",
        )
    )
    print(f"• Session ID     : {session_id or '(unset)'}")
    print(f"• Surface        : {ui_surface}")
    print(f"• Hop Budget     : {active_hop}/{max_hops} (hard cap: {HARD_MAX_CROSSTALK_HOPS})")
    print(f"• Baton Ledgers  : {ledger_counts['inbound']} inbound, {ledger_counts['outbound']} outbound")
    if baton:
        from_cid = str(baton.get("from_cid") or "").strip()
        origin = conversation_pill(from_cid, baton.get("title") or from_cid, surface=ui_surface) if from_cid else str(baton.get("from_project") or "origin")
        print(f"• Inbound Baton  : {origin} ({baton.get('from_project') or '?'} -> {baton.get('to_project') or '?'}, consumed={bool(baton.get('consumed'))})")
    else:
        print("• Inbound Baton  : None active")

    if recent_threads:
        print("• Recent Threads :")
        for item in recent_threads:
            cid = str(item.get("conversation_id") or "")
            label = str(item.get("title") or cid or "untitled")
            pill = conversation_pill(cid, label, surface=ui_surface) if cid else label
            print(f"  - {pill} [{item.get('surface', '-')}]")
    print(theme.rule("━"))
    return 0


def _handle_inspect(args: argparse.Namespace, *, is_json: bool) -> int:
    """Handle `agyis crosstalk inspect <conversation_id>`."""
    _, cfg = _resolve_ws_and_cfg(args)
    cid = str(getattr(args, "conversation_id", "") or "").strip()
    steps_limit = max(1, int(getattr(args, "steps", 20) or 20))
    strict = bool(getattr(args, "strict", False))

    res = get_conversation(cid, include_steps=True, tail=steps_limit, config_dir=cfg)
    if strict and res.get("success"):
        res["steps"] = inspect_conversation_steps(cid, tail=steps_limit, config_dir=cfg, strict=True)

    if is_json:
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if not res.get("success"):
        return _emit_error(str(res.get("error") or f"Conversation '{cid}' not found."), is_json=False)

    conv = res.get("conversation") or {}
    steps_info = res.get("steps") or {}
    steps = steps_info.get("steps") or []
    ui_surface = _resolve_ui_surface("auto")
    pill = conversation_pill(cid, conv.get("title") or cid, surface=ui_surface)

    print(
        theme.banner(
            "Agyis Crosstalk Thread Inspection",
            subtitle=pill,
            badge_label=f"{len(steps)} STEPS",
            status="PASS",
        )
    )
    print(f"• Project / State: {conv.get('project_name') or conv.get('project_id') or '-'} · {conv.get('run_state') or '-'}")
    print(f"• Surfaces       : {', '.join(conv.get('surfaces') or [conv.get('surface') or '-'])}")
    if steps_info.get("hydrated_step_indices"):
        print(f"• Full Hydrated  : steps {steps_info['hydrated_step_indices']}")
    for st in steps:
        idx = st.get("step_index")
        stype = st.get("type") or "-"
        preview = str(st.get("content") or st.get("prompt") or st.get("error") or "")[:120].replace("\n", " ")
        print(f"  [{idx}] ({stype}) {preview}")
    print(theme.rule("━"))
    return 0


def _load_widget_payload(args: argparse.Namespace, ws: Path, cfg: Optional[Path]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Load and merge JSON payload from --payload (file, stdin '-', or JSON) + inline flags."""
    raw_payload = getattr(args, "payload", None)
    data: Dict[str, Any] = {}
    if raw_payload is not None and str(raw_payload).strip():
        raw_s = str(raw_payload).strip()
        try:
            if raw_s == "-":
                parsed = json.loads(sys.stdin.read())
            elif not raw_s.startswith("{") and Path(raw_s).expanduser().is_file():
                parsed = json.loads(Path(raw_s).expanduser().read_text(encoding="utf-8"))
            else:
                parsed = json.loads(raw_s)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return None, f"Invalid --payload JSON: {exc}"
        if not isinstance(parsed, dict):
            return None, "--payload JSON must decode to a JSON object."
        data = dict(parsed)

    title = getattr(args, "title", None)
    summary = getattr(args, "summary", None)
    from_proj = getattr(args, "from_project", None)
    to_proj = getattr(args, "to_project", None)

    if title or summary:
        existing_goal = data.get("goal")
        goal_obj = dict(existing_goal) if isinstance(existing_goal, dict) else (
            {"title": str(existing_goal)} if existing_goal else {}
        )
        if title:
            goal_obj["title"] = title
        if summary:
            goal_obj["line"] = summary
        data["goal"] = goal_obj

    if from_proj or to_proj:
        route_obj = dict(data.get("route")) if isinstance(data.get("route"), dict) else {}
        if from_proj:
            route_obj["from_project"] = from_proj
        if to_proj:
            route_obj["to_project"] = to_proj
        data["route"] = route_obj

    kind = str(getattr(args, "kind", "constellation") or "constellation").strip().lower()
    if kind == "constellation" and "entities" not in data and not raw_payload:
        disc = discover_conversations(limit=6, config_dir=cfg)
        convs = disc.get("conversations") or [] if disc.get("success") else []
        data["entities"] = [
            {
                "id": c.get("conversation_id"),
                "title": c.get("title") or c.get("conversation_id"),
                "outcome": "active" if c.get("run_state") == "RUN_STATE_RUNNING" else "idle",
                "run_state": c.get("run_state") or "RUN_STATE_IDLE",
                "surface": c.get("surface") or "desktop",
                "project": c.get("project_name") or c.get("project_id") or ws.name,
                "activity": c.get("preview") or "",
                "updated_at": c.get("last_modified_time") or "",
            }
            for c in convs
        ]
    return data, None


def _handle_widget(args: argparse.Namespace, *, is_json: bool) -> int:
    """Handle `agyis crosstalk widget`."""
    ws, cfg = _resolve_ws_and_cfg(args)
    kind = str(getattr(args, "kind", "constellation") or "constellation").strip().lower()
    raw_surface = str(getattr(args, "surface", "auto") or "auto").strip().lower()
    eff_surface = None if raw_surface == "auto" else raw_surface

    view_data, err = _load_widget_payload(args, ws, cfg)
    if err or view_data is None:
        return _emit_error(err or "Unable to construct widget payload.", is_json=is_json)

    artifact_dir_arg = getattr(args, "artifact_dir", None)
    write_flag = bool(getattr(args, "write", False))
    dry_run = bool(getattr(args, "dry_run", False))
    eff_artifact_dir: Optional[Path] = None
    if artifact_dir_arg is not None:
        eff_artifact_dir = Path(artifact_dir_arg).expanduser().resolve()
    elif write_flag:
        eff_artifact_dir = ws / CROSSTALK_LEDGER_SUBDIR

    rendered = render_crosstalk_widget(
        view_data,
        mode=kind,
        artifact_dir=eff_artifact_dir,
        surface=eff_surface,
    )

    written_path: Optional[str] = None
    if eff_artifact_dir is not None and not dry_run:
        eff_artifact_dir.mkdir(parents=True, exist_ok=True)
        out_path = eff_artifact_dir / rendered["suggested_filename"]
        atomic_write_text(out_path, rendered["html"])
        written_path = str(out_path)

    out_payload = {
        "success": True,
        "status": "ok",
        "kind": kind,
        "written_path": written_path,
        "dry_run": dry_run,
        **rendered,
    }
    if is_json:
        print(json.dumps(out_payload, indent=2))
        return 0

    if rendered["is_desktop"]:
        print(rendered["embed_hint"])
        links = rendered.get("json_payload", {}).get("links") or []
        strip = render_pill_strip(item.get("markdown", "") for item in links[:4])
        if strip:
            print(strip)
        if written_path:
            print(f"Widget HTML: {written_path}")
    else:
        print(rendered["fallback_markdown"])
    return 0


def _handle_handoff(args: argparse.Namespace, *, is_json: bool) -> int:
    """Handle `agyis crosstalk handoff` with D6 hygiene/redaction/hop guards."""
    ws, cfg = _resolve_ws_and_cfg(args)
    to_val = getattr(args, "to", None)
    proj_val = getattr(args, "project", None)
    new_flag = bool(getattr(args, "new", False))
    target = to_val or proj_val or (str(ws) if new_flag else None)
    if not target:
        return _emit_error("Specify --to <project>, --project <project>, or --new.", is_json=is_json)

    src_vis, tgt_vis, strict, vis_label = _visibility_meta(args)
    dry_run = bool(getattr(args, "dry_run", False)) or (not bool(getattr(args, "send", False)))
    ensure_proj = bool(getattr(args, "ensure_project", False)) or (new_flag and not to_val and not proj_val)

    summary = str(getattr(args, "summary", None) or "").strip()
    task = str(getattr(args, "task", None) or "").strip()
    brief_arg = str(getattr(args, "brief", None) or "").strip()
    if brief_arg:
        brief = brief_arg
    elif summary and task:
        brief = f"## Summary\n{summary}\n\n## Task\n{task}"
    else:
        brief = summary or task or str(getattr(args, "title", None) or "").strip()

    tags_raw = getattr(args, "tags", None)
    tags = [t.strip() for t in str(tags_raw).split(",") if t.strip()] if tags_raw else None
    checkpoint = getattr(args, "checkpoint", None)
    include_cp = bool(getattr(args, "include_checkpoint", False)) or (checkpoint is not None)

    res = handoff_conversation(
        target,
        brief,
        intent="succession" if (new_flag and not to_val) else "handoff",
        title=getattr(args, "title", None),
        source_ws=ws,
        role_hint=getattr(args, "role", None),
        group_id=getattr(args, "group_id", None),
        hop=getattr(args, "hops", None),
        max_hops=int(getattr(args, "max_hops", MAX_CROSSTALK_HOPS) or MAX_CROSSTALK_HOPS),
        model=str(getattr(args, "model", "flash") or "flash"),
        tags=tags,
        include_checkpoint=include_cp,
        checkpoint_path=checkpoint,
        strict=strict,
        ensure_project=ensure_proj,
        config_dir=cfg,
        dry_run=dry_run,
    )
    res["source_visibility"] = src_vis
    res["target_visibility"] = tgt_vis
    res["visibility_crossing"] = vis_label
    res["send_requested"] = bool(getattr(args, "send", False))

    if is_json:
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if not res.get("success"):
        return _emit_error(str(res.get("error") or "Crosstalk handoff failed."), is_json=False)

    ui_surface = _resolve_ui_surface("auto")
    red = res.get("redaction") or {}
    target_info = res.get("target") or {}
    view_payload = {
        "goal": {"title": res.get("title") or "Crosstalk Handoff", "line": summary or task},
        "route": {
            "from_project": ws.name,
            "to_project": target_info.get("name") or str(target),
            "visibility": vis_label,
            "hop": res.get("hop", 1),
            "max_hops": res.get("max_hops", MAX_CROSSTALK_HOPS),
            "intent": res.get("intent", "handoff"),
        },
        "redaction": {
            "tokens_scrubbed": red.get("secrets_redacted", 0),
            "paths_anonymized": red.get("paths_anonymized", 0),
            "blocked_files": red.get("blocked_categories") or [],
            "passed": not bool(res.get("blocked")),
            "cli_command": res.get("cli_command") or "",
        },
    }
    print(render_cli_fallback(view_payload, mode="preflight", surface=ui_surface))
    if res.get("dry_run"):
        print("Dry-run preflight complete. Re-run with --send to dispatch live CreateConversation RPC.")
    elif res.get("conversation_id"):
        print("Dispatched: " + conversation_pill(res["conversation_id"], res.get("title"), surface=ui_surface))
    return 0


def _handle_send(args: argparse.Namespace, *, is_json: bool) -> int:
    """Handle `agyis crosstalk send`."""
    ws, _ = _resolve_ws_and_cfg(args)
    to_cid = getattr(args, "to_cid", None)
    msg_flag = getattr(args, "message_flag", None)
    pos_1 = getattr(args, "target_pos", None)
    pos_2 = getattr(args, "message_pos", None)

    if to_cid and not msg_flag and pos_1 and not pos_2:
        target_cid, message = to_cid, pos_1
    else:
        target_cid = to_cid or pos_1
        message = msg_flag or pos_2

    if not target_cid or not str(target_cid).strip():
        return _emit_error("Target conversation ID is required (<target> or --to).", is_json=is_json)
    if message is None or not str(message).strip():
        return _emit_error("Message text is required (<message> or --message).", is_json=is_json)

    src_vis, tgt_vis, strict, vis_label = _visibility_meta(args)
    res = steer_conversation(
        str(target_cid).strip(),
        str(message),
        title=getattr(args, "title", None),
        source_ws=ws,
        hop=int(getattr(args, "hops", 1) or 1),
        max_hops=int(getattr(args, "max_hops", MAX_CROSSTALK_HOPS) or MAX_CROSSTALK_HOPS),
        strict=strict,
        transport=str(getattr(args, "transport", "auto") or "auto"),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    res["source_visibility"] = src_vis
    res["target_visibility"] = tgt_vis
    res["visibility_crossing"] = vis_label

    if is_json:
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if not res.get("success"):
        return _emit_error(str(res.get("error") or "Crosstalk send failed."), is_json=False)

    ui_surface = _resolve_ui_surface("auto")
    pill = conversation_pill(res["conversation_id"], getattr(args, "title", None), surface=ui_surface)
    badge = "[DRY-RUN] Verified steer payload" if res.get("dry_run") else f"Sent via {res.get('transport_used', 'crosstalk')}"
    print(theme.badge("PASS", f"{badge}: {pill}"))
    return 0


def _handle_archive(args: argparse.Namespace, *, is_json: bool) -> int:
    """Handle `agyis crosstalk archive` (non-destructive soft-archive only)."""
    cid = str(getattr(args, "conversation_id", "") or "").strip()
    unarchive = bool(getattr(args, "unarchive", False))
    dry_run = bool(getattr(args, "dry_run", False))

    res = archive_conversation(cid, archived=not unarchive, dry_run=dry_run)
    if is_json:
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if not res.get("success"):
        return _emit_error(str(res.get("error") or "Crosstalk archive failed."), is_json=False)

    verb = "unarchive" if unarchive else "archive"
    prefix = "[DRY-RUN] Would " if dry_run else "Completed "
    print(theme.badge("PASS", f"{prefix}{verb} conversation '{cid}' (soft UpdateConversation)."))
    return 0


def cmd_crosstalk(args: argparse.Namespace) -> int:
    """Dispatch `agyis crosstalk {list,search,status,inspect,widget,handoff,send,archive}`."""
    action = getattr(args, "crosstalk_action", None) or "status"
    is_json = bool(getattr(args, "json", False))

    if action in ("list", "search"):
        return _handle_list_or_search(args, action=action, is_json=is_json)
    if action == "status":
        return _handle_status(args, is_json=is_json)
    if action == "inspect":
        return _handle_inspect(args, is_json=is_json)
    if action == "widget":
        return _handle_widget(args, is_json=is_json)
    if action == "handoff":
        return _handle_handoff(args, is_json=is_json)
    if action == "send":
        return _handle_send(args, is_json=is_json)
    if action == "archive":
        return _handle_archive(args, is_json=is_json)
    return _emit_error(f"Unknown crosstalk action: {action}", is_json=is_json)


__all__ = ["cmd_crosstalk"]
