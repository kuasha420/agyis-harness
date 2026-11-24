# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Data models, default boundary rules, and constants for Architectural Fitness (AFF)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


def aff_exempt(obj: Any = None) -> Any:
    """Decorator or marker to exempt functions, classes, or modules from architectural fitness checks."""
    if obj is None:
        return lambda target: target
    return obj


@dataclass
class BoundaryRule:
    """Declares an architectural boundary constraint between source packages and target modules."""

    source_pattern: str
    forbidden_targets: List[str]
    rule_name: str
    severity: str = "CRITICAL"  # "CRITICAL", "MAJOR", "WARNING"
    description: str = ""
    remediation: str = ""
    exemptions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BoundaryDefect:
    """Represents an illegal import violating an architectural boundary rule."""

    source_file: str
    line_number: int
    imported_module: str
    rule_name: str
    severity: str  # "CRITICAL", "MAJOR", "WARNING"
    remediation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CycleDefect:
    """Represents a circular dependency path detected across package modules."""

    cycle_path: List[str]
    severity: str = "CRITICAL"
    remediation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SmellDefect:
    """Represents a structural anti-pattern or code smell detected via AST."""

    file: str
    line_number: int
    smell_type: str  # "FOREIGN_LANGUAGE_MONOLITH", "GOD_COMPONENT", "UNBOUNDED_CACHE"
    severity: str  # "CRITICAL", "MAJOR", "WARNING"
    description: str
    remediation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArchitecturalFitnessReport:
    """Consolidated assessment report containing fitness score, status, and defect breakdown."""

    status: str  # "PASS", "FAIL", "WARNING"
    score: float  # 0.0 to 100.0
    boundary_defects: List[BoundaryDefect]
    cycle_defects: List[CycleDefect]
    smell_defects: List[SmellDefect]
    benchmark_latency_s: float
    scanned_files_count: int
    scanned_assets_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "score": round(self.score, 1),
            "boundary_defects": [d.to_dict() for d in self.boundary_defects],
            "cycle_defects": [d.to_dict() for d in self.cycle_defects],
            "smell_defects": [d.to_dict() for d in self.smell_defects],
            "benchmark_latency_s": round(self.benchmark_latency_s, 4),
            "scanned_files_count": self.scanned_files_count,
            "scanned_assets_count": self.scanned_assets_count,
        }


DEFAULT_BOUNDARY_RULES: List[BoundaryRule] = [
    BoundaryRule(
        source_pattern="harness/**",
        forbidden_targets=["pipeline", "tests", "data", "scripts", "scratch"],
        rule_name="BIFURCATION_INVARIANT",
        severity="CRITICAL",
        description="Distributable harness product runtime must never import project-level pipeline, tests, data, scripts, or scratch (ADR-014, PSL-INV-008).",
        remediation="Decouple product runtime from development pipeline scripts and test suites.",
        exemptions=[],
    ),
    BoundaryRule(
        source_pattern="harness/runtime/**",
        forbidden_targets=["harness.commands", "harness/commands", "harness.cli", "harness/cli"],
        rule_name="LAYER_DIRECTION",
        severity="CRITICAL",
        description="Runtime core must never import command dispatchers or CLI entrypoints.",
        remediation="Invert dependency or extract shared utility down into harness/runtime or harness/core.",
    ),
    BoundaryRule(
        source_pattern="harness/**",
        forbidden_targets=[".dirtyroom", "dirtyroom"],
        rule_name="CLEANROOM_MEMBRANE",
        severity="CRITICAL",
        description="Harness product must maintain a strict cleanroom membrane and never import dirtyroom artifacts (PSL-RE-001 / PSL-INV-008).",
        remediation="Maintain cleanroom isolation; reverse-engineering artifacts must remain quarantined in .dirtyroom/.",
    ),
]

IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".dirtyroom",
    "node_modules",
    ".venv",
    "venv",
    ".system_generated",
    "build",
    "dist",
    ".cache",
    ".next",
    ".turbo",
    ".agyis",
    ".psl",
}

MAX_MODULE_LINES = 800
MAX_TOP_LEVEL_DEFS = 25
