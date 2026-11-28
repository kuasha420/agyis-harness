# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Generative UI Widget Renderer & CLI Fallback Formatter for Crosstalk (Track A).

Loads externalized monochrome HTML templates from `harness.ux.assets` via
`importlib.resources`, normalizes and validates the typed JSON view model
(SEP-1865 MCP Apps compatible), escapes JSON safely against HTML script breakout,
and produces crisp Unicode/Markdown CLI fallbacks on headless terminals.
"""

from __future__ import annotations

import importlib.resources as ir
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from harness.ux.pills import _validate_conversation_id, conversation_pill, is_desktop_surface

_TEMPLATE_FILES = {
    "preflight": "crosstalk_preflight.html",
    "constellation": "crosstalk_constellation.html",
}

_ATTENTION_RANK = {
    "decision": 0,
    "failure": 1,
    "review": 2,
    "stuck": 3,
    "quota": 4,
    "error": 4,
    "fyi": 5,
}

_SEVERITY_RANK = {"high": 0, "med": 1, "medium": 1, "low": 2}

_OUTCOME_ORDER = ("blocked", "active", "idle", "done")

_BLOCKED_STATES = frozenset({"blocked", "failed", "error", "stuck", "run_state_cancelling"})
_ACTIVE_STATES = frozenset({"active", "running", "in_progress", "run_state_running"})
_DONE_STATES = frozenset({"done", "verified", "completed", "passed"})
_ALLOWED_LINK_SCHEMES = ("conversation://", "file://", "agyis://", "https://", "http://")
_UNSAFE_URI_MARKERS = ("javascript:", "data:", "vbscript:")


def _is_safe_link_uri(uri: str) -> bool:
    """Allows only safe deep-link and HTTP(S) schemes without whitespace or control chars."""
    if not uri:
        return False
    lowered = uri.strip().lower()
    if any(ch.isspace() or ord(ch) < 32 for ch in lowered):
        return False
    return lowered.startswith(_ALLOWED_LINK_SCHEMES)


def load_ux_asset(filename: str) -> str:
    """Loads a static template asset from `harness.ux.assets` via importlib.resources."""
    clean_name = Path(str(filename)).name
    if clean_name != str(filename) or not clean_name:
        raise ValueError(f"Invalid UX asset filename: {filename!r}")
    return ir.files("harness.ux.assets").joinpath(clean_name).read_text(encoding="utf-8")


def _coerce_int(value: Any, default: int = 0) -> int:
    """Safely converts numeric-like input to int without raising."""
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_text(value: Any, max_len: int = 240) -> str:
    """Normalizes single-line display text by collapsing control chars and whitespace."""
    text = re.sub(r"[\r\n\t\x00-\x1f\x7f]+", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _normalize_refs(raw_refs: Any) -> List[Dict[str, str]]:
    """Normalizes backing citation references (`#step`, `seq`, commit, test run)."""
    if not isinstance(raw_refs, list):
        return []
    out: List[Dict[str, str]] = []
    for item in raw_refs:
        if isinstance(item, str):
            val = _clean_text(item, 160)
            if val:
                out.append({"kind": "ref", "label": val, "target": val})
        elif isinstance(item, Mapping):
            seq = item.get("seq")
            target = _clean_text(item.get("target") or item.get("path") or (f"#{seq}" if seq is not None else ""), 160)
            label = _clean_text(item.get("label") or target or (f"#{seq}" if seq is not None else ""), 120)
            kind = _clean_text(item.get("kind") or ("seq" if seq is not None else "ref"), 32) or "ref"
            if label or target:
                out.append({"kind": kind, "label": label or target, "target": target or label})
    return out


def _normalize_outcome(raw_outcome: Any, raw_run_state: Any, refs: List[Dict[str, str]]) -> Tuple[str, bool]:
    """
    Maps raw outcome/run_state onto `blocked|active|idle|done`.
    Enforces strict citation discipline: never marks `done`/`verified` without refs.
    """
    cand = _clean_text(raw_outcome, 40).lower()
    state = _clean_text(raw_run_state, 40).lower()
    token = cand or state

    if token in _DONE_STATES:
        if refs:
            return "done", False
        return "idle", True
    if token in _BLOCKED_STATES or state in _BLOCKED_STATES:
        return "blocked", False
    if token in _ACTIVE_STATES or state in _ACTIVE_STATES:
        return "active", False
    if token in ("idle", "queued", "pending", "archived", "cli-only", "run_state_idle"):
        return "idle", False
    return "idle", False


def _normalize_entity(raw: Mapping[str, Any], default_max_hops: int) -> Dict[str, Any]:
    """Normalizes a thread/conversation entity for the Constellation view model."""
    raw_id = _clean_text(raw.get("id") or raw.get("conversation_id") or raw.get("cid"), 128)
    refs = _normalize_refs(raw.get("refs"))
    outcome, unverified_claim = _normalize_outcome(raw.get("outcome") or raw.get("state"), raw.get("run_state"), refs)
    raw_surface = _clean_text(raw.get("surface") or "desktop", 24).lower()
    surface = "cli" if "cli" in raw_surface or raw_surface in ("terminal", "tui", "headless") else "desktop"

    title = _clean_text(raw.get("title") or raw.get("summary") or raw_id or "Untitled thread", 120)
    run_state = _clean_text(raw.get("run_state") or outcome.upper(), 32).upper()
    if unverified_claim and run_state in ("DONE", "VERIFIED", "COMPLETED"):
        run_state = "IDLE"

    hop = max(0, _coerce_int(raw.get("hop"), 0))
    max_hops = max(1, _coerce_int(raw.get("max_hops"), default_max_hops))
    generation = max(0, _coerce_int(raw.get("generation"), 0))

    safe_cid = ""
    pill = ""
    cli_command = ""
    raw_cli = _clean_text(raw.get("cli_command"), 200)
    if raw_id:
        try:
            safe_cid = _validate_conversation_id(raw_id)
            pill = conversation_pill(safe_cid, title, surface="desktop")
            cli_command = raw_cli or f"agy --conversation {safe_cid}"
        except ValueError:
            safe_cid = ""
            if raw_cli and ".." not in raw_cli and not raw_cli.startswith("agy --conversation "):
                cli_command = raw_cli
    elif raw_cli and ".." not in raw_cli:
        cli_command = raw_cli

    return {
        "id": safe_cid,
        "title": title,
        "outcome": outcome,
        "run_state": run_state,
        "surface": surface,
        "project": _clean_text(raw.get("project") or raw.get("project_name"), 80),
        "branch": _clean_text(raw.get("branch"), 80),
        "hop": hop,
        "max_hops": max_hops,
        "generation": generation,
        "archived": bool(raw.get("archived", False)),
        "activity": _clean_text(raw.get("activity") or raw.get("now") or raw.get("note"), 180),
        "updated_at": _clean_text(raw.get("updated_at"), 64),
        "refs": refs,
        "unverified_claim": unverified_claim,
        "cli_command": cli_command,
        "pill": pill or title,
    }


def _normalize_attention(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalizes and ranks an attention item (`decision > failure > review > stuck > quota > fyi`)."""
    kind = _clean_text(raw.get("kind") or "fyi", 24).lower()
    if kind not in _ATTENTION_RANK:
        kind = "fyi"
    severity = _clean_text(raw.get("severity") or ("high" if kind in ("decision", "failure") else "med"), 16).lower()
    if severity not in _SEVERITY_RANK:
        severity = "med"
    return {
        "id": _clean_text(raw.get("id"), 64),
        "kind": kind,
        "severity": severity,
        "title": _clean_text(raw.get("title") or "Attention item", 120),
        "line": _clean_text(raw.get("line") or raw.get("note"), 180),
        "entity_id": _clean_text(raw.get("entity_id") or raw.get("thread_id"), 128),
        "refs": _normalize_refs(raw.get("refs")),
    }


