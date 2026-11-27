# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Single-Pass Python AST & JS Asset Smell Extraction Helpers for AFF (Task 1.2A.4).

Extracted from `harness.runtime.aff` to satisfy module line/def budgets while
providing parallel AST fact extraction and bounded JS cache auditing.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

_FRONTEND_PATTERNS = (
    re.compile(r"<!DOCTYPE|<html|<body|<div|<script|</span|</table", re.I),
    re.compile(r"addEventListener|function\s*\(|const\s+\w+\s*=|document\.getElementById", re.I),
    re.compile(r"\{\s*display:\s*|@media\s+|font-family:|margin:\s*", re.I),
)
_SQL_MONOLITH_PATTERN = re.compile(r"CREATE\s+(?:TABLE|INDEX)|INSERT\s+INTO.*SELECT|ALTER\s+TABLE", re.I | re.DOTALL)
_EXEMPT_FILE_MARKERS = ("# aff: exempt", "# aff_exempt", "__aff_exempt__ = True", "// aff: exempt", "/* aff: exempt")

_JS_NAMED_CACHE_DECL_RE = re.compile(
    r"(?:const|let|var)\s+(\w*(?:cache|memo)\w*)\s*=\s*(?:new\s+(?:Map|Set)\s*\(|\{\s*\}|\[\s*\])",
    re.I,
)
_JS_TOP_COLLECTION_DECL_RE = re.compile(
    r"^(?:const|let|var)\s+(\w+)\s*=\s*new\s+(?:Map|Set)\s*\(",
    re.MULTILINE,
)


def _is_exempt_file(content: str) -> bool:
    """Detects file-level AFF exemption pragmas."""
    return any(any(m in line for m in _EXEMPT_FILE_MARKERS) for line in content[:2000].splitlines()[:30])


def _is_exempt_line(line: str) -> bool:
    """Detects explicit line-level AFF exemption pragmas (does NOT honor generic # noqa)."""
    return "# aff: exempt" in line or "# aff_exempt" in line or "// aff: exempt" in line


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


def _extract_js_cache_smells(rel_posix: str, js_content: str) -> List[List[Any]]:
    """Detect unbounded in-memory Map/Set/object/array caches in JavaScript assets."""
    smells: List[List[Any]] = []
    if _is_exempt_file(js_content):
        return smells

    lines = js_content.splitlines()
    candidates: List[Tuple[str, int]] = []
    seen_names: Set[str] = set()

    for pattern in (_JS_NAMED_CACHE_DECL_RE, _JS_TOP_COLLECTION_DECL_RE):
        for match in pattern.finditer(js_content):
            name = match.group(1)
            if name in seen_names:
                continue
            line_no = js_content.count("\n", 0, match.start()) + 1
            raw_line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
            if _is_exempt_line(raw_line):
                continue
            seen_names.add(name)
            candidates.append((name, line_no))

    for var_name, decl_line in candidates:
        esc = re.escape(var_name)
        mut_re = re.compile(rf"\b{esc}\s*(?:\.(?:set|add|push)\s*\(|\[[^\]]+\]\s*=)")
        mut_match = mut_re.search(js_content)
        if not mut_match:
            continue
        mut_line_no = js_content.count("\n", 0, mut_match.start()) + 1
        mut_line = lines[mut_line_no - 1] if 0 < mut_line_no <= len(lines) else ""
        if _is_exempt_line(mut_line):
            continue
        bound_re = re.compile(
            rf"(?:\b{esc}\.(?:delete|clear|shift|pop|splice|slice)\s*\("
            rf"|\b{esc}\.(?:size|length)\s*[><=]"
            rf"|MAX_\w*(?:CACHE|ENTRIES|ITEMS|SIZE|LIMIT)?)",
        )
        if not bound_re.search(js_content):
            smells.append([
                decl_line,
                "UNBOUNDED_CACHE",
                "MAJOR",
                f"JS cache/collection '{var_name}' mutated in '{rel_posix}' without capacity eviction or size bounds.",
                "Enforce explicit capacity bounds (.delete/.clear/.shift/.slice or size >= MAX_ limit eviction).",
            ])
    return smells


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
