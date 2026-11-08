# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Architectural Fitness Function (AFF) & Macro Governance Engine (ADR-014 / Phase 1).

Enforces structural fitness invariants, cleanroom boundaries, and anti-rot metrics:
- Import boundary auditing (Bifurcation Invariant, Layer Direction, Cleanroom Membrane)
- Circular dependency cycle detection (DFS / Tarjan's SCC on AST import graphs)
- Structural smell auditing (Foreign language monoliths, God components, Unbounded caches)
- Hermetic, zero-dependency (<0.25s latency benchmark) CPython stdlib runtime
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import asdict, dataclass, field
import fnmatch
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "score": round(self.score, 1),
            "boundary_defects": [d.to_dict() for d in self.boundary_defects],
            "cycle_defects": [d.to_dict() for d in self.cycle_defects],
            "smell_defects": [d.to_dict() for d in self.smell_defects],
            "benchmark_latency_s": round(self.benchmark_latency_s, 4),
            "scanned_files_count": self.scanned_files_count,
        }


DEFAULT_BOUNDARY_RULES: List[BoundaryRule] = [
    BoundaryRule(
        source_pattern="harness/**",
        forbidden_targets=["pipeline", "tests", "data", "scripts", "scratch"],
        rule_name="BIFURCATION_INVARIANT",
        severity="CRITICAL",
        description="Distributable harness product runtime must never import project-level pipeline, tests, data, scripts, or scratch (ADR-014).",
        remediation="Decouple product runtime from development pipeline scripts and test suites.",
        exemptions=[
            "harness/commands/audit.py",
            "harness/commands/sync.py",
            "harness/telemetry/sync/daemon.py",
        ],
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
        description="Harness product must maintain a strict cleanroom membrane and never import dirtyroom artifacts (PSL-INV-007).",
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


def _discover_python_files(base_dir: Path) -> List[Path]:
    """Fast directory traversal discovering python files while skipping ignored paths."""
    py_files: List[Path] = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        for f in files:
            if f.endswith(".py"):
                py_files.append(Path(root) / f)
    return sorted(py_files)


def _match_source_pattern(rel_posix: str, pattern: str) -> bool:
    """Evaluates whether relative file path matches a rule's source pattern."""
    pat = pattern.strip().replace("\\", "/")
    if pat.endswith("/**"):
        prefix = pat[:-3]
        return rel_posix == prefix or rel_posix.startswith(prefix + "/")
    if pat.endswith("/*"):
        prefix = pat[:-2]
        return rel_posix.startswith(prefix + "/") and "/" not in rel_posix[len(prefix) + 1 :]
    if fnmatch.fnmatch(rel_posix, pat):
        return True
    if pat.endswith("/"):
        return rel_posix.startswith(pat)
    return rel_posix == pat or rel_posix.startswith(pat + "/")


def _normalize_target(target: str) -> str:
    """Normalizes forbidden target specifier to dot-delimited module name."""
    t = target.strip().replace("\\", "/").strip("/").lstrip(". ")
    return t.replace("/", ".")


def _matches_forbidden_target(imported: str, forbidden_target: str) -> bool:
    """Evaluates whether an imported module matches or resides within a forbidden target."""
    norm = _normalize_target(forbidden_target)
    if not norm:
        return False
    if imported == norm or imported.startswith(f"{norm}."):
        return True
    return False


def _is_exempt_file(content: str) -> bool:
    """Detects file-level AFF exemption pragmas."""
    first_lines = content[:2000].splitlines()
    for line in first_lines[:30]:
        stripped = line.strip()
        if (
            "# aff: exempt" in stripped
            or "# aff_exempt" in stripped
            or "__aff_exempt__ = True" in stripped
        ):
            return True
    return False


def _is_exempt_line(line: str) -> bool:
    """Detects line-level AFF exemption pragmas."""
    return "# aff: exempt" in line or "# aff_exempt" in line or "# noqa" in line


def _is_exempt_node(node: ast.AST) -> bool:
    """Detects whether AST definition node carries @aff_exempt decorator."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id == "aff_exempt":
                return True
            if isinstance(dec, ast.Attribute) and dec.attr == "aff_exempt":
                return True
            if isinstance(dec, ast.Call):
                f = dec.func
                if isinstance(f, ast.Name) and f.id == "aff_exempt":
                    return True
                if isinstance(f, ast.Attribute) and f.attr == "aff_exempt":
                    return True
    return False


def _parse_module(
    py_file: Path,
    parsed_cache: Optional[Dict[Path, Tuple[Optional[str], Optional[ast.AST], Optional[SmellDefect]]]] = None,
) -> Tuple[Optional[str], Optional[ast.AST], Optional[SmellDefect]]:
    """
    Safely reads and parses a python file into AST.

    Captures SyntaxError, UnicodeDecodeError, OSError, returning a SmellDefect on failure
    rather than silently swallowing corrupted or unparseable source files (DEFECT-01).
    """
    if parsed_cache is not None and py_file in parsed_cache:
        return parsed_cache[py_file]

    try:
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))
        res = (content, tree, None)
    except SyntaxError as e:
        defect = SmellDefect(
            file=str(py_file),
            line_number=e.lineno or 1,
            smell_type="SYNTAX_ERROR",
            severity="CRITICAL",
            description=f"SyntaxError in Python source: {e.msg}",
            remediation="Fix syntax error so module can be parsed and analyzed.",
        )
        res = (None, None, defect)
    except UnicodeDecodeError as e:
        defect = SmellDefect(
            file=str(py_file),
            line_number=1,
            smell_type="SYNTAX_ERROR",
            severity="CRITICAL",
            description=f"Encoding error: unable to decode UTF-8: {e}",
            remediation="Ensure file is valid UTF-8 text.",
        )
        res = (None, None, defect)
    except OSError as e:
        defect = SmellDefect(
            file=str(py_file),
            line_number=1,
            smell_type="SYNTAX_ERROR",
            severity="CRITICAL",
            description=f"I/O error reading file: {e}",
            remediation="Ensure file permissions and disk state are readable.",
        )
        res = (None, None, defect)
    except Exception as e:
        defect = SmellDefect(
            file=str(py_file),
            line_number=1,
            smell_type="SYNTAX_ERROR",
            severity="CRITICAL",
            description=f"Failed to parse Python module: {e}",
            remediation="Fix module so it can be parsed via ast.parse.",
        )
        res = (None, None, defect)

    if parsed_cache is not None:
        parsed_cache[py_file] = res
    return res


def _has_cache_bounds(func_node: ast.AST, cache_val: ast.AST) -> bool:
    """
    Evaluates whether an enclosing function or method contains bounds/eviction logic
    specifically tied to the target cache structure (DEFECT-04).
    """
    if isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for dec in func_node.decorator_list:
            dec_id = ""
            if isinstance(dec, ast.Name):
                dec_id = dec.id
            elif isinstance(dec, ast.Attribute):
                dec_id = dec.attr
            elif isinstance(dec, ast.Call):
                f = dec.func
                if isinstance(f, ast.Name):
                    dec_id = f.id
                elif isinstance(f, ast.Attribute):
                    dec_id = f.attr
            if "lru_cache" in dec_id or dec_id == "cache":
                return True

    target_attr = cache_val.attr if isinstance(cache_val, ast.Attribute) else None
    target_id = cache_val.id if isinstance(cache_val, ast.Name) else None

    def _matches_cache(node: ast.AST) -> bool:
        if target_attr and isinstance(node, ast.Attribute) and node.attr == target_attr:
            return True
        if target_id and isinstance(node, ast.Name) and node.id == target_id:
            return True
        return False

    for inner in ast.walk(func_node):
        if isinstance(inner, ast.Call):
            if isinstance(inner.func, ast.Name) and inner.func.id == "len":
                if inner.args and _matches_cache(inner.args[0]):
                    return True
            if isinstance(inner.func, ast.Attribute) and inner.func.attr in ("pop", "popitem", "clear", "evict"):
                if _matches_cache(inner.func.value):
                    return True

        if isinstance(inner, ast.Delete):
            for tgt in inner.targets:
                if isinstance(tgt, ast.Subscript) and _matches_cache(tgt.value):
                    return True

        if isinstance(inner, ast.Compare):
            has_len_cache = False
            for comp_node in [inner.left] + inner.comparators:
                if isinstance(comp_node, ast.Call) and isinstance(comp_node.func, ast.Name) and comp_node.func.id == "len":
                    if comp_node.args and _matches_cache(comp_node.args[0]):
                        has_len_cache = True
                        break
            if has_len_cache:
                return True

    return False


def audit_import_boundaries(
    root_dir: Path,
    rules: Optional[List[BoundaryRule]] = None,
    parsed_cache: Optional[Dict[Path, Tuple[Optional[str], Optional[ast.AST], Optional[SmellDefect]]]] = None,
) -> List[BoundaryDefect]:
    """
    Audits source files under root_dir for illegal import boundaries.

    Inspects ast.Import and ast.ImportFrom against specified rules (or DEFAULT_BOUNDARY_RULES).
    """
    active_rules = rules if rules is not None else DEFAULT_BOUNDARY_RULES
    if not active_rules:
        return []

    root_path = Path(root_dir).resolve()
    defects: List[BoundaryDefect] = []

    py_files = _discover_python_files(root_path)

    for py_file in py_files:
        try:
            rel_posix = py_file.relative_to(root_path).as_posix()
        except ValueError:
            rel_posix = py_file.as_posix()

        applicable_rules = [
            r
            for r in active_rules
            if _match_source_pattern(rel_posix, r.source_pattern)
            and rel_posix not in r.exemptions
            and not any(_match_source_pattern(rel_posix, ex) for ex in r.exemptions)
        ]

        if not applicable_rules:
            continue

        content, tree, _ = _parse_module(py_file, parsed_cache)
        if tree is None or content is None:
            continue

        if _is_exempt_file(content):
            continue

        lines = content.splitlines()

        parts = rel_posix[:-3].split("/")
        base_parts = parts[:-1]

        for node in ast.walk(tree):
            line_no = getattr(node, "lineno", 1)
            raw_line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
            if _is_exempt_line(raw_line):
                continue

            imported_modules: List[str] = []

            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    if node.level <= len(base_parts):
                        rel_target = list(base_parts[: len(base_parts) - (node.level - 1)])
                        if node.module:
                            rel_target.extend(node.module.split("."))
                        base_mod = ".".join(rel_target)
                        for alias in node.names:
                            imported_modules.append(f"{base_mod}.{alias.name}" if base_mod else alias.name)
                        if not node.names and base_mod:
                            imported_modules.append(base_mod)
                    else:
                        if node.module:
                            imported_modules.append(node.module)
                else:
                    mod = node.module or ""
                    for alias in node.names:
                        imported_modules.append(f"{mod}.{alias.name}" if mod else alias.name)
                    if not node.names and mod:
                        imported_modules.append(mod)

            for rule in applicable_rules:
                matched_target = None
                matched_imp = None
                for imp in imported_modules:
                    if not imp:
                        continue
                    for forbidden in rule.forbidden_targets:
                        if _matches_forbidden_target(imp, forbidden):
                            matched_target = forbidden
                            matched_imp = imp
                            break
                    if matched_target:
                        break

                if matched_target and matched_imp:
                    defects.append(
                        BoundaryDefect(
                            source_file=rel_posix,
                            line_number=line_no,
                            imported_module=matched_imp,
                            rule_name=rule.rule_name,
                            severity=rule.severity,
                            remediation=rule.remediation,
                        )
                    )

    return defects


def audit_dependency_cycles(
    root_dir: Path,
    target_pkg: str = "harness",
    parsed_cache: Optional[Dict[Path, Tuple[Optional[str], Optional[ast.AST], Optional[SmellDefect]]]] = None,
) -> List[CycleDefect]:
    """
    Builds module dependency graph and detects circular dependency cycles across target_pkg.

    Uses DFS cycle traversal on AST top-level imports to report minimal cycle paths (A -> B -> A).
    """
    root_path = Path(root_dir).resolve()
    pkg_dir = root_path / target_pkg if (root_path / target_pkg).is_dir() else root_path

    py_files = _discover_python_files(pkg_dir)

    file_to_mod: Dict[Path, str] = {}
    known_modules: Set[str] = set()

    for p in py_files:
        try:
            rel = p.relative_to(root_path)
            parts = list(rel.parts)
        except ValueError:
            parts = [p.stem]

        if parts and parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]

        mod_name = ".".join(parts)
        if mod_name:
            file_to_mod[p] = mod_name
            known_modules.add(mod_name)

    graph: Dict[str, Set[str]] = defaultdict(set)

    for p, mod in file_to_mod.items():
        content, tree, _ = _parse_module(p, parsed_cache)
        if tree is None or content is None:
            continue

        if _is_exempt_file(content):
            continue

        mod_parts = mod.split(".")
        base_parts = mod_parts[:-1] if p.name != "__init__.py" else mod_parts

        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imp = alias.name
                    if imp in known_modules and imp != mod:
                        graph[mod].add(imp)
                    else:
                        curr = imp
                        while "." in curr:
                            curr = curr.rsplit(".", 1)[0]
                            if curr in known_modules and curr != mod:
                                graph[mod].add(curr)
                                break
            elif isinstance(node, ast.ImportFrom):
                mod_prefix = ""
                if node.level and node.level > 0:
                    if node.level <= len(base_parts):
                        prefix = base_parts[: len(base_parts) - (node.level - 1)]
                        sub = node.module.split(".") if node.module else []
                        mod_prefix = ".".join(prefix + sub)
                else:
                    mod_prefix = node.module or ""

                for alias in node.names:
                    full_cand = f"{mod_prefix}.{alias.name}" if mod_prefix else alias.name
                    if full_cand in known_modules and full_cand != mod:
                        graph[mod].add(full_cand)
                    elif mod_prefix in known_modules and mod_prefix != mod:
                        graph[mod].add(mod_prefix)
                    else:
                        curr = mod_prefix
                        while "." in curr:
                            curr = curr.rsplit(".", 1)[0]
                            if curr in known_modules and curr != mod:
                                graph[mod].add(curr)
                                break

    state: Dict[str, int] = {}  # 0: UNVISITED, 1: VISITING, 2: VISITED
    path_stack: List[str] = []
    seen_cycles: Set[Tuple[str, ...]] = set()
    cycle_defects: List[CycleDefect] = []

    def dfs(u: str) -> None:
        state[u] = 1
        path_stack.append(u)
        for v in sorted(graph.get(u, set())):
            if state.get(v, 0) == 1:
                try:
                    idx = path_stack.index(v)
                    raw_cycle = path_stack[idx:] + [v]
                    cycle_nodes = raw_cycle[:-1]
                    min_idx = cycle_nodes.index(min(cycle_nodes))
                    canon = tuple(cycle_nodes[min_idx:] + cycle_nodes[:min_idx])
                    if canon not in seen_cycles:
                        seen_cycles.add(canon)
                        cycle_defects.append(
                            CycleDefect(
                                cycle_path=raw_cycle,
                                severity="CRITICAL",
                                remediation=(
                                    f"Break circular import between '{v}' and '{u}' via dependency "
                                    "inversion, moving shared models to leaf module, or using runtime import."
                                ),
                            )
                        )
                except ValueError:
                    pass
            elif state.get(v, 0) == 0:
                dfs(v)
        path_stack.pop()
        state[u] = 2

    for mod in sorted(known_modules):
        if state.get(mod, 0) == 0:
            dfs(mod)

    return cycle_defects


def audit_structural_smells(
    root_dir: Path,
    target_pkg: str = "harness",
    parsed_cache: Optional[Dict[Path, Tuple[Optional[str], Optional[ast.AST], Optional[SmellDefect]]]] = None,
) -> List[SmellDefect]:
    """
    Audits python modules for AST structural code smells:
    1. SYNTAX_ERROR: Corrupted or unparseable Python modules (CRITICAL).
    2. FOREIGN_LANGUAGE_MONOLITH: Multiline strings (>100 lines) containing HTML/JS/CSS/SQL.
    3. GOD_COMPONENT: Modules > 2,000 lines or > 30 top-level definitions without @aff_exempt.
    4. UNBOUNDED_CACHE: Dict cache assignments without capacity bounds (len()), LRU, or eviction.
    """
    root_path = Path(root_dir).resolve()
    pkg_dir = root_path / target_pkg if (root_path / target_pkg).is_dir() else root_path

    py_files = _discover_python_files(pkg_dir)
    smells: List[SmellDefect] = []

    frontend_patterns = [
        re.compile(r"<!DOCTYPE|<html|<body|<div|<script|</span|</table", re.I),
        re.compile(r"addEventListener|function\s*\(|const\s+\w+\s*=|document\.getElementById", re.I),
        re.compile(r"\{\s*display:\s*|@media\s+|font-family:|margin:\s*", re.I),
        re.compile(r"CREATE\s+TABLE.*CREATE\s+TABLE|INSERT\s+INTO.*SELECT", re.I | re.DOTALL),
    ]

    for py_file in py_files:
        try:
            rel_posix = py_file.relative_to(root_path).as_posix()
        except ValueError:
            rel_posix = py_file.as_posix()

        content, tree, parse_defect = _parse_module(py_file, parsed_cache)
        if parse_defect is not None:
            parse_defect.file = rel_posix
            smells.append(parse_defect)
            continue

        if tree is None or content is None:
            continue

        if _is_exempt_file(content):
            continue

        lines = content.splitlines()
        total_lines = len(lines)

        # 1. GOD_COMPONENT Check (>2000 lines or >30 top-level definitions)
        if total_lines > 2000:
            smells.append(
                SmellDefect(
                    file=rel_posix,
                    line_number=1,
                    smell_type="GOD_COMPONENT",
                    severity="MAJOR",
                    description=f"Module exceeds 2,000 lines ({total_lines} lines). High structural complexity.",
                    remediation="Decompose module into cohesive submodules or encapsulate into a dedicated subpackage.",
                )
            )

        top_level_defs = [
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not _is_exempt_node(n)
        ]
        if len(top_level_defs) > 30:
            smells.append(
                SmellDefect(
                    file=rel_posix,
                    line_number=1,
                    smell_type="GOD_COMPONENT",
                    severity="MAJOR",
                    description=f"Module contains {len(top_level_defs)} top-level definitions (threshold: 30).",
                    remediation="Refactor top-level procedures into cohesive domain classes or separate service modules.",
                )
            )

        # 2. FOREIGN_LANGUAGE_MONOLITH & 3. UNBOUNDED_CACHE Check
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s_val = node.value
                val_lines = s_val.splitlines()
                if len(val_lines) > 100:
                    if any(pat.search(s_val) for pat in frontend_patterns):
                        line_no = getattr(node, "lineno", 1)
                        raw_line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
                        if not _is_exempt_line(raw_line):
                            smells.append(
                                SmellDefect(
                                    file=rel_posix,
                                    line_number=line_no,
                                    smell_type="FOREIGN_LANGUAGE_MONOLITH",
                                    severity="MAJOR",
                                    description=(
                                        f"Multiline string constant ({len(val_lines)} lines) contains "
                                        "embedded foreign language markup/code (HTML/JS/CSS/SQL)."
                                    ),
                                    remediation=(
                                        "Decouple foreign language code into external static assets under "
                                        "assets/ and load dynamically via importlib.resources."
                                    ),
                                )
                            )

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _is_exempt_node(node):
                    continue

                for inner in ast.walk(node):
                    if isinstance(inner, (ast.Assign, ast.AugAssign)):
                        targets = inner.targets if isinstance(inner, ast.Assign) else [inner.target]
                        for tgt in targets:
                            if isinstance(tgt, ast.Subscript):
                                cache_val = None
                                cache_name = ""
                                if isinstance(tgt.value, ast.Attribute):
                                    attr_l = tgt.value.attr.lower()
                                    if "cache" in attr_l or "memo" in attr_l:
                                        cache_val = tgt.value
                                        cache_name = tgt.value.attr
                                elif isinstance(tgt.value, ast.Name):
                                    name_l = tgt.value.id.lower()
                                    if "cache" in name_l or "memo" in name_l:
                                        cache_val = tgt.value
                                        cache_name = tgt.value.id

                                if cache_val is not None:
                                    if not _has_cache_bounds(node, cache_val):
                                        line_no = getattr(inner, "lineno", node.lineno)
                                        raw_line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
                                        if not _is_exempt_line(raw_line):
                                            smells.append(
                                                SmellDefect(
                                                    file=rel_posix,
                                                    line_number=line_no,
                                                    smell_type="UNBOUNDED_CACHE",
                                                    severity="MAJOR",
                                                    description=(
                                                        f"Assignment to cache '{cache_name}[...]' inside "
                                                        f"method '{node.name}' without capacity checks "
                                                        "(len()), LRU, or eviction bounds."
                                                    ),
                                                    remediation=(
                                                        "Implement capacity guard (e.g. if len(cache) >= limit), "
                                                        "use functools.lru_cache, or bounded OrderedDict."
                                                    ),
                                                )
                                            )

    return smells


def audit_architectural_fitness(
    workspace_root: Optional[Path] = None,
    rules: Optional[List[BoundaryRule]] = None,
    target_pkg: str = "harness",
) -> ArchitecturalFitnessReport:
    """
    Orchestrates the complete Architectural Fitness Function (AFF) audit suite:
    - Boundary defect analysis
    - Dependency cycle detection
    - Structural smell detection
    - Benchmarking and overall scoring
    """
    start_t = time.perf_counter()
    root = (Path(workspace_root) if workspace_root else Path.cwd()).resolve()

    pkg_dir = root / target_pkg if (root / target_pkg).is_dir() else root
    py_files = _discover_python_files(pkg_dir)
    scanned_count = len(py_files)

    # Shared parsed AST cache for single-pass performance
    parsed_cache: Dict[Path, Tuple[Optional[str], Optional[ast.AST], Optional[SmellDefect]]] = {}

    boundary_defects = audit_import_boundaries(root_dir=root, rules=rules, parsed_cache=parsed_cache)
    cycle_defects = audit_dependency_cycles(root_dir=root, target_pkg=target_pkg, parsed_cache=parsed_cache)
    smell_defects = audit_structural_smells(root_dir=root, target_pkg=target_pkg, parsed_cache=parsed_cache)

    elapsed = time.perf_counter() - start_t

    score = 100.0
    for b in boundary_defects:
        score -= 25.0 if b.severity == "CRITICAL" else (10.0 if b.severity == "MAJOR" else 5.0)
    for c in cycle_defects:
        score -= 25.0 if c.severity == "CRITICAL" else 10.0
    for s in smell_defects:
        score -= 25.0 if s.severity == "CRITICAL" else (10.0 if s.severity == "MAJOR" else 5.0)

    score = max(0.0, min(100.0, score))

    has_critical = any(
        d.severity == "CRITICAL"
        for d in (boundary_defects + cycle_defects + smell_defects)
    )
    has_major = any(
        d.severity == "MAJOR"
        for d in (boundary_defects + cycle_defects + smell_defects)
    )

    if has_critical or has_major or score < 80.0:
        status = "FAIL"
    elif boundary_defects or cycle_defects or smell_defects or score < 100.0:
        status = "WARNING"
    else:
        status = "PASS"

    return ArchitecturalFitnessReport(
        status=status,
        score=score,
        boundary_defects=boundary_defects,
        cycle_defects=cycle_defects,
        smell_defects=smell_defects,
        benchmark_latency_s=elapsed,
        scanned_files_count=scanned_count,
    )
