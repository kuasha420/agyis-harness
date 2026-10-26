# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Out-of-band auditor verdict schema, generation, and validation (ADR-014, ADR-022, Issue #66).
Provides dual-gate verification fence integration for independent auditor sign-off.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Optional, Tuple


@dataclass
class AuditVerdict:
    """Dataclass encapsulating out-of-band auditor verification verdict."""

    task_id: str
    verdict: str = "VICTORY CONFIRMED"
    protocol_version: str = "2026.1"
    auditor_role: str = "agyis_auditor"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    test_suite: dict = field(
        default_factory=lambda: {
            "command": "./agyis test",
            "exit_code": 0,
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "benchmark_latency_s": 0.0,
        }
    )
    doctor_audit: dict = field(
        default_factory=lambda: {
            "ok_count": 0,
            "missing_count": 0,
            "outdated_count": 0,
        }
    )
    path: Optional[Path] = None

    def to_dict(self) -> dict:
        d = {
            "protocol_version": self.protocol_version,
            "verdict": self.verdict,
            "task_id": self.task_id,
            "auditor_role": self.auditor_role,
            "timestamp": self.timestamp,
            "test_suite": dict(self.test_suite),
            "doctor_audit": dict(self.doctor_audit),
        }
        return d

    @classmethod
    def from_dict(cls, d: dict, path: Optional[Path] = None) -> AuditVerdict:
        return cls(
            protocol_version=str(d.get("protocol_version", "2026.1")),
            verdict=str(d.get("verdict", "VICTORY CONFIRMED")),
            task_id=str(d.get("task_id", "DEFAULT")),
            auditor_role=str(d.get("auditor_role", "agyis_auditor")),
            timestamp=str(d.get("timestamp", "")),
            test_suite=dict(d.get("test_suite") or {}),
            doctor_audit=dict(d.get("doctor_audit") or {}),
            path=path,
        )


def _find_candidate_verdict_file(
    workspace_dir: Path,
    brain_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Resolves the candidate audit verdict file according to the discovery order."""
    # 1. Environment variable override
    env_path = os.environ.get("AGYIS_AUDIT_VERDICT_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p

    # 2. workspace_dir / .agents / artifacts / audit_verdict.json
    p2 = workspace_dir / ".agents" / "artifacts" / "audit_verdict.json"
    if p2.is_file():
        return p2

    # 3. workspace_dir / .agents / teamwork / audit_verdict.json
    p3 = workspace_dir / ".agents" / "teamwork" / "audit_verdict.json"
    if p3.is_file():
        return p3

    # 4. brain_dir / audit_verdict.json
    if brain_dir:
        p4 = Path(brain_dir) / "audit_verdict.json"
        if p4.is_file():
            return p4

    # 5. Newest *audit_verdict*.json or *verdict*.json in artifacts or brain_dir
    candidates: list[Path] = []
    search_dirs = [workspace_dir / ".agents" / "artifacts"]
    if brain_dir and Path(brain_dir).is_dir():
        search_dirs.append(Path(brain_dir))

    for s_dir in search_dirs:
        if s_dir.is_dir():
            try:
                for item in s_dir.iterdir():
                    if item.is_file() and item.suffix.lower() == ".json":
                        name_lower = item.name.lower()
                        if "verdict" in name_lower:
                            candidates.append(item)
            except Exception:
                pass

    if candidates:
        # Sort by mtime descending
        candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return candidates[0]

    return None


def validate_audit_verdict(
    workspace_dir: Path,
    brain_dir: Optional[Path] = None,
    max_age_seconds: int = 3600,
    allow_synthetic: bool = False,
) -> Tuple[bool, Optional[str], Optional[AuditVerdict]]:
    """
    Validates the presence, structure, verdict, test suite status, and freshness
    of an out-of-band audit verdict (Gate 2).
    """
    candidate_path = _find_candidate_verdict_file(workspace_dir, brain_dir)
    if candidate_path is None or not candidate_path.is_file():
        return (
            False,
            "Out-of-band auditor clearance missing (audit_verdict.json not found)",
            None,
        )

    try:
        data = json.loads(candidate_path.read_text(encoding="utf-8"))
    except Exception as err:
        return (False, f"Corrupted audit verdict file: {err}", None)

    if not isinstance(data, dict):
        return (False, "Corrupted audit verdict file: root must be JSON object", None)

    verdict_obj = AuditVerdict.from_dict(data, path=candidate_path)

    # Verdict status validation
    v_norm = verdict_obj.verdict.strip().upper()
    if v_norm not in ("VICTORY CONFIRMED", "PASS"):
        return (
            False,
            f"Auditor rejected victory ({verdict_obj.verdict})",
            verdict_obj,
        )

    # Test suite result validation
    test_suite = verdict_obj.test_suite
    exit_code = test_suite.get("exit_code", -1)
    failed_tests = test_suite.get("failed_tests", 0)

    if not allow_synthetic:
        if exit_code != 0 or failed_tests != 0:
            return (
                False,
                f"Test suite reported failure (exit code {exit_code}, {failed_tests} failed)",
                verdict_obj,
            )

    # Freshness / staleness validation
    if not allow_synthetic and max_age_seconds > 0:
        ts_str = verdict_obj.timestamp
        if not ts_str:
            return (False, "Audit verdict timestamp missing", verdict_obj)
        try:
            # Handle ISO-8601 timestamps
            if ts_str.endswith("Z"):
                ts_str_clean = ts_str[:-1] + "+00:00"
            else:
                ts_str_clean = ts_str
            dt = datetime.fromisoformat(ts_str_clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            age_s = (now_utc - dt).total_seconds()
            if age_s > max_age_seconds:
                return (
                    False,
                    f"Audit verdict is stale ({int(age_s)}s > {max_age_seconds}s limit)",
                    verdict_obj,
                )
        except Exception as err:
            return (False, f"Unparseable audit verdict timestamp: {err}", verdict_obj)

    return (True, None, verdict_obj)


def generate_audit_verdict(
    workspace_dir: Path,
    task_id: str = "DEFAULT",
    verdict: str = "VICTORY CONFIRMED",
    test_suite_result: Optional[dict] = None,
    doctor_result: Optional[dict] = None,
    output_path: Optional[Path] = None,
    auditor_role: str = "agyis_auditor",
) -> AuditVerdict:
    """
    Generates and persists an AuditVerdict JSON artifact.
    Default destination is <workspace_dir>/.agents/artifacts/audit_verdict.json.
    """
    dest = output_path or (workspace_dir / ".agents" / "artifacts" / "audit_verdict.json")
    dest.parent.mkdir(parents=True, exist_ok=True)

    default_suite = {
        "command": "./agyis test",
        "exit_code": 0,
        "total_tests": 0,
        "passed_tests": 0,
        "failed_tests": 0,
        "benchmark_latency_s": 0.0,
    }
    if test_suite_result:
        default_suite.update(test_suite_result)

    default_doctor = {
        "ok_count": 0,
        "missing_count": 0,
        "outdated_count": 0,
    }
    if doctor_result:
        default_doctor.update(doctor_result)

    verdict_obj = AuditVerdict(
        task_id=task_id,
        verdict=verdict,
        protocol_version="2026.1",
        auditor_role=auditor_role,
        timestamp=datetime.now(timezone.utc).isoformat(),
        test_suite=default_suite,
        doctor_audit=default_doctor,
        path=dest,
    )

    dest.write_text(json.dumps(verdict_obj.to_dict(), indent=2), encoding="utf-8")
    return verdict_obj