def _normalize_links(entities: List[Dict[str, Any]], raw_links: Any, is_desktop: bool) -> List[Dict[str, str]]:
    """Normalizes clickable deep links plus CLI equivalents from explicit `links` or entities."""
    links: List[Dict[str, str]] = []
    seen_uris = set()

    if isinstance(raw_links, list):
        for item in raw_links:
            if not isinstance(item, Mapping):
                continue
            kind = _clean_text(item.get("kind") or "conversation", 24).lower()
            lid = _clean_text(item.get("id"), 128)
            label = _clean_text(item.get("label") or lid, 120)
            uri = _clean_text(item.get("uri"), 256)
            cli_cmd = _clean_text(item.get("cli_command"), 200)
            markdown = _clean_text(item.get("markdown"), 256)
            if uri and not _is_safe_link_uri(uri):
                continue
            if kind == "conversation" and lid and not uri:
                try:
                    valid_cid = _validate_conversation_id(lid)
                    uri = f"conversation://{valid_cid}"
                    markdown = conversation_pill(valid_cid, label, surface="desktop" if is_desktop else "cli")
                    if not cli_cmd:
                        cli_cmd = f"agy --conversation {valid_cid}"
                except ValueError:
                    continue
            if any(bad in markdown.lower() for bad in _UNSAFE_URI_MARKERS):
                markdown = label
            if uri and uri in seen_uris:
                continue
            if uri:
                seen_uris.add(uri)
            links.append({
                "kind": kind,
                "id": lid,
                "label": label,
                "uri": uri,
                "markdown": markdown or label,
                "cli_command": cli_cmd,
            })

    for ent in entities:
        eid = ent.get("id") or ""
        if not eid:
            continue
        try:
            valid_cid = _validate_conversation_id(eid)
        except ValueError:
            continue
        uri = f"conversation://{valid_cid}"
        if uri in seen_uris:
            continue
        seen_uris.add(uri)
        links.append({
            "kind": "conversation",
            "id": valid_cid,
            "label": ent["title"],
            "uri": uri,
            "markdown": conversation_pill(valid_cid, ent["title"], surface="desktop" if is_desktop else "cli"),
            "cli_command": ent.get("cli_command") or f"agy --conversation {valid_cid}",
        })
    return links


