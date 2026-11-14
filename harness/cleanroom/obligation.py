# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Typed Cleanroom Obligation Ledger and Evidence Schemas for REA 6.8.0+ (ADR-028).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class EvidenceBundle:
    """Represents captured cleanroom evidence and analysis providers."""
    providers: List[Any] = field(default_factory=list)
    records: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    captures: List[Dict[str, Any]] = field(default_factory=list)
    environments: List[Dict[str, Any]] = field(default_factory=list)
    scenarios: List[Dict[str, Any]] = field(default_factory=list)
    unknowns: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ReviewedObligation:
    """Represents a reviewed cleanroom reconstruction obligation."""
    obligation_id: str
    disposition: str
    target: Optional[str] = None
    rationale: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)


@dataclass
class ObligationManifest:
    """Represents cleanroom symbol/protocol bindings and contradiction registry."""
    bindings: List[Dict[str, Any]] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)


def validate_obligation_ledger(ledger_path: Path | str) -> Tuple[bool, List[str]]:
    """
    Validates an obligation ledger JSON file against REA 6.8.0 schema:
    1. Valid JSON object without top-level '$schema'.
    2. 'evidence_bundle': dictionary containing 'providers', 'records', and 'artifacts'.
    3. 'reviewed_obligations': list of objects, each containing 'obligation_id' and valid 'disposition'.
    4. 'manifest': dictionary containing 'bindings' list and 'contradictions' list.
    """
    path = Path(ledger_path)
    if not path.is_file():
        return False, [f"Ledger file not found: {path}"]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return False, [f"Failed to parse obligation ledger as JSON: {e}"]

    if not isinstance(data, dict):
        return False, ["Obligation ledger root must be a JSON object."]

    errors: List[str] = []

    # Disallow top-level $schema (deprecated/unsupported in REA 6.8.0 schema)
    if "$schema" in data:
        errors.append("Top-level '$schema' is not allowed in REA 6.8.0 schema.")

    # 1. Validate evidence_bundle
    evidence_bundle = data.get("evidence_bundle")
    if not isinstance(evidence_bundle, dict):
        errors.append("Missing or invalid 'evidence_bundle' (must be a dictionary).")
    else:
        if "providers" not in evidence_bundle or not isinstance(evidence_bundle["providers"], list):
            errors.append("'evidence_bundle' must contain a 'providers' list.")
        if "records" not in evidence_bundle or not isinstance(evidence_bundle["records"], list):
            errors.append("'evidence_bundle' must contain a 'records' list.")
        if "artifacts" not in evidence_bundle or not isinstance(evidence_bundle["artifacts"], (list, dict)):
            errors.append("'evidence_bundle' must contain an 'artifacts' collection.")

    # 2. Validate reviewed_obligations
    reviewed = data.get("reviewed_obligations")
    if not isinstance(reviewed, list):
        errors.append("'reviewed_obligations' must be a list of obligations.")
    else:
        valid_dispositions = {"active", "blocked", "out-of-scope"}
        for idx, ob in enumerate(reviewed):
            if not isinstance(ob, dict):
                errors.append(f"Obligation at index {idx} must be a dictionary.")
                continue
            if not ob.get("obligation_id"):
                errors.append(f"Obligation at index {idx} is missing required 'obligation_id'.")
            disposition = ob.get("disposition")
            if not disposition:
                errors.append(f"Obligation at index {idx} is missing required 'disposition'.")
            elif disposition not in valid_dispositions:
                errors.append(
                    f"Obligation at index {idx} has invalid disposition '{disposition}' "
                    f"(expected one of {sorted(valid_dispositions)})."
                )

    # 3. Validate manifest
    manifest = data.get("manifest")
    if not isinstance(manifest, dict):
        errors.append("Missing or invalid 'manifest' (must be a dictionary).")
    else:
        if "bindings" not in manifest or not isinstance(manifest["bindings"], list):
            errors.append("'manifest' must contain a 'bindings' list.")
        contradictions = manifest.get("contradictions")
        if contradictions is None or not isinstance(contradictions, list):
            errors.append("'manifest' must contain a 'contradictions' list.")
        elif len(contradictions) > 0:
            errors.append(f"Unresolved contradictions present in manifest ({len(contradictions)} items).")

    return len(errors) == 0, errors


def scaffold_obligation_ledger(output_path: Path | str) -> Path:
    """
    Generates a starter typed obligation ledger adhering to REA 6.8.0 schema.
    """
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    template: Dict[str, Any] = {
        "evidence_bundle": {
            "artifacts": [],
            "captures": [],
            "environments": [],
            "providers": [
                {
                    "id": "ghidra",
                    "name": "Ghidra Headless Decompiler",
                    "version": "12.2",
                }
            ],
            "records": [],
            "scenarios": [],
            "unknowns": [],
        },
        "manifest": {
            "bindings": [],
            "contradictions": [],
        },
        "reviewed_obligations": [],
    }

    target.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    return target
