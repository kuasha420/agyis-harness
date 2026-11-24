# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Typed Cleanroom Obligation Ledger and Evidence Schemas for REA 6.9.0 (ADR-028, PSL-RE-001, PSL-INV-002).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_EVIDENCE_ID_RE = re.compile(r"^ev_[a-f0-9]{64}$")
_UNKNOWN_ID_RE = re.compile(r"^unk_[a-f0-9]{64}$")
_APP_NODE_ID_RE = re.compile(r"^jag_node_[a-f0-9]{64}$")
_SEM_NODE_ID_RE = re.compile(r"^jsrg_node_[a-f0-9]{64}$")
_STABLE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._:/-]*$")

_VALID_DISPOSITIONS = frozenset({"active", "blocked", "out-of-scope"})
_VALID_LAYERS = frozenset({"cli", "protocol", "electron", "persistence", "process", "runtime", "packaging", "native-abi", "application", "other"})
_VALID_CASE_KINDS = frozenset({"positive", "negative", "malformed", "cancellation", "teardown"})
_VALID_ORIGINAL_AUTHORITIES = frozenset({"static", "runtime", "process", "external"})
_VALID_PROOF_AUTHORITIES = frozenset({"unit", "integration", "protocol", "renderer", "packaged-process", "native-abi", "live-observation", "external"})
_VALID_EVIDENCE_CONFIDENCES = frozenset({"observed", "derived", "inferred"})
_VALID_EVIDENCE_AUTHORITIES = frozenset({"shipped-artifact", "controlled-replay", "historical-reference", "external-service", "analyst-inference"})
_VALID_ISOLATIONS = frozenset({"none", "process", "container", "virtual-machine"})
_VALID_UNKNOWN_STATUSES = frozenset({"open", "investigating", "blocked", "contradicted", "resolved"})
_VALID_UNKNOWN_SEVERITIES = frozenset({"low", "medium", "high", "critical"})
_VALID_VERIFIER_STATUSES = frozenset({"pass", "fail", "unknown", "unsupported", "skipped"})
_VALID_NONDETERMINISM_MODES = frozenset({"total-order", "partial-order", "finite-traces"})
_BUNDLE_KEYS = frozenset({"artifacts", "captures", "environments", "providers", "records", "scenarios", "unknowns"})
_MANIFEST_KEYS = frozenset({"bindings", "contradictions"})
_TARGET_KEYS = frozenset({"artifact_sha256", "application_node_id", "semantic_node_id", "location"})
_REVIEWED_OBLIGATION_KEYS = frozenset({
    "obligation_id", "obligation_version", "title", "application_layer", "family", "target", "required",
    "required_case_kinds", "required_original_authority", "required_fixture_authority", "required_verifier_authority",
    "requires_parser_type", "dependency_obligation_ids", "residual_unknown_ids", "unavailable_authority",
    "required_next_evidence", "disposition", "review_evidence_ids",
})
_BINDING_KEYS = frozenset({"obligation_id", "owner", "parser_type", "original_cases", "fixtures", "verifier"})


@dataclass
class EvidenceBundle:
    """Represents captured cleanroom evidence and analysis providers (REA 6.9.0)."""
    providers: List[Any] = field(default_factory=list)
    records: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    captures: List[Dict[str, Any]] = field(default_factory=list)
    environments: List[Dict[str, Any]] = field(default_factory=list)
    scenarios: List[Dict[str, Any]] = field(default_factory=list)
    unknowns: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ObligationTarget:
    """Represents the strictObject target descriptor for a reviewed obligation (REA 6.9.0)."""
    artifact_sha256: Optional[str] = None
    application_node_id: Optional[str] = None
    semantic_node_id: Optional[str] = None
    location: str = ""


