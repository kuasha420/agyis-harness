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

import ast
from collections import defaultdict
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from harness.utils.state import atomic_write_json, get_state_dir

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
    "DEFAULT_BOUNDARY_RULES", "IGNORED_DIRS", "MAX_MODULE_LINES", "MAX_TOP_LEVEL_DEFS",
    "SmellDefect", "aff_exempt", "audit_architectural_fitness", "audit_dependency_cycles",
    "audit_import_boundaries", "audit_structural_smells",
]

MAX_AFF_DISK_CACHE = 1024
_AFF_CACHE_VERSION = 1
_FRONTEND_PATTERNS = (
    re.compile(r"<!DOCTYPE|<html|<body|<div|<script|</span|</table", re.I),
    re.compile(r"addEventListener|function\s*\(|const\s+\w+\s*=|document\.getElementById", re.I),
    re.compile(r"\{\s*display:\s*|@media\s+|font-family:|margin:\s*", re.I),
)
_SQL_MONOLITH_PATTERN = re.compile(r"CREATE\s+(?:TABLE|INDEX)|INSERT\s+INTO.*SELECT|ALTER\s+TABLE", re.I | re.DOTALL)
_EXEMPT_FILE_MARKERS = ("# aff: exempt", "# aff_exempt", "__aff_exempt__ = True", "// aff: exempt", "/* aff: exempt")


def _discover_workspace_files(base_dir: Path) -> Tuple[List[Path], List[Path]]:
    """Single os.walk discovering both .py and .js files while skipping ignored dirs."""
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
    return py_files, js_files


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


def _is_exempt_file(content: str) -> bool:
    """Detects file-level AFF exemption pragmas."""
    return any(any(m in line for m in _EXEMPT_FILE_MARKERS) for line in content[:2000].splitlines()[:30])


def _is_exempt_line(line: str) -> bool:
    """Detects explicit line-level AFF exemption pragmas (does NOT honor generic # noqa)."""
    return "# aff: exempt" in line or "# aff_exempt" in line


def _is_exempt_node(node: ast.AST) -> bool:
    """Detects whether AST definition node carries @aff_exempt decorator."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    for dec in node.decorator_list:
        tgt = dec.func if isinstance(dec, ast.Call) else dec
        if (isinstance(tgt, ast.Name) and tgt.id == "aff_exempt") or (
            isinstance(tgt, ast.Attribute) and tgt.attr == "aff_exempt"
        ):
            return True
    return False


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
        return bool(
            (target_attr and isinstance(node, ast.Attribute) and node.attr == target_attr)
            or (target_id and isinstance(node, ast.Name) and node.id == target_id)
        )

    for inner in ast.walk(func_node):
        if isinstance(inner, ast.Call):
            if isinstance(inner.func, ast.Attribute) and inner.func.attr in ("pop", "popitem", "clear", "evict"):
                if _matches_cache(inner.func.value):
                    return True
        elif isinstance(inner, ast.Delete):
            if any(isinstance(t, ast.Subscript) and _matches_cache(t.value) for t in inner.targets):
                return True
        elif isinstance(inner, ast.Assign) and isinstance(inner.value, ast.Subscript):
            if isinstance(inner.value.slice, ast.Slice) and _matches_cache(inner.value.value):
                if any(_matches_cache(t) or (isinstance(t, ast.Subscript) and _matches_cache(t.value)) for t in inner.targets):
                    return True
    return False


def _has_multiline_block(src: str) -> bool:
    for quote in ('"""', "'''"):
        if src.count(quote) >= 2:
            for chunk in src.split(quote)[1::2]:
                if len(chunk) >= 120 and chunk.count("\n") >= 39:
                    return True
    return False


