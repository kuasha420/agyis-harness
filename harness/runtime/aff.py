# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Architectural Fitness Function (AFF) & Macro Governance Engine (ADR-014 / Phase 1).

Enforces structural fitness invariants, cleanroom boundaries, and anti-rot metrics:
- Import boundary auditing (Bifurcation Invariant, Layer Direction, Cleanroom Membrane)
- Circular dependency cycle detection (DFS on AST import graphs)
- Structural smell auditing (Foreign language monoliths, God components, Unbounded caches)
- Hermetic, zero-dependency (<0.25s latency benchmark) CPython stdlib runtime
"""

from __future__ import annotations

from collections import defaultdict
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from harness.utils.state import atomic_write_json, get_state_dir

from .aff_extract import (
    _extract_js_cache_smells,
    _extract_uncached_parallel,
    _is_exempt_file,
)
from .aff_models import (
    ArchitecturalFitnessReport,
    BoundaryDefect,
    BoundaryRule,
    CycleDefect,
    DEFAULT_BOUNDARY_RULES,
    IGNORED_DIRS,
    MAX_MODULE_LINES,
    MAX_TOP_LEVEL_DEFS,
    SmellDefect,
    aff_exempt,
)

__all__ = [
    "ArchitecturalFitnessReport", "BoundaryDefect", "BoundaryRule", "CycleDefect",
    "DEFAULT_BOUNDARY_RULES", "IGNORED_DIRS", "MAX_AFF_DISK_CACHE", "MAX_JS_ASSETS",
    "MAX_MODULE_LINES", "MAX_SCANNED_FILES", "MAX_TOP_LEVEL_DEFS",
    "SmellDefect", "aff_exempt", "audit_architectural_fitness", "audit_dependency_cycles",
    "audit_import_boundaries", "audit_structural_smells",
]

MAX_AFF_DISK_CACHE = 1024
MAX_SCANNED_FILES = 10_000
MAX_JS_ASSETS = 2_000
_AFF_CACHE_VERSION = 1


def _discover_workspace_files(base_dir: Path) -> Tuple[List[Path], List[Path]]:
    """Single os.walk discovering bounded .py and .js files while skipping ignored dirs."""
    py_files: List[Path] = []
    js_files: List[Path] = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        root_path = Path(root)
        for f in files:
            if f.endswith(".py"):
                py_files.append(root_path / f)
            elif f.endswith(".js"):
                js_files.append(root_path / f)
    py_files.sort()
    js_files.sort()
    return py_files[:MAX_SCANNED_FILES], js_files[:MAX_JS_ASSETS]


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
    return rel_posix.startswith(pat) if pat.endswith("/") else (rel_posix == pat or rel_posix.startswith(pat + "/"))


def _normalize_target(target: str) -> str:
    """Normalizes forbidden target specifier to dot-delimited module name."""
    return target.strip().replace("\\", "/").strip("/").lstrip(". ").replace("/", ".")


def _matches_forbidden_target(imported: str, forbidden_target: str) -> bool:
    """Evaluates whether an imported module matches or resides within a forbidden target."""
    norm = _normalize_target(forbidden_target)
    return bool(norm) and (imported == norm or imported.startswith(f"{norm}."))


def _collect_pkg_facts(py_files: List[Path], parsed_cache: Optional[Dict[Path, Any]] = None) -> Dict[Path, Dict[str, Any]]:
    """Collects per-file structural facts using in-memory cache + bounded blake2b disk cache."""
    facts_by_file: Dict[Path, Dict[str, Any]] = {}
    if not py_files:
        return facts_by_file

    cache_file = get_state_dir() / f"aff_facts_v{_AFF_CACHE_VERSION}.json"
    disk_cache: Dict[str, Dict[str, Any]] = {}
    if len(py_files) >= 16:
        try:
            if cache_file.is_file():
                loaded = json.loads(cache_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    if len(loaded) > MAX_AFF_DISK_CACHE:
                        keep = list(loaded.keys())[-MAX_AFF_DISK_CACHE:]
                        disk_cache = {k: loaded[k] for k in keep}
                    else:
                        disk_cache = loaded
        except (OSError, json.JSONDecodeError, ValueError):
            disk_cache = {}

    misses: List[Path] = []
    for p in py_files:
        if parsed_cache is not None and isinstance(parsed_cache.get(p), dict):
            facts_by_file[p] = parsed_cache[p]
            continue
        if disk_cache:
            try:
                dg = hashlib.blake2b(p.read_bytes(), digest_size=16).hexdigest()
                entry = disk_cache.get(dg)
                if isinstance(entry, dict):
                    facts_by_file[p] = entry
                    if parsed_cache is not None:
                        if len(parsed_cache) >= MAX_SCANNED_FILES:
                            parsed_cache.clear()
                        parsed_cache[p] = entry
                    continue
            except OSError:
                pass
        misses.append(p)

    if misses:
        extracted = _extract_uncached_parallel(misses)
        updated_disk = False
        for p, (dg, facts) in extracted.items():
            facts_by_file[p] = facts
            if parsed_cache is not None:
                if len(parsed_cache) >= MAX_SCANNED_FILES:
                    parsed_cache.clear()
                parsed_cache[p] = facts
            if dg and len(py_files) >= 16:
                while dg not in disk_cache and len(disk_cache) >= MAX_AFF_DISK_CACHE:
                    disk_cache.pop(next(iter(disk_cache)))
                disk_cache[dg] = facts
                updated_disk = True
        if updated_disk:
            try:
                atomic_write_json(cache_file, disk_cache)
            except OSError:
                pass
    return facts_by_file


def _evaluate_boundaries(
    root_path: Path, py_files: List[Path], facts_by_file: Dict[Path, Dict[str, Any]], active_rules: List[BoundaryRule],
) -> List[BoundaryDefect]:
    """Evaluates boundary rules against pre-extracted file import facts."""
    defects: List[BoundaryDefect] = []
    norm_rules = [(r, [_normalize_target(f) for f in r.forbidden_targets if _normalize_target(f)]) for r in active_rules]

    for py_file in py_files:
        try:
            rel_posix = py_file.relative_to(root_path).as_posix()
        except ValueError:
            rel_posix = py_file.as_posix()

        applicable = [
            (r, f_norms) for r, f_norms in norm_rules
            if _match_source_pattern(rel_posix, r.source_pattern)
            and rel_posix not in r.exemptions
            and not any(_match_source_pattern(rel_posix, ex) for ex in r.exemptions)
        ]
        if not applicable:
            continue

        facts = facts_by_file.get(py_file)
        if not facts or facts.get("parse_defect") or facts.get("exempt"):
            continue

        base_parts = rel_posix[:-3].split("/")[:-1]
        for _, line_no, is_from, level, mod, names in facts.get("imports", ()):
            imported_modules: List[str] = []
            if is_from == 0:
                imported_modules.extend(names)
            elif level and level > 0:
                if level <= len(base_parts):
                    rel_target = list(base_parts[: len(base_parts) - (level - 1)])
                    if mod:
                        rel_target.extend(mod.split("."))
                    base_mod = ".".join(rel_target)
                    imported_modules.extend(f"{base_mod}.{nm}" if base_mod else nm for nm in names)
                    if not names and base_mod:
                        imported_modules.append(base_mod)
                elif mod:
                    imported_modules.append(mod)
                    imported_modules.extend(f"{mod}.{nm}" for nm in names)
                else:
                    imported_modules.extend(names)
            else:
                imported_modules.extend(f"{mod}.{nm}" if mod else nm for nm in names)
                if not names and mod:
                    imported_modules.append(mod)

            for rule, f_norms in applicable:
                matched_imp = next(
                    (imp for imp in imported_modules if imp and any(imp == norm or imp.startswith(f"{norm}.") for norm in f_norms)),
                    None,
                )
                if matched_imp:
                    defects.append(BoundaryDefect(
                        source_file=rel_posix, line_number=line_no, imported_module=matched_imp,
                        rule_name=rule.rule_name, severity=rule.severity, remediation=rule.remediation,
                    ))
    return defects


def _evaluate_cycles(root_path: Path, py_files: List[Path], facts_by_file: Dict[Path, Dict[str, Any]]) -> List[CycleDefect]:
    """Detects circular dependency loops across pre-extracted module import facts."""
    file_to_mod: Dict[Path, str] = {}
    known_modules: Set[str] = set()
    for p in py_files:
        try:
            parts = list(p.relative_to(root_path).parts)
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
        facts = facts_by_file.get(p)
        if not facts or facts.get("parse_defect") or facts.get("exempt"):
            continue
        mod_parts = mod.split(".")
        base_parts = mod_parts[:-1] if p.name != "__init__.py" else mod_parts

        for in_tc, _, is_from, level, raw_mod, names in facts.get("imports", ()):
            if in_tc:
                continue
            if is_from == 0:
                for imp in names:
                    curr = imp
                    while curr:
                        if curr in known_modules and curr != mod:
                            graph[mod].add(curr)
                            break
                        curr = curr.rsplit(".", 1)[0] if "." in curr else ""
            else:
                mod_prefix = ""
                if level and level > 0:
                    if level <= len(base_parts):
                        mod_prefix = ".".join(base_parts[: len(base_parts) - (level - 1)] + (raw_mod.split(".") if raw_mod else []))
                else:
                    mod_prefix = raw_mod
                for nm in names:
                    full_cand = f"{mod_prefix}.{nm}" if mod_prefix else nm
                    if full_cand in known_modules and full_cand != mod:
                        graph[mod].add(full_cand)
                    else:
                        curr = mod_prefix
                        while curr:
                            if curr in known_modules and curr != mod:
                                graph[mod].add(curr)
                                break
                            curr = curr.rsplit(".", 1)[0] if "." in curr else ""

    state: Dict[str, int] = {}
    path_stack: List[str] = []
    seen_cycles: Set[Tuple[str, ...]] = set()
    cycle_defects: List[CycleDefect] = []

    def dfs(u: str) -> None:
        state[u] = 1
        path_stack.append(u)
        for v in sorted(graph.get(u, set())):
            if state.get(v, 0) == 1:
                try:
                    raw_cycle = path_stack[path_stack.index(v) :] + [v]
                    cycle_nodes = raw_cycle[:-1]
                    min_idx = cycle_nodes.index(min(cycle_nodes))
                    canon = tuple(cycle_nodes[min_idx:] + cycle_nodes[:min_idx])
                    if canon not in seen_cycles:
                        seen_cycles.add(canon)
                        cycle_defects.append(CycleDefect(
                            cycle_path=raw_cycle, severity="CRITICAL",
                            remediation=f"Break circular import between '{v}' and '{u}' via dependency inversion, moving shared models to leaf module, or using runtime import.",
                        ))
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


def _evaluate_smells(root_path: Path, py_files: List[Path], js_files: List[Path], facts_by_file: Dict[Path, Dict[str, Any]]) -> List[SmellDefect]:
    """Evaluates structural smells from pre-extracted Python facts and JS assets."""
    smells: List[SmellDefect] = []
    for py_file in py_files:
        try:
            rel_posix = py_file.relative_to(root_path).as_posix()
        except ValueError:
            rel_posix = py_file.as_posix()
        facts = facts_by_file.get(py_file)
        if not facts:
            continue
        pdef = facts.get("parse_defect")
        if pdef is not None:
            smells.append(SmellDefect(rel_posix, pdef[0], "SYNTAX_ERROR", "CRITICAL", pdef[1], pdef[2]))
            continue
        if facts.get("exempt"):
            continue
        total_lines = facts.get("total_lines", 0)
        if total_lines > MAX_MODULE_LINES:
            smells.append(SmellDefect(
                rel_posix, 1, "GOD_COMPONENT", "MAJOR",
                f"Module exceeds {MAX_MODULE_LINES} lines ({total_lines} lines). High structural complexity.",
                "Decompose module into cohesive submodules or encapsulate into a dedicated subpackage.",
            ))
        top_defs = facts.get("top_level_defs", 0)
        if top_defs > MAX_TOP_LEVEL_DEFS:
            smells.append(SmellDefect(
                rel_posix, 1, "GOD_COMPONENT", "MAJOR",
                f"Module contains {top_defs} top-level definitions (threshold: {MAX_TOP_LEVEL_DEFS}).",
                "Refactor top-level procedures into cohesive domain classes or separate service modules.",
            ))
        for cls_name, cls_line, mcnt in facts.get("class_methods", ()):
            if mcnt > MAX_TOP_LEVEL_DEFS:
                smells.append(SmellDefect(
                    rel_posix, cls_line, "GOD_COMPONENT", "MAJOR",
                    f"Class '{cls_name}' defines {mcnt} methods (threshold: {MAX_TOP_LEVEL_DEFS}).",
                    "Decompose God class into focused collaborator classes or service modules.",
                ))
        for line_no, stype, sev, desc, rem in facts.get("smells", ()):
            smells.append(SmellDefect(rel_posix, line_no, stype, sev, desc, rem))

    for js_file in js_files:
        try:
            rel_posix = js_file.relative_to(root_path).as_posix()
            js_content = js_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _is_exempt_file(js_content):
            js_lines = len(js_content.splitlines())
            if js_lines > MAX_MODULE_LINES:
                smells.append(SmellDefect(
                    rel_posix, 1, "GOD_COMPONENT", "MAJOR",
                    f"JS asset exceeds {MAX_MODULE_LINES} lines ({js_lines} lines). High frontend complexity.",
                    "Modularize frontend JS asset into focused ES submodules under assets/ <= 800 lines.",
                ))
            for line_no, stype, sev, desc, rem in _extract_js_cache_smells(rel_posix, js_content):
                smells.append(SmellDefect(rel_posix, line_no, stype, sev, desc, rem))
    return smells


def audit_import_boundaries(
    root_dir: Path, rules: Optional[List[BoundaryRule]] = None, parsed_cache: Optional[Dict[Path, Any]] = None, target_pkg: Optional[str] = None,
) -> List[BoundaryDefect]:
    """Audits source files under root_dir for illegal import boundaries."""
    active_rules = rules if rules is not None else DEFAULT_BOUNDARY_RULES
    if not active_rules:
        return []
    root_path = Path(root_dir).resolve()
    scan_dirs: List[Path] = []
    if target_pkg and (root_path / target_pkg).is_dir():
        scan_dirs = [root_path / target_pkg]
    else:
        concrete_roots: List[Path] = []
        has_wildcard_root = False
        for r in active_rules:
            first_seg = r.source_pattern.strip().replace("\\", "/").split("/", 1)[0]
            if not first_seg or any(ch in first_seg for ch in ("*", "?", "[")):
                has_wildcard_root = True
                break
            cand = root_path / first_seg
            if cand.is_dir():
                concrete_roots.append(cand)
        scan_dirs = [root_path] if has_wildcard_root else list(dict.fromkeys(concrete_roots))

    py_files_set: Set[Path] = set()
    for sdir in scan_dirs:
        py_files_set.update(_discover_workspace_files(sdir)[0])
    py_files = sorted(py_files_set)
    facts_by_file = _collect_pkg_facts(py_files, parsed_cache=parsed_cache)
    return _evaluate_boundaries(root_path, py_files, facts_by_file, active_rules)


def audit_dependency_cycles(
    root_dir: Path, target_pkg: str = "harness", parsed_cache: Optional[Dict[Path, Any]] = None,
) -> List[CycleDefect]:
    """Builds module dependency graph and detects circular dependency cycles across target_pkg."""
    root_path = Path(root_dir).resolve()
    pkg_dir = root_path / target_pkg if (root_path / target_pkg).is_dir() else root_path
    py_files, _ = _discover_workspace_files(pkg_dir)
    return _evaluate_cycles(root_path, py_files, _collect_pkg_facts(py_files, parsed_cache=parsed_cache))


def audit_structural_smells(
    root_dir: Path, target_pkg: str = "harness", parsed_cache: Optional[Dict[Path, Any]] = None,
) -> List[SmellDefect]:
    """Audits Python modules and JS assets for structural code smells."""
    root_path = Path(root_dir).resolve()
    pkg_dir = root_path / target_pkg if (root_path / target_pkg).is_dir() else root_path
    py_files, js_files = _discover_workspace_files(pkg_dir)
    return _evaluate_smells(root_path, py_files, js_files, _collect_pkg_facts(py_files, parsed_cache=parsed_cache))


def audit_architectural_fitness(
    workspace_root: Optional[Path] = None, rules: Optional[List[BoundaryRule]] = None, target_pkg: str = "harness",
) -> ArchitecturalFitnessReport:
    """Orchestrates the complete AFF audit suite in a single file-discovery walk and single AST extraction pass."""
    start_t = time.perf_counter()
    root = (Path(workspace_root) if workspace_root else Path.cwd()).resolve()
    pkg_dir = root / target_pkg if (root / target_pkg).is_dir() else root
    py_files, js_files = _discover_workspace_files(pkg_dir)
    active_rules = rules if rules is not None else DEFAULT_BOUNDARY_RULES

    parsed_cache: Dict[Path, Any] = {}
    facts_by_file = _collect_pkg_facts(py_files, parsed_cache=parsed_cache)
    if rules is None and target_pkg == "harness" and (root / "harness").is_dir():
        boundary_defects = _evaluate_boundaries(root, py_files, facts_by_file, active_rules)
    else:
        boundary_defects = audit_import_boundaries(root_dir=root, rules=active_rules, parsed_cache=parsed_cache, target_pkg=target_pkg)
    cycle_defects = _evaluate_cycles(root, py_files, facts_by_file)
    smell_defects = _evaluate_smells(root, py_files, js_files, facts_by_file)
    elapsed = time.perf_counter() - start_t

    score = 100.0
    for b in boundary_defects:
        score -= 25.0 if b.severity == "CRITICAL" else (10.0 if b.severity == "MAJOR" else 5.0)
    for c in cycle_defects:
        score -= 25.0 if c.severity == "CRITICAL" else 10.0
    for s in smell_defects:
        score -= 25.0 if s.severity == "CRITICAL" else (10.0 if s.severity == "MAJOR" else 5.0)
    score = max(0.0, min(100.0, score))

    all_defects = boundary_defects + cycle_defects + smell_defects
    if any(d.severity in ("CRITICAL", "MAJOR") for d in all_defects) or score < 80.0:
        status = "FAIL"
    elif all_defects or score < 100.0:
        status = "WARNING"
    else:
        status = "PASS"

    return ArchitecturalFitnessReport(
        status=status, score=score, boundary_defects=boundary_defects, cycle_defects=cycle_defects,
        smell_defects=smell_defects, benchmark_latency_s=elapsed,
        scanned_files_count=len(py_files), scanned_assets_count=len(js_files),
    )