def normalize_crosstalk_view_data(
    view_data: Mapping[str, Any],
    mode: Optional[str] = None,
    *,
    surface: Optional[str] = None,
) -> Dict[str, Any]:
    """Validates and normalizes crosstalk widget input into the typed view schema."""
    if not isinstance(view_data, Mapping):
        raise TypeError("view_data must be a mapping")

    raw_mode = mode if mode is not None else view_data.get("mode")
    effective_mode = str(raw_mode or "constellation").strip().lower()
    if effective_mode not in _TEMPLATE_FILES:
        raise ValueError(f"Unsupported crosstalk widget mode: {effective_mode!r}")

    desktop = is_desktop_surface(surface)
    raw_goal = view_data.get("goal")
    if isinstance(raw_goal, Mapping):
        goal_title = _clean_text(raw_goal.get("title") or view_data.get("headline") or f"Crosstalk {effective_mode.title()}", 120)
        goal_line = _clean_text(raw_goal.get("line") or raw_goal.get("summary") or "", 180)
        goal_status = _clean_text(raw_goal.get("status") or "active", 24).lower()
    else:
        goal_title = _clean_text(raw_goal or view_data.get("headline") or f"Crosstalk {effective_mode.title()}", 120)
        goal_line = _clean_text(view_data.get("summary") or "", 180)
        goal_status = "active"

    raw_route = view_data.get("route") if isinstance(view_data.get("route"), Mapping) else {}
    max_hops = max(1, _coerce_int(raw_route.get("max_hops") or view_data.get("max_hops"), 2))
    route = {
        "from_project": _clean_text(raw_route.get("from_project") or "current", 80),
        "from_branch": _clean_text(raw_route.get("from_branch"), 80),
        "from_cid": _clean_text(raw_route.get("from_cid"), 128),
        "to_project": _clean_text(raw_route.get("to_project") or "target", 80),
        "to_branch": _clean_text(raw_route.get("to_branch"), 80),
        "to_cid": _clean_text(raw_route.get("to_cid"), 128),
        "visibility": _clean_text(raw_route.get("visibility") or "Same-Project", 48),
        "hop": max(0, _coerce_int(raw_route.get("hop"), 1)),
        "max_hops": max_hops,
        "generation": max(0, _coerce_int(raw_route.get("generation"), 1)),
        "role_hint": _clean_text(raw_route.get("role_hint"), 48),
        "intent": _clean_text(raw_route.get("intent") or "handoff", 32),
    }

    raw_red = view_data.get("redaction") if isinstance(view_data.get("redaction"), Mapping) else {}
    blocked_files = [
        _clean_text(p, 160)
        for p in (raw_red.get("blocked_files") if isinstance(raw_red.get("blocked_files"), list) else [])
        if _clean_text(p, 160)
    ]
    warnings = [
        _clean_text(w, 200)
        for w in (raw_red.get("warnings") if isinstance(raw_red.get("warnings"), list) else [])
        if _clean_text(w, 200)
    ]
    redaction = {
        "policy": _clean_text(raw_red.get("policy") or "standard", 32),
        "visibility_crossing": _clean_text(raw_red.get("visibility_crossing") or route["visibility"], 48),
        "tokens_scrubbed": max(0, _coerce_int(raw_red.get("tokens_scrubbed"), 0)),
        "paths_anonymized": max(0, _coerce_int(raw_red.get("paths_anonymized"), 0)),
        "blocked_files": blocked_files,
        "warnings": warnings,
        "passed": bool(raw_red.get("passed", True)),
        "excerpt_preview": str(raw_red.get("excerpt_preview") or "").strip()[:1200],
        "cli_command": _clean_text(raw_red.get("cli_command") or view_data.get("cli_command"), 240),
    }

    raw_entities = view_data.get("entities") if isinstance(view_data.get("entities"), list) else []
    entities = [_normalize_entity(item, max_hops) for item in raw_entities if isinstance(item, Mapping)]
    entities.sort(key=lambda ent: _OUTCOME_ORDER.index(ent["outcome"]) if ent["outcome"] in _OUTCOME_ORDER else 9)

    raw_threads = view_data.get("threads") if isinstance(view_data.get("threads"), list) else []
    threads: List[Dict[str, Any]] = []
    for item in raw_threads:
        if not isinstance(item, Mapping):
            continue
        t_refs = _normalize_refs(item.get("refs"))
        t_outcome, t_unverified = _normalize_outcome(item.get("outcome") or item.get("state"), None, t_refs)
        threads.append({
            "id": _clean_text(item.get("id"), 64),
            "title": _clean_text(item.get("title") or "Thread", 120),
            "goal": _clean_text(item.get("goal"), 160),
            "outcome": t_outcome,
            "now": _clean_text(item.get("now"), 160),
            "entities": [_clean_text(e, 128) for e in (item.get("entities") or []) if _clean_text(e, 128)],
            "attention": [_clean_text(a, 64) for a in (item.get("attention") or []) if _clean_text(a, 64)],
            "refs": t_refs,
            "unverified_claim": t_unverified,
        })

    raw_edges = view_data.get("edges") if isinstance(view_data.get("edges"), list) else []
    edges: List[Dict[str, Any]] = []
    for item in raw_edges:
        if not isinstance(item, Mapping):
            continue
        edges.append({
            "from": _clean_text(item.get("from") or item.get("source"), 128),
            "to": _clean_text(item.get("to") or item.get("target"), 128),
            "kind": _clean_text(item.get("kind") or "handoff", 32),
            "hop": max(0, _coerce_int(item.get("hop"), 0)),
            "label": _clean_text(item.get("label"), 64),
        })

    raw_att = view_data.get("attention") if isinstance(view_data.get("attention"), list) else []
    attention = [_normalize_attention(item) for item in raw_att if isinstance(item, Mapping)]
    attention.sort(key=lambda att: (_ATTENTION_RANK.get(att["kind"], 99), _SEVERITY_RANK.get(att["severity"], 9)))

    raw_arts = view_data.get("artifacts") if isinstance(view_data.get("artifacts"), list) else []
    artifacts: List[Dict[str, str]] = []
    for item in raw_arts:
        if not isinstance(item, Mapping):
            continue
        label = _clean_text(item.get("label") or item.get("path"), 120)
        path = _clean_text(item.get("path"), 240)
        if label or path:
            artifacts.append({
                "label": label or path,
                "path": path,
                "kind": _clean_text(item.get("kind") or "baton", 32),
            })

    links = _normalize_links(entities, view_data.get("links"), desktop)

    return {
        "version": _clean_text(view_data.get("version") or "1.0", 16),
        "mode": effective_mode,
        "goal": {"title": goal_title, "line": goal_line, "status": goal_status},
        "route": route,
        "redaction": redaction,
        "entities": entities,
        "threads": threads,
        "edges": edges,
        "attention": attention,
        "artifacts": artifacts,
        "links": links,
    }