def _extract_facts_from_file(py_file: Path) -> Tuple[str, Dict[str, Any]]:
    """Reads, hashes, parses, and extracts all boundary/cycle/smell facts in a single pass."""
    digest = ""
    try:
        raw_bytes = py_file.read_bytes()
        digest = hashlib.blake2b(raw_bytes, digest_size=16).hexdigest()
        content = raw_bytes.decode("utf-8")
        tree = compile(content, str(py_file), "exec", ast.PyCF_ONLY_AST, dont_inherit=True)
    except SyntaxError as e:
        return digest, {"parse_defect": [e.lineno or 1, f"SyntaxError in Python source: {e.msg}", "Fix syntax error so module can be parsed and analyzed."]}
    except UnicodeDecodeError as e:
        return digest, {"parse_defect": [1, f"Encoding error: unable to decode UTF-8: {e}", "Ensure file is valid UTF-8 text."]}
    except OSError as e:
        return digest, {"parse_defect": [1, f"I/O error reading file: {e}", "Ensure file permissions and disk state are readable."]}
    except Exception as e:
        return digest, {"parse_defect": [1, f"Failed to parse Python module: {e}", "Fix module so it can be parsed via ast.parse."]}

    if _is_exempt_file(content):
        return digest, {"exempt": True}

    lines = content.splitlines()
    total_lines = len(lines)
    top_level_defs = 0
    module_mutables: Set[str] = set()

    for top_node in tree.body:
        if isinstance(top_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not _is_exempt_node(top_node):
            top_level_defs += 1
        elif isinstance(top_node, (ast.Assign, ast.AnnAssign)) and top_node.value is not None:
            val_node = top_node.value
            is_mut = isinstance(val_node, (ast.Dict, ast.List, ast.Set))
            if isinstance(val_node, ast.Call):
                fn_name = val_node.func.id if isinstance(val_node.func, ast.Name) else (
                    val_node.func.attr if isinstance(val_node.func, ast.Attribute) else ""
                )
                is_mut = fn_name in ("dict", "list", "set", "OrderedDict", "defaultdict")
            if is_mut:
                tgts = top_node.targets if isinstance(top_node, ast.Assign) else [top_node.target]
                for tgt in tgts:
                    if isinstance(tgt, ast.Name):
                        module_mutables.add(tgt.id)

    imports: List[List[Any]] = []
    class_methods: List[List[Any]] = []
    func_nodes: List[ast.AST] = []
    stack: List[Tuple[ast.AST, bool]] = [(n, False) for n in tree.body]

    while stack:
        node, in_tc = stack.pop()
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            line_no = getattr(node, "lineno", 1)
            raw_line = lines[line_no - 1] if 0 < line_no <= total_lines else ""
            if not _is_exempt_line(raw_line):
                names = [a.name for a in node.names]
                if isinstance(node, ast.Import):
                    imports.append([in_tc, line_no, 0, 0, "", names])
                else:
                    imports.append([in_tc, line_no, 1, node.level or 0, node.module or "", names])
            continue
        if isinstance(node, ast.If):
            t = node.test
            is_tc = (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or (
                isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING"
            )
            stack.extend((sub, in_tc) for sub in (node.orelse or ()))
            stack.extend((sub, in_tc or is_tc) for sub in (node.body or ()))
            continue
        if isinstance(node, ast.ClassDef):
            if not _is_exempt_node(node):
                mcnt = sum(1 for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not _is_exempt_node(m))
                class_methods.append([node.name, getattr(node, "lineno", 1), mcnt])
            stack.extend((sub, in_tc) for sub in node.body)
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not _is_exempt_node(node):
                func_nodes.append(node)
            stack.extend((sub, in_tc) for sub in node.body)
            continue
        for attr in ("body", "orelse", "finalbody"):
            sub_list = getattr(node, attr, None)
            if isinstance(sub_list, list):
                stack.extend((sub, in_tc) for sub in sub_list)
        for grp_attr in ("handlers", "cases"):
            for item in getattr(node, grp_attr, None) or ():
                if getattr(item, "body", None):
                    stack.extend((sub, in_tc) for sub in item.body)

    extra_smells: List[List[Any]] = []
    if _has_multiline_block(content):
        for node in ast.walk(tree):
            str_payload: Optional[str] = None
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if len(node.value) >= 120 and node.value.count("\n") >= 39:
                    str_payload = node.value
            elif isinstance(node, ast.JoinedStr):
                parts = [v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
                cand = "".join(parts) if parts else ""
                if len(cand) >= 120 and cand.count("\n") >= 39:
                    str_payload = cand
            if str_payload is not None:
                val_lines = str_payload.splitlines()
                is_fe = len(val_lines) > 100 and any(p.search(str_payload) for p in _FRONTEND_PATTERNS)
                is_sql = len(val_lines) >= 40 and bool(_SQL_MONOLITH_PATTERN.search(str_payload))
                if is_fe or is_sql:
                    line_no = getattr(node, "lineno", 1)
                    raw_line = lines[line_no - 1] if 0 < line_no <= total_lines else ""
                    if not _is_exempt_line(raw_line):
                        extra_smells.append([
                            line_no, "FOREIGN_LANGUAGE_MONOLITH", "MAJOR",
                            f"Multiline string constant ({len(val_lines)} lines) contains embedded HTML/JS/CSS/SQL.",
                            "Decouple foreign language code into external static assets under assets/ and load via importlib.resources.",
                        ])

    mutables_lower = tuple(m.lower() for m in module_mutables)

    def _extract_cache_target_name(expr: ast.AST) -> str:
        if isinstance(expr, ast.Attribute) and ("cache" in expr.attr.lower() or "memo" in expr.attr.lower()):
            return expr.attr
        if isinstance(expr, ast.Name) and ("cache" in expr.id.lower() or "memo" in expr.id.lower() or expr.id in module_mutables):
            return expr.id
        return ""

    for fnode in func_nodes:
        f_end = getattr(fnode, "end_lineno", fnode.lineno)
        func_src = "\n".join(lines[fnode.lineno - 1 : f_end]).lower()
        if not ("cache" in func_src or "memo" in func_src or any(m in func_src for m in mutables_lower)):
            continue
        flagged_lines: Set[int] = set()
        for inner in ast.walk(fnode):
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
            if mut_expr is not None and not _has_cache_bounds(fnode, mut_expr):
                line_no = getattr(inner, "lineno", fnode.lineno)
                raw_line = lines[line_no - 1] if 0 < line_no <= total_lines else ""
                if line_no not in flagged_lines and not _is_exempt_line(raw_line):
                    flagged_lines.add(line_no)
                    extra_smells.append([
                        line_no, "UNBOUNDED_CACHE", "MAJOR",
                        f"{mut_desc} inside '{fnode.name}' without capacity eviction or LRU bounds.",
                        "Implement capacity guard with eviction (pop/popitem/clear/slice), functools.lru_cache, or bounded OrderedDict.",
                    ])

    return digest, {
        "total_lines": total_lines, "top_level_defs": top_level_defs,
        "class_methods": class_methods, "imports": imports, "smells": extra_smells,
    }


def _extract_uncached_parallel(py_files: List[Path]) -> Dict[Path, Tuple[str, Dict[str, Any]]]:
    """Parses >=48 uncached Python files across forked POSIX workers via pipes when single-threaded."""
    results: Dict[Path, Tuple[str, Dict[str, Any]]] = {}
    if len(py_files) < 48 or os.name != "posix" or not hasattr(os, "fork") or threading.active_count() != 1:
        return {p: _extract_facts_from_file(p) for p in py_files}

    n_workers = min(4, os.cpu_count() or 2)
    chunks = [py_files[i::n_workers] for i in range(n_workers)]
    readers: Dict[int, Tuple[List[Path], bytearray]] = {}
    pids: List[int] = []
    sel: Optional[selectors.DefaultSelector] = None
    try:
        for chunk in chunks:
            if not chunk:
                continue
            r_fd, w_fd = os.pipe()
            pid = os.fork()
            if pid == 0:
                os.close(r_fd)
                try:
                    payload = json.dumps([_extract_facts_from_file(p) for p in chunk], separators=(",", ":")).encode("utf-8")
                    view = memoryview(payload)
                    written = 0
                    while written < len(payload):
                        written += os.write(w_fd, view[written:])
                    os.close(w_fd)
                    os._exit(0)
                except BaseException:
                    os._exit(1)
            else:
                os.close(w_fd)
                pids.append(pid)
                readers[r_fd] = (chunk, bytearray())

        sel = selectors.DefaultSelector()
        for r_fd in readers:
            sel.register(r_fd, selectors.EVENT_READ)
        while sel.get_map():
            for key, _ in sel.select():
                data = os.read(key.fd, 65536)
                if data:
                    readers[key.fd][1].extend(data)
                else:
                    sel.unregister(key.fd)
                    os.close(key.fd)

        if all(os.WIFEXITED(st) and os.WEXITSTATUS(st) == 0 for _, st in (os.waitpid(p, 0) for p in pids)):
            for chunk, buf in readers.values():
                for p, item in zip(chunk, json.loads(buf.decode("utf-8"))):
                    results[p] = (item[0], item[1])
            return results
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError):
        for r_fd in list(readers):
            try:
                os.close(r_fd)
            except OSError:
                pass
        for pid in pids:
            try:
                os.waitpid(pid, 0)
            except OSError:
                pass
    finally:
        if sel is not None:
            try:
                sel.close()
            except OSError:
                pass
    return {p: _extract_facts_from_file(p) for p in py_files}


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
                        if len(parsed_cache) >= 10000:
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
                if len(parsed_cache) >= 10000:
                    parsed_cache.clear()
                parsed_cache[p] = facts
            if dg and len(py_files) >= 16:
                if dg not in disk_cache and len(disk_cache) >= MAX_AFF_DISK_CACHE:
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
