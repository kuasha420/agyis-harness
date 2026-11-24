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
import fnmatch
import os
from pathlib import Path
import re
import time
from typing import Dict, List, Optional, Set, Tuple

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
    "ArchitecturalFitnessReport",
    "BoundaryDefect",
    "BoundaryRule",
    "CycleDefect",
    "DEFAULT_BOUNDARY_RULES",
    "IGNORED_DIRS",
    "MAX_MODULE_LINES",
    "MAX_TOP_LEVEL_DEFS",
    "SmellDefect",
    "aff_exempt",
    "audit_architectural_fitness",
    "audit_dependency_cycles",
    "audit_import_boundaries",
    "audit_structural_smells",
]


def _discover_files(base_dir: Path, suffix: str) -> List[Path]:
    """Fast traversal discovering files matching suffix while skipping ignored paths."""
    found: List[Path] = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        for f in files:
            if f.endswith(suffix):
                found.append(Path(root) / f)
    return sorted(found)


def _discover_python_files(base_dir: Path) -> List[Path]:
    return _discover_files(base_dir, ".py")


def _discover_asset_files(base_dir: Path) -> List[Path]:
    return _discover_files(base_dir, ".js")


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
    return bool(norm) and (imported == norm or imported.startswith(f"{norm}."))


def _is_exempt_file(content: str) -> bool:
    """Detects file-level AFF exemption pragmas."""
    markers = ("# aff: exempt", "# aff_exempt", "__aff_exempt__ = True", "// aff: exempt", "/* aff: exempt")
    return any(any(m in line for m in markers) for line in content[:2000].splitlines()[:30])


def _is_exempt_line(line: str) -> bool:
    """Detects explicit line-level AFF exemption pragmas (does NOT honor generic # noqa)."""
    return "# aff: exempt" in line or "# aff_exempt" in line