def _safe_json_for_html_script(payload: Mapping[str, Any]) -> str:
    """Serializes JSON with HTML-safe escapes so `</script>` cannot break out of script tags."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        raw.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_cli_fallback(
    view_data: Mapping[str, Any],
    mode: Optional[str] = None,
    *,
    surface: Optional[str] = None,
) -> str:
    """Renders a crisp plain-Unicode/Markdown view for terminal and headless CLI surfaces."""
    payload = normalize_crosstalk_view_data(view_data, mode=mode, surface=surface)
    desktop = is_desktop_surface(surface)
    effective_mode = payload["mode"]
    goal = payload["goal"]
    lines: List[str] = []

    if effective_mode == "preflight":
        route = payload["route"]
        red = payload["redaction"]
        from_spec = route["from_project"] + (f"@{route['from_branch']}" if route["from_branch"] else "")
        to_spec = route["to_project"] + (f"@{route['to_branch']}" if route["to_branch"] else "")
        lines.append(f"── Crosstalk Preflight [{route['visibility']}] (Hop {route['hop']}/{route['max_hops']}) ──")
        lines.append(f"Goal:    {goal['title']}" + (f" — {goal['line']}" if goal["line"] else ""))
        lines.append(f"Route:   {from_spec} -> {to_spec}")
        shield_state = "OK" if red["passed"] else "REVIEW"
        lines.append(
            f"Shield:  {shield_state} · {red['tokens_scrubbed']} scrubbed · "
            f"{red['paths_anonymized']} paths · {len(red['blocked_files'])} blocked"
        )
        if red["blocked_files"]:
            lines.append("Blocked: " + ", ".join(red["blocked_files"][:4]))
        for warn in red["warnings"][:3]:
            lines.append(f"Warn:    {warn}")
        for art in payload["artifacts"][:4]:
            lines.append(f"Ref:     {art['label']}" + (f" ({art['path']})" if art["path"] else ""))
        if red["cli_command"]:
            lines.append(f"CLI:     {red['cli_command']}")
        return "\n".join(lines)

    entities = payload["entities"]
    counts = {k: sum(1 for ent in entities if ent["outcome"] == k) for k in _OUTCOME_ORDER}
    summary = ", ".join(f"{counts[k]} {k}" for k in _OUTCOME_ORDER if counts[k] > 0) or "0 threads"
    lines.append(f"── Crosstalk Constellation ({summary}) ──")
    lines.append(f"Goal: {goal['title']}" + (f" — {goal['line']}" if goal["line"] else ""))

    if payload["attention"]:
        lines.append("Attention:")
        for att in payload["attention"][:4]:
            ref_txt = f" (ref: {att['refs'][0]['label']})" if att["refs"] else " (no ref)"
            lines.append(f"  [{att['kind'].upper()}] {att['title']}{ref_txt}")

    rows = entities if entities else payload["threads"]
    if rows:
        lines.append("Threads:")
        for row in rows:
            outcome_tag = row["outcome"].upper()
            if row.get("unverified_claim") and outcome_tag == "IDLE":
                outcome_tag = "IDLE/UNVERIFIED"
            surf_tag = f"[{row.get('surface', 'desktop')}]"
            proj_txt = row.get("project") or ""
            branch_txt = f"@{row['branch']}" if row.get("branch") else ""
            loc = f" {proj_txt}{branch_txt}" if proj_txt else ""
            gen_txt = f" gen:{row['generation']}" if row.get("generation") else ""
            hop_txt = f" hop:{row['hop']}/{row['max_hops']}" if row.get("hop") else ""
            ref_txt = f" ref:{row['refs'][0]['label']}" if row.get("refs") else ""
            if desktop and row.get("id"):
                try:
                    nav_txt = conversation_pill(row["id"], row["title"], surface="desktop")
                except ValueError:
                    nav_txt = row["title"]
            elif row.get("cli_command"):
                nav_txt = f"{row['title']} · `{row['cli_command']}`"
            else:
                nav_txt = row["title"]
            lines.append(f"  ● [{outcome_tag}] {surf_tag} {nav_txt}{loc}{gen_txt}{hop_txt}{ref_txt}")
    else:
        lines.append("Threads: (none discovered)")

    return "\n".join(lines)


def render_crosstalk_widget(
    view_data: Mapping[str, Any],
    mode: Optional[str] = None,
    artifact_dir: Optional[Union[Path, str]] = None,
    *,
    surface: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Renders a Generative UI Crosstalk widget (`constellation` or `preflight`) and
    returns `{html, json_payload, fallback_markdown, embed_hint, is_desktop, suggested_filename}`.
    """
    payload = normalize_crosstalk_view_data(view_data, mode=mode, surface=surface)
    effective_mode = payload["mode"]
    filename = _TEMPLATE_FILES[effective_mode]
    template = load_ux_asset(filename)
    safe_json = _safe_json_for_html_script(payload)
    html = template.replace("__CROSSTALK_VIEW_DATA__", safe_json, 1)

    desktop = is_desktop_surface(surface)
    fallback_md = render_cli_fallback(payload, mode=effective_mode, surface=surface)

    embed_hint = ""
    if desktop:
        if artifact_dir is not None and str(artifact_dir).strip():
            target_uri = (Path(artifact_dir).expanduser().resolve() / filename).as_uri()
        else:
            target_uri = f"file:///<artifact_dir>/{filename}"

        projects = {
            ent["project"] for ent in payload["entities"] if ent.get("project")
        }
        if payload["route"]["from_project"] and payload["route"]["from_project"] != "current":
            projects.add(payload["route"]["from_project"])
        if payload["route"]["to_project"] and payload["route"]["to_project"] != "target":
            projects.add(payload["route"]["to_project"])

        if effective_mode == "constellation" and (bool(view_data.get("standalone")) or len(projects) >= 4):
            embed_hint = f"[Crosstalk Constellation]({target_uri})"
        else:
            embed_hint = f'<agent-embed src="{target_uri}"></agent-embed>'

    return {
        "html": html,
        "json_payload": payload,
        "fallback_markdown": fallback_md,
        "embed_hint": embed_hint,
        "is_desktop": desktop,
        "suggested_filename": filename,
    }


__all__ = [
    "load_ux_asset",
    "normalize_crosstalk_view_data",
    "render_cli_fallback",
    "render_crosstalk_widget",
]
