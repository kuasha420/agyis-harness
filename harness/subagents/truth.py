# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Persona Truth Validation Engine (ADR-031 / Issue #72).

Enforces the Anti-Code-Monkey Invariant: root orchestrators cannot report victory
or delegate completion without verified on-disk transition payloads and healthy
subagent liveness states.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

from harness.subagents.liveness import probe_subagent_liveness
from harness.subagents.routing import validate_stage_transition_payload


def validate_transition_payload_truth(
    workspace: Path,
    payload_path: Optional[Path] = None,
    allow_synthetic: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Validates on-disk transition payload truth and subagent liveness against schema
    and empirical truth invariants.
    """
    workspace = Path(workspace)
    target_payload: Optional[Path] = None

    if payload_path is not None:
        p = Path(payload_path)
        if not p.is_absolute():
            p = workspace / p
        if p.is_file():
            target_payload = p
        else:
            return False, [f"Specified payload file does not exist: {p}"]
    else:
        # Search candidate paths in workspace
        candidates = [
            workspace / "psl_stage_transition_payload.json",
            workspace / ".agents" / "artifacts" / "psl_stage_transition_payload.json",
            workspace / ".agents" / "teamwork" / "psl_stage_transition_payload.json",
        ]
        for c in candidates:
            if c.is_file():
                target_payload = c
                break

        if target_payload is None:
            # Check pattern psl_stage_transition_*.json in artifacts or teamwork
            search_dirs = [
                workspace / ".agents" / "artifacts",
                workspace / ".agents" / "teamwork",
            ]
            for sdir in search_dirs:
                if sdir.is_dir():
                    matches = sorted(sdir.glob("psl_stage_transition_*.json"))
                    if matches:
                        target_payload = matches[-1]
                        break

    if target_payload is None:
        return False, ["Missing stage transition payload file: psl_stage_transition_payload.json"]

    errors: List[str] = []
    try:
        content = target_payload.read_text(encoding="utf-8")
        payload = json.loads(content)
    except Exception as exc:
        return False, [f"Failed to parse payload JSON from {target_payload}: {exc}"]

    # Schema validation
    valid_schema, schema_errors = validate_stage_transition_payload(payload)
    if not valid_schema:
        errors.extend(schema_errors)

    # Status invariant
    status = payload.get("status")
    if status != "PASS":
        errors.append(f"Stage transition status must be 'PASS', got '{status}'")

    # Verification invariants
    verif = payload.get("verification")
    if isinstance(verif, dict):
        exit_code = verif.get("exit_code")
        if exit_code != 0:
            errors.append(f"Verification exit_code must be 0, got {exit_code}")
        total = verif.get("total_tests")
        passed = verif.get("passed_tests")
        failed = verif.get("failed_tests")
        if failed is not None and failed > 0:
            errors.append(f"Verification has {failed} failed tests")
        if total is not None and passed is not None and total != passed:
            errors.append(f"Total tests ({total}) does not match passed tests ({passed})")

    # Referenced artifacts existence
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, dict):
        for art_key, art_val in artifacts.items():
            if art_val and isinstance(art_val, str) and art_val.strip():
                art_path = Path(art_val.strip())
                if not art_path.is_absolute():
                    art_path = workspace / art_path
                if not art_path.exists():
                    errors.append(f"Referenced artifact '{art_key}' does not exist on disk: {art_path}")

    # Delegate liveness check (unless allow_synthetic=True)
    if not allow_synthetic:
        try:
            teamwork_dir = workspace / ".agents" / "teamwork"
            if teamwork_dir.is_dir():
                statuses = probe_subagent_liveness(workspace_dir=workspace)
                for st in statuses:
                    if st.progress_file and str(workspace) in st.progress_file:
                        if st.liveness_state in ("DEAD", "STALE"):
                            errors.append(
                                f"Delegate subagent '{st.role}' ({st.conversation_id[:8]}) is in {st.liveness_state} state "
                                f"(age {int(st.heartbeat_age_seconds)}s)"
                            )
        except Exception as exc:
            errors.append(f"Failed to probe delegate liveness: {exc}")

    return len(errors) == 0, errors