@dataclass
class ReviewedObligation:
    """Represents a reviewed cleanroom reconstruction obligation (REA 6.9.0 strictObject)."""
    obligation_id: str
    disposition: str
    target: Union[Dict[str, Any], ObligationTarget, str] = field(
        default_factory=lambda: {"artifact_sha256": None, "application_node_id": None, "semantic_node_id": None, "location": ""}
    )
    obligation_version: int = 1
    title: str = ""
    application_layer: str = "application"
    family: str = "cleanroom"
    required: bool = True
    required_case_kinds: List[str] = field(default_factory=lambda: ["positive"])
    required_original_authority: str = "static"
    required_fixture_authority: str = "unit"
    required_verifier_authority: str = "unit"
    requires_parser_type: bool = False
    dependency_obligation_ids: List[str] = field(default_factory=list)
    residual_unknown_ids: List[str] = field(default_factory=list)
    unavailable_authority: List[str] = field(default_factory=list)
    required_next_evidence: List[str] = field(default_factory=list)
    review_evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes this obligation to a REA 6.9.0 strictObject dictionary."""
        data = asdict(self)
        raw_target = self.target
        if isinstance(raw_target, str):
            data["target"] = {
                "artifact_sha256": None,
                "application_node_id": None,
                "semantic_node_id": None,
                "location": raw_target,
            }
        elif isinstance(raw_target, ObligationTarget):
            data["target"] = asdict(raw_target)
        return data


@dataclass
class ObligationManifest:
    """Represents cleanroom symbol/protocol bindings and contradiction registry."""

    bindings: List[Dict[str, Any]] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)


def _is_non_bool_int(val: Any) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _is_non_empty_text(val: Any) -> bool:
    return isinstance(val, str) and bool(val.strip()) and "\x00" not in val


def _validate_strict_keys(
    obj: Dict[str, Any],
    expected_keys: Set[str] | frozenset[str],
    label: str,
    errors: List[str],
) -> bool:
    keys = set(obj.keys())
    missing = sorted(expected_keys - keys)
    extra = sorted(keys - expected_keys)
    if missing:
        errors.append(f"{label} is missing required keys: {', '.join(missing)}.")
    if extra:
        errors.append(f"{label} contains unrecognized strictObject keys: {', '.join(extra)}.")
    return not missing and not extra


def _validate_provider_obj(provider: Any, label: str, errors: List[str]) -> None:
    if not isinstance(provider, dict):
        errors.append(f"{label} must be an object.")
        return
    _validate_strict_keys(provider, {"id", "name", "version"}, label, errors)
    if not _is_non_empty_text(provider.get("id")):
        errors.append(f"{label}.id must be a non-empty string.")
    if not _is_non_empty_text(provider.get("name")):
        errors.append(f"{label}.name must be a non-empty string.")
    version = provider.get("version")
    if version is not None and not _is_non_empty_text(version):
        errors.append(f"{label}.version must be null or a non-empty string.")


def _validate_subject_obj(subject: Any, label: str, errors: List[str]) -> None:
    if subject is None:
        return
    if not isinstance(subject, dict):
        errors.append(f"{label} must be null or an object.")
        return
    if not _is_non_empty_text(subject.get("name")):
        errors.append(f"{label}.name must be a non-empty string.")
    digest = subject.get("digest")
    if not isinstance(digest, dict) or not _SHA256_RE.match(str(digest.get("sha256", ""))):
        errors.append(f"{label}.digest.sha256 must be a valid 64-character lowercase hex SHA-256 digest.")
    if not _is_non_empty_text(subject.get("format")):
        errors.append(f"{label}.format must be a non-empty string.")
    local_path = subject.get("local_path")
    if not isinstance(local_path, str) or "\x00" in local_path:
        errors.append(f"{label}.local_path must be a valid NUL-free string.")
    arch = subject.get("architecture")
    if arch is not None and not _is_non_empty_text(arch):
        errors.append(f"{label}.architecture must be null or a non-empty string.")


def _validate_unknowns(
    unknowns: Any,
    retained_ids: Set[str],
    errors: List[str],
) -> Dict[str, Dict[str, Any]]:
    if not isinstance(unknowns, list):
        errors.append("'evidence_bundle.unknowns' must be a list.")
        return {}

    histories: Dict[str, List[Dict[str, Any]]] = {}
    for idx, unk in enumerate(unknowns):
        label = f"evidence_bundle.unknowns[{idx}]"
        if not isinstance(unk, dict):
            errors.append(f"{label} must be an object.")
            continue
        unk_id = unk.get("unknown_id")
        if not isinstance(unk_id, str) or not _UNKNOWN_ID_RE.match(unk_id):
            errors.append(f"{label}.unknown_id must match 'unk_<64-hex>'.")
            continue
        rev = unk.get("revision")
        if not _is_non_bool_int(rev) or rev < 1:
            errors.append(f"{label}.revision must be an integer >= 1.")
        prev_digest = unk.get("previous_revision_digest")
        if rev == 1:
            if prev_digest is not None:
                errors.append(f"{label}.previous_revision_digest must be null for revision 1.")
        elif not isinstance(prev_digest, str) or not _SHA256_RE.match(prev_digest):
            errors.append(f"{label}.previous_revision_digest must be a 64-hex digest for revision > 1.")
        rev_digest = unk.get("revision_digest")
        if not isinstance(rev_digest, str) or not _SHA256_RE.match(rev_digest):
            errors.append(f"{label}.revision_digest must be a 64-hex digest.")
        scope_digest = unk.get("scope_digest")
        if scope_digest is not None and (not isinstance(scope_digest, str) or not _SHA256_RE.match(scope_digest)):
            errors.append(f"{label}.scope_digest must be null or a 64-hex digest.")
        if not _is_non_empty_text(unk.get("question")):
            errors.append(f"{label}.question must be a non-empty string.")
        if not _is_non_empty_text(unk.get("domain")):
            errors.append(f"{label}.domain must be a non-empty string.")
        status = unk.get("status")
        if status not in _VALID_UNKNOWN_STATUSES:
            errors.append(f"{label}.status '{status}' must be one of {sorted(_VALID_UNKNOWN_STATUSES)}.")
        sev = unk.get("severity")
        if sev not in _VALID_UNKNOWN_SEVERITIES:
            errors.append(f"{label}.severity '{sev}' must be one of {sorted(_VALID_UNKNOWN_SEVERITIES)}.")

        sup_ids = unk.get("supporting_evidence_ids", [])
        con_ids = unk.get("contradicting_evidence_ids", [])
        mut_ids = unk.get("mutation_evidence_ids")
        if not isinstance(sup_ids, list) or not isinstance(con_ids, list) or not isinstance(mut_ids, list) or len(mut_ids) == 0:
            errors.append(f"{label} must have list evidence IDs and non-empty 'mutation_evidence_ids'.")
        else:
            for ev_id in sup_ids + con_ids + mut_ids:
                if not isinstance(ev_id, str) or not _EVIDENCE_ID_RE.match(ev_id):
                    errors.append(f"{label} references invalid evidence ID '{ev_id}'.")
                elif ev_id not in retained_ids:
                    errors.append(f"{label} references missing retained evidence '{ev_id}'.")
            overlap = set(sup_ids) & set(con_ids)
            if overlap:
                errors.append(f"{label} has evidence simultaneously supporting and contradicting: {sorted(overlap)}.")
            if status == "contradicted" and len(con_ids) == 0:
                errors.append(f"{label} has status 'contradicted' without contradicting_evidence_ids.")

        resolution = unk.get("resolution")
        if (status == "resolved") != (resolution is not None):
            errors.append(f"{label} must set 'resolution' iff status is 'resolved'.")
        elif isinstance(resolution, dict):
            disp = resolution.get("disposition")
            res_evs = resolution.get("evidence_ids")
            if disp not in {"verified", "withdrawn", "out-of-scope"} or not _is_non_empty_text(resolution.get("rationale")):
                errors.append(f"{label}.resolution must have valid disposition and rationale.")
            if not isinstance(res_evs, list) or (disp == "verified" and len(res_evs) == 0):
                errors.append(f"{label}.resolution.evidence_ids must be non-empty for verified disposition.")
            elif disp == "verified":
                if isinstance(con_ids, list) and len(con_ids) > 0:
                    errors.append(f"{label} cannot be resolved as 'verified' with contradicting evidence.")
                for ev_id in res_evs:
                    if ev_id not in retained_ids:
                        errors.append(f"{label}.resolution references missing evidence '{ev_id}'.")

        histories.setdefault(unk_id, []).append(unk)

    latest_unknowns: Dict[str, Dict[str, Any]] = {}
    for unk_id, items in sorted(histories.items()):
        ordered = sorted(items, key=lambda u: u.get("revision", 0) if _is_non_bool_int(u.get("revision")) else 0)
        for idx, item in enumerate(ordered):
            expected_rev = idx + 1
            if item.get("revision") != expected_rev:
                errors.append(f"Residual unknown {unk_id} revision history has a gap (expected {expected_rev}, got {item.get('revision')}).")
            if idx > 0 and item.get("previous_revision_digest") != ordered[idx - 1].get("revision_digest"):
                errors.append(f"Residual unknown {unk_id} revision {expected_rev} breaks previous_revision_digest chain.")
        head = ordered[-1]
        latest_unknowns[unk_id] = head
        if head.get("status") != "resolved":
            errors.append(
                f"PSL-RE-001 / PSL-INV-002: Unresolved residual unknown '{unk_id}' "
                f"(status='{head.get('status')}', question='{head.get('question', '')}')."
            )

    return latest_unknowns


def _validate_evidence_bundle(
    bundle: Any,
    errors: List[str],
) -> Tuple[Set[str], Dict[str, Dict[str, Any]]]:
    if not isinstance(bundle, dict):
        errors.append("Missing or invalid 'evidence_bundle' (must be a strictObject dictionary).")
        return set(), {}

    _validate_strict_keys(bundle, _BUNDLE_KEYS, "evidence_bundle", errors)

    for key in sorted(_BUNDLE_KEYS):
        val = bundle.get(key)
        if not isinstance(val, list):
            errors.append(f"'evidence_bundle.{key}' must be a list (got {type(val).__name__}).")

    records = bundle.get("records")
    retained_ids: Set[str] = set()
    if isinstance(records, list):
        if len(records) == 0:
            errors.append(
                "PSL-RE-001 / PSL-INV-002: 'evidence_bundle.records' cannot be empty; "
                "empty or unbacked ledgers cannot claim cleanroom verification."
            )
        for idx, rec in enumerate(records):
            label = f"evidence_bundle.records[{idx}]"
            if not isinstance(rec, dict):
                errors.append(f"{label} must be an object.")
                continue
            ev_id = rec.get("evidence_id")
            if not isinstance(ev_id, str) or not _EVIDENCE_ID_RE.match(ev_id):
                errors.append(f"{label}.evidence_id must match 'ev_<64-hex>'.")
            elif ev_id in retained_ids:
                errors.append(f"Duplicate evidence_id '{ev_id}' in evidence_bundle.records.")
            else:
                retained_ids.add(ev_id)

            _validate_provider_obj(rec.get("provider"), f"{label}.provider", errors)
            _validate_subject_obj(rec.get("subject"), f"{label}.subject", errors)

            if not _is_non_empty_text(rec.get("predicate_type")):
                errors.append(f"{label}.predicate_type must be a non-empty string.")
            if not _is_non_empty_text(rec.get("operation")):
                errors.append(f"{label}.operation must be a non-empty string.")
            if rec.get("confidence") not in _VALID_EVIDENCE_CONFIDENCES:
                errors.append(f"{label}.confidence must be one of {sorted(_VALID_EVIDENCE_CONFIDENCES)}.")
            if rec.get("authority") not in _VALID_EVIDENCE_AUTHORITIES:
                errors.append(f"{label}.authority must be one of {sorted(_VALID_EVIDENCE_AUTHORITIES)}.")

    artifacts = bundle.get("artifacts")
    if isinstance(artifacts, list):
        for idx, art in enumerate(artifacts):
            label = f"evidence_bundle.artifacts[{idx}]"
            if not isinstance(art, dict):
                errors.append(f"{label} must be an object.")
                continue
            digest = art.get("digest")
            if not isinstance(digest, dict) or not _SHA256_RE.match(str(digest.get("sha256", ""))):
                errors.append(f"{label}.digest.sha256 must be a valid 64-character hex SHA-256 digest.")
            if not _is_non_empty_text(art.get("format")):
                errors.append(f"{label}.format must be a non-empty string.")

    providers = bundle.get("providers")
    if isinstance(providers, list):
        for idx, prov in enumerate(providers):
            _validate_provider_obj(prov, f"evidence_bundle.providers[{idx}]", errors)

    environments = bundle.get("environments")
    if isinstance(environments, list):
        for idx, env in enumerate(environments):
            label = f"evidence_bundle.environments[{idx}]"
            if not isinstance(env, dict):
                errors.append(f"{label} must be an object.")
                continue
            _validate_strict_keys(env, {"id", "platform", "architecture", "isolation"}, label, errors)
            for field_name in ("id", "platform", "architecture"):
                if not _is_non_empty_text(env.get(field_name)):
                    errors.append(f"{label}.{field_name} must be a non-empty string.")
            if env.get("isolation") not in _VALID_ISOLATIONS:
                errors.append(f"{label}.isolation must be one of {sorted(_VALID_ISOLATIONS)}.")

    scenarios = bundle.get("scenarios")
    if isinstance(scenarios, list):
        for idx, scen in enumerate(scenarios):
            label = f"evidence_bundle.scenarios[{idx}]"
            if not isinstance(scen, dict):
                errors.append(f"{label} must be an object.")
                continue
            _validate_strict_keys(scen, {"evidence_id", "operation", "authority"}, label, errors)
            ev_id = scen.get("evidence_id")
            if not isinstance(ev_id, str) or ev_id not in retained_ids:
                errors.append(f"{label}.evidence_id '{ev_id}' must reference a retained record.")
            if not _is_non_empty_text(scen.get("operation")):
                errors.append(f"{label}.operation must be a non-empty string.")
            if scen.get("authority") != "controlled-replay":
                errors.append(f"{label}.authority must be 'controlled-replay'.")

    captures = bundle.get("captures")
    if isinstance(captures, list):
        for idx, cap in enumerate(captures):
            label = f"evidence_bundle.captures[{idx}]"
            if not isinstance(cap, dict):
                errors.append(f"{label} must be an object.")
                continue
            _validate_strict_keys(cap, {"evidence_id", "predicate_type"}, label, errors)
            ev_id = cap.get("evidence_id")
            if not isinstance(ev_id, str) or ev_id not in retained_ids:
                errors.append(f"{label}.evidence_id '{ev_id}' must reference a retained record.")
            if not _is_non_empty_text(cap.get("predicate_type")):
                errors.append(f"{label}.predicate_type must be a non-empty string.")

    latest_unknowns = _validate_unknowns(bundle.get("unknowns"), retained_ids, errors)
    return retained_ids, latest_unknowns


def _validate_target_obj(target: Any, label: str, errors: List[str]) -> None:
    if not isinstance(target, dict):
        errors.append(f"{label} must be a strictObject dictionary.")
        return
    _validate_strict_keys(target, _TARGET_KEYS, label, errors)
    sha = target.get("artifact_sha256")
    if sha is not None and (not isinstance(sha, str) or not _SHA256_RE.match(sha)):
        errors.append(f"{label}.artifact_sha256 must be null or a 64-hex SHA-256 digest.")
    app_id = target.get("application_node_id")
    if app_id is not None and (not isinstance(app_id, str) or not _APP_NODE_ID_RE.match(app_id)):
        errors.append(f"{label}.application_node_id must be null or match 'jag_node_<64-hex>'.")
    sem_id = target.get("semantic_node_id")
    if sem_id is not None and (not isinstance(sem_id, str) or not _SEM_NODE_ID_RE.match(sem_id)):
        errors.append(f"{label}.semantic_node_id must be null or match 'jsrg_node_<64-hex>'.")
    if not _is_non_empty_text(target.get("location")):
        errors.append(f"{label}.location must be a non-empty string.")


def _validate_reviewed_obligations(
    reviewed: Any,
    retained_ids: Set[str],
    latest_unknowns: Dict[str, Dict[str, Any]],
    errors: List[str],
) -> Dict[str, Dict[str, Any]]:
    if not isinstance(reviewed, list):
        errors.append("'reviewed_obligations' must be a list of obligations.")
        return {}
    if len(reviewed) == 0:
        errors.append(
            "PSL-RE-001 / PSL-INV-002: 'reviewed_obligations' cannot be empty; "
            "an empty obligation ledger cannot claim reconstruction closure."
        )
        return {}

    reviewed_by_id: Dict[str, Dict[str, Any]] = {}
    for idx, ob in enumerate(reviewed):
        label = f"reviewed_obligations[{idx}]"
        if not isinstance(ob, dict):
            errors.append(f"{label} must be an object.")
            continue

        _validate_strict_keys(ob, _REVIEWED_OBLIGATION_KEYS, label, errors)

        ob_id = ob.get("obligation_id")
        if not isinstance(ob_id, str) or not _STABLE_ID_RE.match(ob_id):
            errors.append(f"{label} is missing or has invalid 'obligation_id' (must match stable identifier pattern).")
        elif ob_id in reviewed_by_id:
            errors.append(f"Duplicate obligation_id '{ob_id}' in reviewed_obligations.")
        else:
            reviewed_by_id[ob_id] = ob

        ob_ver = ob.get("obligation_version")
        if not _is_non_bool_int(ob_ver) or ob_ver < 1:
            errors.append(f"{label}.obligation_version must be an integer >= 1 (REA 6.9.0).")

        for text_field in ("title", "family"):
            if not _is_non_empty_text(ob.get(text_field)):
                errors.append(f"{label}.{text_field} must be a non-empty string.")

        if ob.get("application_layer") not in _VALID_LAYERS:
            errors.append(f"{label}.application_layer must be one of {sorted(_VALID_LAYERS)}.")

        _validate_target_obj(ob.get("target"), f"{label}.target", errors)

        for bool_field in ("required", "requires_parser_type"):
            if not isinstance(ob.get(bool_field), bool):
                errors.append(f"{label}.{bool_field} must be a boolean.")

        case_kinds = ob.get("required_case_kinds")
        if not isinstance(case_kinds, list) or len(case_kinds) == 0 or any(k not in _VALID_CASE_KINDS for k in case_kinds):
            errors.append(f"{label}.required_case_kinds must be a non-empty list of {sorted(_VALID_CASE_KINDS)}.")

        if ob.get("required_original_authority") not in _VALID_ORIGINAL_AUTHORITIES:
            errors.append(f"{label}.required_original_authority must be one of {sorted(_VALID_ORIGINAL_AUTHORITIES)}.")
        if ob.get("required_fixture_authority") not in _VALID_PROOF_AUTHORITIES:
            errors.append(f"{label}.required_fixture_authority must be one of {sorted(_VALID_PROOF_AUTHORITIES)}.")
        if ob.get("required_verifier_authority") not in _VALID_PROOF_AUTHORITIES:
            errors.append(f"{label}.required_verifier_authority must be one of {sorted(_VALID_PROOF_AUTHORITIES)}.")

        disposition = ob.get("disposition")
        if not disposition:
            errors.append(f"{label} is missing required 'disposition'.")
        elif disposition not in _VALID_DISPOSITIONS:
            errors.append(
                f"{label} has invalid disposition '{disposition}' "
                f"(expected one of {sorted(_VALID_DISPOSITIONS)})."
            )

        rev_evs = ob.get("review_evidence_ids")
        if not isinstance(rev_evs, list) or len(rev_evs) == 0:
            errors.append(f"{label}.review_evidence_ids must contain at least 1 retained evidence ID.")
        else:
            for ev_id in rev_evs:
                if not isinstance(ev_id, str) or not _EVIDENCE_ID_RE.match(ev_id):
                    errors.append(f"{label}.review_evidence_ids contains invalid ID '{ev_id}'.")
                elif ev_id not in retained_ids:
                    errors.append(f"{label}.review_evidence_ids references missing retained evidence '{ev_id}'.")

        dep_ids = ob.get("dependency_obligation_ids")
        if not isinstance(dep_ids, list) or any(not isinstance(d, str) or not _STABLE_ID_RE.match(d) for d in dep_ids):
            errors.append(f"{label}.dependency_obligation_ids must be a list of stable obligation IDs.")

        res_unks = ob.get("residual_unknown_ids")
        if not isinstance(res_unks, list) or any(not isinstance(u, str) or not _STABLE_ID_RE.match(u) for u in res_unks):
            errors.append(f"{label}.residual_unknown_ids must be a list of stable unknown IDs.")
        else:
            for unk_id in res_unks:
                if unk_id not in latest_unknowns:
                    errors.append(f"{label}.residual_unknown_ids references missing unknown '{unk_id}' not in evidence_bundle.unknowns.")

        unavail = ob.get("unavailable_authority")
        if not isinstance(unavail, list) or any(not _is_non_empty_text(item) for item in unavail):
            errors.append(f"{label}.unavailable_authority must be a list of non-empty strings.")

        next_ev = ob.get("required_next_evidence")
        if not isinstance(next_ev, list) or any(not _is_non_empty_text(item) for item in next_ev):
            errors.append(f"{label}.required_next_evidence must be a list of non-empty strings.")

        if disposition == "active" and ob.get("required") is True:
            if isinstance(res_unks, list) and len(res_unks) > 0:
                errors.append(f"PSL-RE-001: Active required obligation '{ob_id}' retains unresolved residual_unknown_ids.")
            if isinstance(unavail, list) and len(unavail) > 0:
                errors.append(f"PSL-RE-001: Active required obligation '{ob_id}' reports unavailable_authority.")
            if isinstance(next_ev, list) and len(next_ev) > 0:
                errors.append(f"PSL-RE-001: Active required obligation '{ob_id}' still requires next evidence.")

    for ob_id, ob in reviewed_by_id.items():
        deps = ob.get("dependency_obligation_ids")
        if isinstance(deps, list):
            for dep_id in deps:
                if dep_id == ob_id:
                    errors.append(f"Obligation '{ob_id}' cannot depend on itself.")
                elif dep_id not in reviewed_by_id:
                    errors.append(f"Obligation '{ob_id}' depends on missing obligation '{dep_id}'.")

    return reviewed_by_id


def _validate_binding_item(
    binding: Any,
    idx: int,
    retained_ids: Set[str],
    reviewed_by_id: Dict[str, Dict[str, Any]],
    bound_ids: Set[str],
    errors: List[str],
) -> None:
    label = f"manifest.bindings[{idx}]"
    if not isinstance(binding, dict):
        errors.append(f"{label} must be an object.")
        return
    _validate_strict_keys(binding, _BINDING_KEYS, label, errors)

    ob_id = binding.get("obligation_id")
    if not isinstance(ob_id, str) or not _STABLE_ID_RE.match(ob_id):
        errors.append(f"{label}.obligation_id must be a valid stable identifier.")
    elif ob_id in bound_ids:
        errors.append(f"Duplicate manifest binding for obligation '{ob_id}'.")
    else:
        bound_ids.add(ob_id)
        if reviewed_by_id and ob_id not in reviewed_by_id:
            errors.append(f"{label}.obligation_id '{ob_id}' is not present in reviewed_obligations.")

    owner = binding.get("owner")
    if not isinstance(owner, dict):
        errors.append(f"{label}.owner must be an object.")
    else:
        _validate_strict_keys(owner, {"module_path", "symbol", "owner_sha256"}, f"{label}.owner", errors)
        if not _is_non_empty_text(owner.get("module_path")):
            errors.append(f"{label}.owner.module_path must be a non-empty string.")
        if not _is_non_empty_text(owner.get("symbol")):
            errors.append(f"{label}.owner.symbol must be a non-empty string.")
        if not isinstance(owner.get("owner_sha256"), str) or not _SHA256_RE.match(owner["owner_sha256"]):
            errors.append(f"{label}.owner.owner_sha256 must be a valid 64-hex SHA-256 digest.")

    parser_type = binding.get("parser_type")
    if parser_type is not None:
        if not isinstance(parser_type, dict):
            errors.append(f"{label}.parser_type must be null or an object.")
        else:
            _validate_strict_keys(parser_type, {"parser", "schema", "domain_type"}, f"{label}.parser_type", errors)
            for pf in ("parser", "schema", "domain_type"):
                if not _is_non_empty_text(parser_type.get(pf)):
                    errors.append(f"{label}.parser_type.{pf} must be a non-empty string.")

    orig_cases = binding.get("original_cases")
    if not isinstance(orig_cases, list):
        errors.append(f"{label}.original_cases must be a list.")
    else:
        for c_idx, case in enumerate(orig_cases):
            c_lbl = f"{label}.original_cases[{c_idx}]"
            if not isinstance(case, dict):
                errors.append(f"{c_lbl} must be an object.")
                continue
            _validate_strict_keys(case, {"kind", "evidence_id", "location"}, c_lbl, errors)
            if case.get("kind") not in _VALID_CASE_KINDS:
                errors.append(f"{c_lbl}.kind must be one of {sorted(_VALID_CASE_KINDS)}.")
            ev_id = case.get("evidence_id")
            if not isinstance(ev_id, str) or not _EVIDENCE_ID_RE.match(ev_id) or ev_id not in retained_ids:
                errors.append(f"{c_lbl}.evidence_id '{ev_id}' must reference a retained record.")
            if not _is_non_empty_text(case.get("location")):
                errors.append(f"{c_lbl}.location must be a non-empty string.")

    fixtures = binding.get("fixtures")
    fixture_case_kinds: Set[str] = set()
    if not isinstance(fixtures, list):
        errors.append(f"{label}.fixtures must be a list.")
    else:
        for f_idx, fix in enumerate(fixtures):
            f_lbl = f"{label}.fixtures[{f_idx}]"
            if not isinstance(fix, dict):
                errors.append(f"{f_lbl} must be an object.")
                continue
            _validate_strict_keys(fix, {"fixture_id", "case_kind", "authority", "evidence_ids"}, f_lbl, errors)
            if not isinstance(fix.get("fixture_id"), str) or not _STABLE_ID_RE.match(fix["fixture_id"]):
                errors.append(f"{f_lbl}.fixture_id must be a valid stable identifier.")
            ck = fix.get("case_kind")
            if ck not in _VALID_CASE_KINDS:
                errors.append(f"{f_lbl}.case_kind must be one of {sorted(_VALID_CASE_KINDS)}.")
            else:
                fixture_case_kinds.add(ck)
            if fix.get("authority") not in _VALID_PROOF_AUTHORITIES:
                errors.append(f"{f_lbl}.authority must be one of {sorted(_VALID_PROOF_AUTHORITIES)}.")
            ev_ids = fix.get("evidence_ids")
            if not isinstance(ev_ids, list) or len(ev_ids) == 0:
                errors.append(f"{f_lbl}.evidence_ids must be a non-empty list.")
            else:
                for ev_id in ev_ids:
                    if not isinstance(ev_id, str) or not _EVIDENCE_ID_RE.match(ev_id) or ev_id not in retained_ids:
                        errors.append(f"{f_lbl}.evidence_ids references missing retained evidence '{ev_id}'.")

    verifier = binding.get("verifier")
    if verifier is not None:
        v_lbl = f"{label}.verifier"
        if not isinstance(verifier, dict):
            errors.append(f"{v_lbl} must be null or an object.")
        else:
            _validate_strict_keys(
                verifier,
                {
                    "verifier_id", "claim_id", "command", "authority",
                    "status", "result_evidence_id", "enumerated_obligation_ids", "nondeterminism",
                },
                v_lbl,
                errors,
            )
            for id_f in ("verifier_id", "claim_id"):
                if not isinstance(verifier.get(id_f), str) or not _STABLE_ID_RE.match(verifier[id_f]):
                    errors.append(f"{v_lbl}.{id_f} must be a valid stable identifier.")
            if not _is_non_empty_text(verifier.get("command")):
                errors.append(f"{v_lbl}.command must be a non-empty string.")
            if verifier.get("authority") not in _VALID_PROOF_AUTHORITIES:
                errors.append(f"{v_lbl}.authority must be one of {sorted(_VALID_PROOF_AUTHORITIES)}.")
            if verifier.get("status") not in _VALID_VERIFIER_STATUSES:
                errors.append(f"{v_lbl}.status must be one of {sorted(_VALID_VERIFIER_STATUSES)}.")
            res_ev = verifier.get("result_evidence_id")
            if not isinstance(res_ev, str) or not _EVIDENCE_ID_RE.match(res_ev) or res_ev not in retained_ids:
                errors.append(f"{v_lbl}.result_evidence_id '{res_ev}' must reference a retained record.")
            enum_ids = verifier.get("enumerated_obligation_ids")
            if not isinstance(enum_ids, list) or len(enum_ids) == 0 or any(not isinstance(e, str) or not _STABLE_ID_RE.match(e) for e in enum_ids):
                errors.append(f"{v_lbl}.enumerated_obligation_ids must be a non-empty list of stable IDs.")
            elif isinstance(ob_id, str) and ob_id not in enum_ids:
                errors.append(f"{v_lbl} does not enumerate obligation '{ob_id}'.")
            nd = verifier.get("nondeterminism")
            if not isinstance(nd, dict):
                errors.append(f"{v_lbl}.nondeterminism must be an object.")
            else:
                _validate_strict_keys(nd, {"mode", "specification"}, f"{v_lbl}.nondeterminism", errors)
                if nd.get("mode") not in _VALID_NONDETERMINISM_MODES:
                    errors.append(f"{v_lbl}.nondeterminism.mode must be one of {sorted(_VALID_NONDETERMINISM_MODES)}.")
                if not _is_non_empty_text(nd.get("specification")):
                    errors.append(f"{v_lbl}.nondeterminism.specification must be a non-empty string.")

    ob = reviewed_by_id.get(ob_id) if isinstance(ob_id, str) else None
    if ob and ob.get("disposition") == "active" and ob.get("required") is True:
        if ob.get("requires_parser_type") and parser_type is None:
            errors.append(f"Active obligation '{ob_id}' requires parser_type binding.")
        req_kinds = ob.get("required_case_kinds")
        if isinstance(req_kinds, list):
            missing_kinds = [k for k in req_kinds if k not in fixture_case_kinds]
            if missing_kinds:
                errors.append(f"Active obligation '{ob_id}' is missing required fixture case kind(s): {', '.join(missing_kinds)}.")
        if verifier is None:
            errors.append(f"Active obligation '{ob_id}' is missing a verifier binding.")
        elif isinstance(verifier, dict) and verifier.get("status") != "pass":
            errors.append(f"Active obligation '{ob_id}' verifier status is '{verifier.get('status')}', expected 'pass'.")


def _validate_manifest(
    manifest: Any,
    retained_ids: Set[str],
    reviewed_by_id: Dict[str, Dict[str, Any]],
    errors: List[str],
) -> None:
    if not isinstance(manifest, dict):
        errors.append("Missing or invalid 'manifest' (must be a strictObject dictionary).")
        return

    _validate_strict_keys(manifest, _MANIFEST_KEYS, "manifest", errors)

    bindings = manifest.get("bindings")
    bound_ids: Set[str] = set()
    if not isinstance(bindings, list):
        errors.append("'manifest' must contain a 'bindings' list.")
    else:
        for idx, b in enumerate(bindings):
            _validate_binding_item(b, idx, retained_ids, reviewed_by_id, bound_ids, errors)

    for ob_id, ob in reviewed_by_id.items():
        if ob.get("disposition") == "active" and ob.get("required") is True and ob_id not in bound_ids:
            errors.append(f"Active required obligation '{ob_id}' has no owner binding in manifest.bindings.")

    contradictions = manifest.get("contradictions")
    if contradictions is None or not isinstance(contradictions, list):
        errors.append("'manifest' must contain a 'contradictions' list.")
    else:
        for idx, con in enumerate(contradictions):
            c_lbl = f"manifest.contradictions[{idx}]"
            if not isinstance(con, dict):
                errors.append(f"{c_lbl} must be an object.")
                continue
            _validate_strict_keys(con, {"obligation_id", "evidence_ids"}, c_lbl, errors)
            ev_ids = con.get("evidence_ids")
            if not isinstance(ev_ids, list) or len(ev_ids) < 2:
                errors.append(f"{c_lbl}.evidence_ids must list at least 2 contradicting evidence IDs.")
            else:
                for ev_id in ev_ids:
                    if ev_id not in retained_ids:
                        errors.append(f"{c_lbl} references missing retained evidence '{ev_id}'.")
        if len(contradictions) > 0:
            errors.append(f"Unresolved contradictions present in manifest ({len(contradictions)} items).")


def validate_obligation_ledger(ledger_path: Path | str) -> Tuple[bool, List[str]]:
    """
    Validates an obligation ledger JSON file against REA 6.9.0 strictObject schema
    and PSL-RE-001 / PSL-INV-002 evidence-backing invariants:
    1. Valid JSON strictObject without top-level '$schema'.
    2. 'evidence_bundle': complete bundle with valid, non-empty SHA-256 retained records and resolved unknowns.
    3. 'reviewed_obligations': non-empty list of strictObject obligations referencing retained evidence.
    4. 'manifest': bindings cross-checked against reviewed obligations & records, zero contradictions.
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

    if "$schema" in data:
        errors.append("Top-level '$schema' is not allowed in REA 6.9.0 schema.")

    expected_top = {"evidence_bundle", "reviewed_obligations", "manifest"}
    extra_top = sorted(set(data.keys()) - expected_top - {"$schema"})
    if extra_top:
        errors.append(f"Obligation ledger contains unrecognized top-level keys: {', '.join(extra_top)}.")

    retained_ids, latest_unknowns = _validate_evidence_bundle(data.get("evidence_bundle"), errors)
    reviewed_by_id = _validate_reviewed_obligations(data.get("reviewed_obligations"), retained_ids, latest_unknowns, errors)
    _validate_manifest(data.get("manifest"), retained_ids, reviewed_by_id, errors)

    return len(errors) == 0, errors


def scaffold_obligation_ledger(output_path: Path | str) -> Path:
    """
    Generates a starter typed obligation ledger adhering to REA 6.9.0 canonical bundle schema.
    Note: A newly scaffolded empty ledger fails validate_obligation_ledger() under PSL-RE-001 /
    PSL-INV-002 until populated with SHA-256 evidence records and bound reviewed obligations.
    """
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    template: Dict[str, Any] = {
        "evidence_bundle": {
            "artifacts": [],
            "captures": [],
            "environments": [],
            "providers": [],
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