def _is_exempt_node(node: ast.AST) -> bool:
    """Detects whether AST definition node carries @aff_exempt decorator."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if (isinstance(target, ast.Name) and target.id == "aff_exempt") or (
            isinstance(target, ast.Attribute) and target.attr == "aff_exempt"
        ):
            return True
    return False


def _parse_module(
    py_file: Path,
    parsed_cache: Optional[Dict[Path, Tuple[Optional[str], Optional[ast.AST], Optional[SmellDefect]]]] = None,
) -> Tuple[Optional[str], Optional[ast.AST], Optional[SmellDefect]]:
    """Reads and parses a Python file into AST, capturing syntax/encoding/IO defects (DEFECT-01)."""
    if parsed_cache is not None and py_file in parsed_cache:
        return parsed_cache[py_file]

    line_no, desc, rem = 1, "", ""
    try:
        content = py_file.read_text(encoding="utf-8")
        res: Tuple[Optional[str], Optional[ast.AST], Optional[SmellDefect]] = (
            content, ast.parse(content, filename=str(py_file)), None
        )
    except SyntaxError as e:
        line_no = e.lineno or 1
        desc, rem = f"SyntaxError in Python source: {e.msg}", "Fix syntax error so module can be parsed and analyzed."
        res = (None, None, SmellDefect(str(py_file), line_no, "SYNTAX_ERROR", "CRITICAL", desc, rem))
    except UnicodeDecodeError as e:
        desc, rem = f"Encoding error: unable to decode UTF-8: {e}", "Ensure file is valid UTF-8 text."
        res = (None, None, SmellDefect(str(py_file), 1, "SYNTAX_ERROR", "CRITICAL", desc, rem))
    except OSError as e:
        desc, rem = f"I/O error reading file: {e}", "Ensure file permissions and disk state are readable."
        res = (None, None, SmellDefect(str(py_file), 1, "SYNTAX_ERROR", "CRITICAL", desc, rem))
    except Exception as e:
        desc, rem = f"Failed to parse Python module: {e}", "Fix module so it can be parsed via ast.parse."
        res = (None, None, SmellDefect(str(py_file), 1, "SYNTAX_ERROR", "CRITICAL", desc, rem))

    if parsed_cache is not None:
        if len(parsed_cache) >= 10000:
            parsed_cache.clear()
        parsed_cache[py_file] = res
    return res


def _iter_import_nodes(tree: ast.AST, skip_type_checking: bool = False) -> List[ast.AST]:
    """Fast iterative statement-suite traversal yielding Import/ImportFrom nodes without walking expressions."""
    imports: List[ast.AST] = []
    stack: List[ast.AST] = list(getattr(tree, "body", ()))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(node)
            continue
        if skip_type_checking and isinstance(node, ast.If):
            t = node.test
            if (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or (
                isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING"
            ):
                stack.extend(node.orelse or ())
                continue
        for attr in ("body", "orelse", "finalbody"):
            sub = getattr(node, attr, None)
            if isinstance(sub, list):
                stack.extend(sub)
        for grp_attr in ("handlers", "cases"):
            for item in getattr(node, grp_attr, None) or ():
                if getattr(item, "body", None):
                    stack.extend(item.body)
    return imports


def _has_cache_bounds(func_node: ast.AST, cache_val: ast.AST) -> bool:
    """Evaluates whether an enclosing function contains eviction/LRU bounds tied to cache_val (DEFECT-04)."""
    if isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for dec in func_node.decorator_list:
            tgt = dec.func if isinstance(dec, ast.Call) else dec
            dec_id = tgt.id if isinstance(tgt, ast.Name) else (tgt.attr if isinstance(tgt, ast.Attribute) else "")
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
            if isinstance(inner.func, ast.Attribute) and inner.func.attr in ("pop", "popitem", "clear", "evict"):
                if _matches_cache(inner.func.value):
                    return True

        if isinstance(inner, ast.Delete):
            for tgt in inner.targets:
                if isinstance(tgt, ast.Subscript) and _matches_cache(tgt.value):
                    return True

        if isinstance(inner, ast.Assign) and isinstance(inner.value, ast.Subscript):
            if isinstance(inner.value.slice, ast.Slice) and _matches_cache(inner.value.value):
                for tgt in inner.targets:
                    if _matches_cache(tgt) or (isinstance(tgt, ast.Subscript) and _matches_cache(tgt.value)):
                        return True

    return False


def audit_import_boundaries(
    root_dir: Path,
    rules: Optional[List[BoundaryRule]] = None,
    parsed_cache: Optional[Dict[Path, Tuple[Optional[str], Optional[ast.AST], Optional[SmellDefect]]]] = None,
    target_pkg: Optional[str] = None,
) -> List[BoundaryDefect]:
    """
    Audits source files under root_dir for illegal import boundaries.

    Inspects ast.Import and ast.ImportFrom against specified rules (or DEFAULT_BOUNDARY_RULES).
    Scopes filesystem walk to rule prefixes or target_pkg to maintain <0.25s latency.
    """
    active_rules = rules if rules is not None else DEFAULT_BOUNDARY_RULES
    if not active_rules:
        return []

    root_path = Path(root_dir).resolve()
    defects: List[BoundaryDefect] = []

    scan_dirs: List[Path] = []
    if target_pkg and (root_path / target_pkg).is_dir():
        scan_dirs = [root_path / target_pkg]
    else:
        concrete_roots: List[Path] = []
        has_wildcard_root = False
        for r in active_rules:
            pat = r.source_pattern.strip().replace("\\", "/")
            first_seg = pat.split("/", 1)[0]
            if not first_seg or any(ch in first_seg for ch in ("*", "?", "[")):
                has_wildcard_root = True
                break
            cand = root_path / first_seg
            if cand.is_dir():
                concrete_roots.append(cand)
        if has_wildcard_root:
            scan_dirs = [root_path]
        else:
            seen_roots: Set[Path] = set()
            for cr in concrete_roots:
                if cr not in seen_roots:
                    seen_roots.add(cr)
                    scan_dirs.append(cr)

    py_files_set: Set[Path] = set()
    for sdir in scan_dirs:
        py_files_set.update(_discover_python_files(sdir))
    py_files = sorted(py_files_set)

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

        for node in _iter_import_nodes(tree, skip_type_checking=False):
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
                            for alias in node.names:
                                imported_modules.append(f"{node.module}.{alias.name}")
                        else:
                            for alias in node.names:
                                imported_modules.append(alias.name)
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

        lines = content.splitlines()
        mod_parts = mod.split(".")
        base_parts = mod_parts[:-1] if p.name != "__init__.py" else mod_parts

        for node in _iter_import_nodes(tree, skip_type_checking=True):
            line_no = getattr(node, "lineno", 1)
            raw_line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
            if _is_exempt_line(raw_line):
                continue
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
    Audits Python modules and JS assets for structural code smells:
    1. SYNTAX_ERROR: Corrupted or unparseable Python modules (CRITICAL).
    2. FOREIGN_LANGUAGE_MONOLITH: Multiline strings (>100 lines) containing HTML/JS/CSS/SQL.
    3. GOD_COMPONENT: Modules/JS assets > 800 lines or Python modules > 25 top-level defs without @aff_exempt.
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
    ]
    sql_monolith_pattern = re.compile(
        r"CREATE\s+(?:TABLE|INDEX)|INSERT\s+INTO.*SELECT|ALTER\s+TABLE",
        re.I | re.DOTALL,
    )

    def _has_multiline_block(src: str) -> bool:
        for quote in ('"""', "'''"):
            if src.count(quote) >= 2:
                parts = src.split(quote)
                for chunk in parts[1::2]:
                    if len(chunk) >= 120 and chunk.count("\n") >= 39:
                        return True
        return False

    def _iter_def_nodes(root_tree: ast.AST) -> Tuple[List[ast.ClassDef], List[ast.AST]]:
        classes: List[ast.ClassDef] = []
        funcs: List[ast.AST] = []
        stack: List[ast.AST] = list(getattr(root_tree, "body", ()))
        while stack:
            n = stack.pop()
            if isinstance(n, ast.ClassDef):
                classes.append(n)
                stack.extend(n.body)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append(n)
                stack.extend(n.body)
            else:
                for attr in ("body", "orelse", "finalbody"):
                    sub = getattr(n, attr, None)
                    if isinstance(sub, list):
                        stack.extend(sub)
                for h in getattr(n, "handlers", None) or ():
                    if getattr(h, "body", None):
                        stack.extend(h.body)
        return classes, funcs

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
        if tree is None or content is None or _is_exempt_file(content):
            continue

        lines = content.splitlines()
        total_lines = len(lines)
        if total_lines > MAX_MODULE_LINES:
            smells.append(SmellDefect(
                file=rel_posix, line_number=1, smell_type="GOD_COMPONENT", severity="MAJOR",
                description=f"Module exceeds {MAX_MODULE_LINES} lines ({total_lines} lines). High structural complexity.",
                remediation="Decompose module into cohesive submodules or encapsulate into a dedicated subpackage.",
            ))

        top_level_defs = [
            n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not _is_exempt_node(n)
        ]
        if len(top_level_defs) > MAX_TOP_LEVEL_DEFS:
            smells.append(SmellDefect(
                file=rel_posix, line_number=1, smell_type="GOD_COMPONENT", severity="MAJOR",
                description=f"Module contains {len(top_level_defs)} top-level definitions (threshold: {MAX_TOP_LEVEL_DEFS}).",
                remediation="Refactor top-level procedures into cohesive domain classes or separate service modules.",
            ))

        # Track module-level mutable containers for UNBOUNDED_CACHE auditing
        module_mutables: Set[str] = set()
        for top_node in tree.body:
            val_node = top_node.value if isinstance(top_node, (ast.Assign, ast.AnnAssign)) else None
            if val_node is None:
                continue
            is_mut = isinstance(val_node, (ast.Dict, ast.List, ast.Set))
            if isinstance(val_node, ast.Call):
                fn_name = (
                    val_node.func.id
                    if isinstance(val_node.func, ast.Name)
                    else (val_node.func.attr if isinstance(val_node.func, ast.Attribute) else "")
                )
                if fn_name in ("dict", "list", "set", "OrderedDict", "defaultdict"):
                    is_mut = True
            if is_mut:
                tgts = top_node.targets if isinstance(top_node, ast.Assign) else [top_node.target]
                for tgt in tgts:
                    if isinstance(tgt, ast.Name):
                        module_mutables.add(tgt.id)

        def _extract_cache_target_name(expr: ast.AST) -> str:
            if isinstance(expr, ast.Attribute) and ("cache" in expr.attr.lower() or "memo" in expr.attr.lower()):
                return expr.attr
            if isinstance(expr, ast.Name):
                if "cache" in expr.id.lower() or "memo" in expr.id.lower() or expr.id in module_mutables:
                    return expr.id
            return ""

        class_nodes, func_nodes = _iter_def_nodes(tree)
        for cls_node in class_nodes:
            if _is_exempt_node(cls_node):
                continue
            class_methods = [
                m for m in cls_node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not _is_exempt_node(m)
            ]
            if len(class_methods) > MAX_TOP_LEVEL_DEFS:
                smells.append(SmellDefect(
                    file=rel_posix, line_number=getattr(cls_node, "lineno", 1),
                    smell_type="GOD_COMPONENT", severity="MAJOR",
                    description=f"Class '{cls_node.name}' defines {len(class_methods)} methods (threshold: {MAX_TOP_LEVEL_DEFS}).",
                    remediation="Decompose God class into focused collaborator classes or service modules.",
                ))

        # Only walk AST for multiline strings if file actually contains a >=40-line triple-quoted block
        if _has_multiline_block(content):
            for node in ast.walk(tree):
                str_payload: Optional[str] = None
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if len(node.value) >= 120 and node.value.count("\n") >= 39:
                        str_payload = node.value
                elif isinstance(node, ast.JoinedStr):
                    joined_parts = [
                        v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)
                    ]
                    if joined_parts:
                        cand_str = "".join(joined_parts)
                        if len(cand_str) >= 120 and cand_str.count("\n") >= 39:
                            str_payload = cand_str
                if str_payload is not None:
                    val_lines = str_payload.splitlines()
                    is_frontend = len(val_lines) > 100 and any(pat.search(str_payload) for pat in frontend_patterns)
                    is_sql = len(val_lines) >= 40 and bool(sql_monolith_pattern.search(str_payload))
                    if is_frontend or is_sql:
                        line_no = getattr(node, "lineno", 1)
                        raw_line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
                        if not _is_exempt_line(raw_line):
                            smells.append(SmellDefect(
                                file=rel_posix, line_number=line_no, smell_type="FOREIGN_LANGUAGE_MONOLITH", severity="MAJOR",
                                description=f"Multiline string constant ({len(val_lines)} lines) contains embedded HTML/JS/CSS/SQL.",
                                remediation="Decouple foreign language code into external static assets under assets/ and load via importlib.resources.",
                            ))

        for node in func_nodes:
            if _is_exempt_node(node):
                continue
            func_end = getattr(node, "end_lineno", node.lineno)
            func_src = "\n".join(lines[node.lineno - 1 : func_end]).lower()
            has_candidate_ref = (
                "cache" in func_src
                or "memo" in func_src
                or any(m.lower() in func_src for m in module_mutables)
            )
            if not has_candidate_ref:
                continue
            flagged_lines: Set[int] = set()
            for inner in ast.walk(node):
                mut_expr: Optional[ast.AST] = None
                mut_desc = ""
                if isinstance(inner, (ast.Assign, ast.AugAssign)):
                    for tgt in (inner.targets if isinstance(inner, ast.Assign) else [inner.target]):
                        if isinstance(tgt, ast.Subscript):
                            cname = _extract_cache_target_name(tgt.value)
                            if cname:
                                mut_expr, mut_desc = tgt.value, f"Assignment to cache '{cname}[...]'"
                                break
                elif isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                    if inner.func.attr in ("append", "add", "setdefault", "update"):
                        cname = _extract_cache_target_name(inner.func.value)
                        if cname:
                            mut_expr, mut_desc = inner.func.value, f"Unbounded mutation '{cname}.{inner.func.attr}(...)'"
                if mut_expr is not None and not _has_cache_bounds(node, mut_expr):
                    line_no = getattr(inner, "lineno", node.lineno)
                    raw_line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
                    if line_no not in flagged_lines and not _is_exempt_line(raw_line):
                        flagged_lines.add(line_no)
                        smells.append(SmellDefect(
                            file=rel_posix, line_number=line_no, smell_type="UNBOUNDED_CACHE", severity="MAJOR",
                            description=f"{mut_desc} inside '{node.name}' without capacity eviction or LRU bounds.",
                            remediation="Implement capacity guard with eviction (pop/popitem/clear/slice), functools.lru_cache, or bounded OrderedDict.",
                        ))

    for js_file in _discover_asset_files(pkg_dir):
        try:
            rel_posix = js_file.relative_to(root_path).as_posix()
            js_content = js_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _is_exempt_file(js_content):
            continue
        js_lines = len(js_content.splitlines())
        if js_lines > MAX_MODULE_LINES:
            smells.append(SmellDefect(
                file=rel_posix, line_number=1, smell_type="GOD_COMPONENT", severity="MAJOR",
                description=f"JS asset exceeds {MAX_MODULE_LINES} lines ({js_lines} lines). High frontend complexity.",
                remediation="Modularize frontend JS asset into focused ES submodules under assets/ <= 800 lines.",
            ))

    return smells


