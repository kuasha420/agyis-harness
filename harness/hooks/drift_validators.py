# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Pluggable domain-specific validators for anti-drift hook (ADR-014 / ADR-031).

Provides cluster status and ledger verification as a pluggable validator
rather than hardcoded core hook logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Optional

from harness.utils.state import get_state_dir

CLUSTER_TABLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\|\s*(?:Node|Host|Strand|Worker|Controller|Anchor|Device)\s*\|.*\|\s*(?:Status|Role|Hardware|Model|Ping|State|Last\s+Seen|Quota|Tailscale)\s*\|", re.I),
    re.compile(r"\|\s*(?:Status|State|Role|Metrics|Quota)\s*\|.*(?:Node|Host|Strand|Cluster|Device)\b", re.I),
    re.compile(r"##+.*(?:Cluster\s+Status|Node\s+Metrics|Strand\s+Allocation|Fleet.*Quota|Node\s+Status|Cluster\s+Table)", re.I),
    re.compile(r"\b(?:5-Hour Quota|Weekly Quota|Hardware Role|Keyring State)\b", re.I),
)


def get_proof_file(conv_id: str = "default", state_dir: Path | None = None) -> Path:
    """Returns path to the telemetry proof record file for conversation."""
    target_dir = state_dir or get_state_dir()
    return target_dir / f"telemetry_proof_{conv_id}.json"


def record_telemetry_proof(
    command: str,
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> bool:
    """
    Records live CLI telemetry proof if command matches 'knot ledger generate --json'
    or 'knot status --json' (or knot status/ledger commands).
    """
    if not command:
        return False
    clean = command.strip()
    if not re.search(r"\bknot\s+(?:ledger\s+generate|status)\b", clean):
        return False

    target_dir = state_dir or get_state_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    proof_file = get_proof_file(conv_id, target_dir)
    data = {
        "conversation_id": conv_id,
        "command": clean,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "verified": True,
    }
    try:
        proof_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except OSError as exc:
        sys.stderr.write(f"PSL Anti-Drift: Failed to record telemetry proof: {exc}\n")
        return False


def has_telemetry_proof(
    conv_id: str = "default",
    state_dir: Path | None = None,
    payload: dict | None = None,
) -> bool:
    """
    Checks whether live CLI telemetry proof has been established for this session:
    1. Explicit proof in payload ('telemetry_proof', 'live_telemetry_proof').
    2. Dedicated proof file 'telemetry_proof_{conv_id}.json'.
    3. Tool execution history in 'history_{conv_id}.json' with matching knot command.
    """
    if payload:
        if payload.get("telemetry_proof") or payload.get("live_telemetry_proof"):
            return True

    target_dir = state_dir or get_state_dir()
    proof_file = get_proof_file(conv_id, target_dir)
    if proof_file.exists():
        try:
            data = json.loads(proof_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("verified"):
                return True
        except (json.JSONDecodeError, OSError):
            pass

    history_file = target_dir / f"history_{conv_id}.json"
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text(encoding="utf-8"))
            if isinstance(history, list):
                for item in history:
                    args = item.get("args") or {}
                    cmd = args.get("CommandLine") or args.get("command") or ""
                    if re.search(r"\bknot\s+(?:ledger\s+generate|status)\b", cmd):
                        return True
        except (json.JSONDecodeError, OSError):
            pass

    return False


def has_cluster_status_table(content: str) -> bool:
    """
    Detects whether Markdown content contains cluster status or node metrics tables.
    Requires Markdown table pipe ('|') syntax plus cluster/node telemetry headers.
    """
    if not content or "|" not in content:
        return False
    return any(pat.search(content) is not None for pat in CLUSTER_TABLE_PATTERNS)


def check_ledger_cluster_tables(
    target_file: str,
    content: str,
    conv_id: str = "default",
    state_dir: Path | None = None,
    payload: dict | None = None,
) -> Optional[dict]:
    """
    Intercepts modifications targeting operator_ledger.md containing cluster status or
    node metrics tables, verifying that live CLI telemetry proof was recorded.
    """
    if not target_file:
        return None

    target_name = Path(target_file).name.lower()
    is_ledger = (
        target_name == "operator_ledger.md"
        or target_file.endswith("operator_ledger.md")
        or bool(re.search(r"operator_ledger(?:\.md)?$", target_file, re.I))
        or (target_name.endswith(".md") and "ledger" in target_name)
    )
    if not is_ledger:
        return None

    if not has_cluster_status_table(content):
        return None

    if not has_telemetry_proof(conv_id=conv_id, state_dir=state_dir, payload=payload):
        return {
            "decision": "deny",
            "reason": (
                f"PSL Anti-Drift Gate: Modification to '{target_name}' contains cluster status "
                "or node metrics tables without live CLI telemetry proof. "
                "Execute 'knot ledger generate --json' or 'knot status --json' to verify "
                "live cluster metrics before updating ledger."
            ),
        }

    return None