def audit_architectural_fitness(
    workspace_root: Optional[Path] = None,
    rules: Optional[List[BoundaryRule]] = None,
    target_pkg: str = "harness",
) -> ArchitecturalFitnessReport:
    """
    Orchestrates the complete Architectural Fitness Function (AFF) audit suite:
    - Boundary defect analysis, circular dependencies, structural smells, and benchmark scoring
    """
    start_t = time.perf_counter()
    root = (Path(workspace_root) if workspace_root else Path.cwd()).resolve()
    pkg_dir = root / target_pkg if (root / target_pkg).is_dir() else root
    py_count = len(_discover_python_files(pkg_dir))
    js_count = len(_discover_asset_files(pkg_dir))
    parsed_cache: Dict[Path, Tuple[Optional[str], Optional[ast.AST], Optional[SmellDefect]]] = {}

    boundary_defects = audit_import_boundaries(
        root_dir=root, rules=rules, parsed_cache=parsed_cache, target_pkg=target_pkg
    )
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

    all_defects = boundary_defects + cycle_defects + smell_defects
    if any(d.severity in ("CRITICAL", "MAJOR") for d in all_defects) or score < 80.0:
        status = "FAIL"
    elif all_defects or score < 100.0:
        status = "WARNING"
    else:
        status = "PASS"

    return ArchitecturalFitnessReport(
        status=status, score=score,
        boundary_defects=boundary_defects, cycle_defects=cycle_defects, smell_defects=smell_defects,
        benchmark_latency_s=elapsed, scanned_files_count=py_count, scanned_assets_count=js_count,
    )
