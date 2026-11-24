# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Mutation data models and AST/token mutation operators."""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field
import difflib
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

from harness.mutation.probe_safety import (
    ACTIVE_BACKUPS,
    MUTATABLE_EXTENSIONS,
    PRAGMA_PATTERN,
    TYPE_ANNOTATION_ONLY,
    MutationCandidate,
    _SAFETY_HANDLERS_INSTALLED,
    _SAFETY_LOCK,
    _install_safety_handlers,
    _restore_all_backups,
    _sig_handler,
    check_baseline_cached,
    clear_backup,
    extract_diff_mutation_candidates,
    has_no_mutant_pragma,
    is_arid_line,
    is_test_file,
    parse_diff_lines,
    register_backup,
    resolve_repo_target,
    run_targeted_test_cmd,
)

CANONICAL_OPERATORS: Tuple[str, ...] = (
    "condition_inversion",
    "logical_swap",
    "boundary_shift",
    "return_stub",
    "void_statement_delete",
    "literal_mutation",
)

__all__ = [
    "ACTIVE_BACKUPS",
    "CANONICAL_OPERATORS",
    "FunctionMutant",
    "MUTATABLE_EXTENSIONS",
    "MutationCandidate",
    "MutationConfig",
    "MutationResult",
    "PRAGMA_PATTERN",
    "PythonAstMutator",
    "SurvivingMutant",
    "TYPE_ANNOTATION_ONLY",
    "_SAFETY_HANDLERS_INSTALLED",
    "_SAFETY_LOCK",
    "_install_safety_handlers",
    "_restore_all_backups",
    "_sig_handler",
    "apply_operator",
    "check_baseline_cached",
    "clear_backup",
    "extract_diff_mutation_candidates",
    "flip_bool_op",
    "generate_function_mutants",
    "has_no_mutant_pragma",
    "invert_compare_op",
    "is_arid_line",
    "is_test_file",
    "mutate_python_source",
    "mutate_token_source",
    "parse_diff_lines",
    "register_backup",
    "replace_source_segment_utf8",
    "resolve_repo_target",
    "run_targeted_test_cmd",
    "swap_arith_op",
]


@dataclass
class SurvivingMutant:
    """Represents a mutant that survived execution (tests passed despite mutation)."""
    file_path: str
    function_name: str
    line_number: int
    operator: str
    diff_snippet: str
    test_target: str

    def to_actionable_report(self) -> str:
        """Formats an actionable diagnostic diff and cognitive guidance report."""
        loc = f"{self.file_path}:{self.line_number}"
        return (
            f"\n❌ MUTATION TEST FAILURE: Surviving mutant detected!\n"
            f"The test suite passed on mutated code, indicating missing test assertions.\n\n"
            f"──────────────────────────────────────────────────────────────────────\n"
            f"[Surviving Mutant]\n"
            f"  Location: {loc}\n"
            f"  Function: `{self.function_name}`\n"
            f"  Operator: {self.operator}\n"
            f"  Test Target: {self.test_target}\n"
            f"──────────────────────────────────────────────────────────────────────\n"
            f"Unified Diff:\n"
            f"{self.diff_snippet}\n\n"
            f"Cognitive Guidance:\n"
            f"  • Your tests passed even when {self.operator} was applied to {loc}.\n"
            f"  • Remediation: Add test assertions exercising this branch or boundary.\n"
            f"  • Equivalent Mutant? If semantically equivalent, suppress with:\n"
            f"    # agyis: no-mutant <reason>\n"
            f"──────────────────────────────────────────────────────────────────────\n"
        )


@dataclass
class MutationResult:
    """Result of micro-mutation testing across the working tree or target diff."""
    total_mutants: int
    killed_mutants: int
    survived_mutants: List[SurvivingMutant] = field(default_factory=list)
    exit_code: int = 0
    suppressed_by_pragma: int = 0
    error_message: Optional[str] = None


@dataclass
class MutationConfig:
    """Configuration options for micro-mutation execution."""
    max_mutants_per_function: int = 6
    max_mutants_total: int = 20
    operators: Optional[List[str]] = None
    timeout_sec: float = 3.0
    fail_fast: bool = False
    repo_root: Optional[Path] = None
    verbose: bool = False


@dataclass
class FunctionMutant:
    """A planned mutant for a function or code block."""
    mutated_code: str
    operator: str
    line_number: int
    diff_snippet: str
    function_name: str = ""


def _mask_strings_and_comments(line: str) -> str:
    """Returns a same-length string with string literals and comments replaced by NUL bytes."""
    chars = list(line)
    n = len(chars)
    i = 0
    in_quote: Optional[str] = None
    in_block_comment = False

    while i < n:
        ch = chars[i]
        if in_block_comment:
            chars[i] = "\x00"
            if ch == "*" and i + 1 < n and chars[i + 1] == "/":
                chars[i + 1] = "\x00"
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_quote is not None:
            chars[i] = "\x00"
            if ch == "\\" and i + 1 < n:
                chars[i + 1] = "\x00"
                i += 2
                continue
            if ch == in_quote:
                in_quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            in_quote = ch
            chars[i] = "\x00"
            i += 1
            continue
        if ch == "#" or (ch == "/" and i + 1 < n and chars[i + 1] == "/"):
            for j in range(i, n):
                chars[j] = "\x00"
            break
        if ch == "/" and i + 1 < n and chars[i + 1] == "*":
            chars[i] = "\x00"
            chars[i + 1] = "\x00"
            in_block_comment = True
            i += 2
            continue
        i += 1
    return "".join(chars)


def _replace_masked(src: str, masked: str, token: str, repl: str, *, regex: bool = False) -> Optional[str]:
    if regex:
        m = re.search(token, masked)
        return (src[: m.start()] + repl + src[m.end():]) if m else None
    idx = masked.find(token)
    return (src[:idx] + repl + src[idx + len(token):]) if idx != -1 else None


def apply_operator(src: str, operator: str) -> str:
    """Applies a mutation operator while preserving indentation and ignoring strings/comments."""
    s = src
    masked = _mask_strings_and_comments(s)
    indent = s[: len(s) - len(s.lstrip(" \t"))]

    if operator == "condition_inversion":
        for tok, rep in (
            (" is not ", " is "), (" is ", " is not "), (" not in ", " in "), (" in ", " not in "),
            (" != ", " == "), (" == ", " != "), (" >= ", " < "), (" <= ", " > "),
            (" > ", " <= "), (" < ", " >= "), ("if not ", "if "),
        ):
            res = _replace_masked(s, masked, tok, rep)
            if res is not None:
                return res
        res = _replace_masked(s, masked, r"\bnot\s+", "", regex=True)
        if res is not None:
            return res

    elif operator == "logical_swap":
        for tok, rep in ((" and ", " or "), (" or ", " and "), ("&&", "||"), ("||", "&&")):
            res = _replace_masked(s, masked, tok, rep)
            if res is not None:
                return res

    elif operator == "boundary_shift":
        for tok, rep in (
            (" += ", " -= "), (" -= ", " += "), (" *= ", " /= "), (" /= ", " *= "),
            (" + 1", " - 1"), (" - 1", " + 1"), (" > 0", " >= 0"), (" < 0", " <= 0"),
            (" >= 0", " > 0"), (" <= 0", " < 0"), (" > ", " >= "), (" < ", " <= "),
            (" >= ", " > "), (" <= ", " < "), (" + ", " - "), (" - ", " + "),
        ):
            res = _replace_masked(s, masked, tok, rep)
            if res is not None:
                return res

    elif operator == "return_stub":
        m = re.match(r"^(\s*return)\s+(.+)$", s)
        if m:
            val = m.group(2).strip()
            if val == "True":
                return m.group(1) + " False"
            if val == "False":
                return m.group(1) + " True"
            if val == "None":
                return m.group(1) + " False"
            return m.group(1) + " None"
        if masked.strip() == "return":
            return f"{indent}return False"

    elif operator == "void_statement_delete":
        return f"{indent}pass"

    elif operator == "literal_mutation":
        for pat, rep in ((r"\bTrue\b", "False"), (r"\bFalse\b", "True"), (r"\btrue\b", "false"), (r"\bfalse\b", "true")):
            res = _replace_masked(s, masked, pat, rep, regex=True)
            if res is not None:
                return res

    return s


def replace_source_segment_utf8(
    source: str,
    lineno: int,
    col_offset: int,
    end_lineno: int,
    end_col_offset: int,
    replacement: str,
) -> str:
    """Replaces an AST segment using UTF-8 byte offsets without corrupting non-ASCII lines."""
    lines = source.splitlines(keepends=True)
    if lineno < 1 or lineno > len(lines) or end_lineno < 1 or end_lineno > len(lines) or lineno > end_lineno:
        return source
    if lineno == end_lineno:
        line_bytes = lines[lineno - 1].encode("utf-8")
        prefix = line_bytes[:col_offset].decode("utf-8", errors="replace")
        suffix = line_bytes[end_col_offset:].decode("utf-8", errors="replace")
    else:
        prefix = lines[lineno - 1].encode("utf-8")[:col_offset].decode("utf-8", errors="replace")
        suffix = lines[end_lineno - 1].encode("utf-8")[end_col_offset:].decode("utf-8", errors="replace")
    new_lines = list(lines[: lineno - 1]) + [prefix + replacement + suffix] + list(lines[end_lineno:])
    return "".join(new_lines)


def invert_compare_op(op: ast.cmpop) -> Optional[ast.cmpop]:
    """Returns the canonical negated AST comparison operator, or None if unsupported."""
    pairs = (
        (ast.Eq, ast.NotEq), (ast.NotEq, ast.Eq),
        (ast.Lt, ast.GtE), (ast.GtE, ast.Lt),
        (ast.Gt, ast.LtE), (ast.LtE, ast.Gt),
        (ast.Is, ast.IsNot), (ast.IsNot, ast.Is),
        (ast.In, ast.NotIn), (ast.NotIn, ast.In),
    )
    for src_t, dst_t in pairs:
        if isinstance(op, src_t):
            return dst_t()
    return None


def swap_arith_op(op: ast.operator, include_mult_div: bool = True) -> Optional[ast.operator]:
    """Returns the canonical swapped AST binary/augassign arithmetic operator."""
    if isinstance(op, ast.Add):
        return ast.Sub()
    if isinstance(op, ast.Sub):
        return ast.Add()
    if include_mult_div:
        if isinstance(op, ast.Mult):
            return ast.Div()
        if isinstance(op, (ast.Div, ast.FloorDiv)):
            return ast.Mult()
    return None


def flip_bool_op(op: ast.boolop) -> Optional[ast.boolop]:
    """Returns the canonical inverted AST boolean operator (and <-> or)."""
    if isinstance(op, ast.And):
        return ast.Or()
    if isinstance(op, ast.Or):
        return ast.And()
    return None


class PythonAstMutator(ast.NodeTransformer):
    """AST NodeTransformer that surgically mutates target nodes on target_line."""

    def __init__(self, operator: str, target_line: Optional[int] = None):
        self.operator = operator
        self.target_line = target_line
        self.mutated = False
        self.span: Optional[Tuple[int, int, int, int]] = None
        self.replacement_text: Optional[str] = None

    def _matches_line(self, node: ast.AST) -> bool:
        if self.target_line is None:
            return True
        lineno = getattr(node, "lineno", None)
        if lineno is None:
            return False
        end_lineno = getattr(node, "end_lineno", None) or lineno
        return lineno <= self.target_line <= end_lineno

    def _record_mutation(self, node: ast.AST, replacement_text: str) -> None:
        self.mutated = True
        self.span = (
            node.lineno,
            node.col_offset,
            node.end_lineno or node.lineno,
            node.end_col_offset or (node.col_offset + 5),
        )
        self.replacement_text = replacement_text

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        if not self.mutated and self._matches_line(node):
            if self.operator == "condition_inversion":
                if len(node.ops) == 1:
                    new_op = invert_compare_op(node.ops[0])
                    if new_op is not None:
                        node.ops = [new_op]
                        self._record_mutation(node, ast.unparse(node))
                        return node
                elif len(node.ops) > 1:
                    negated = ast.UnaryOp(op=ast.Not(), operand=copy.deepcopy(node))
                    self._record_mutation(node, f"not ({ast.unparse(node)})")
                    return negated
            elif self.operator == "boundary_shift":
                new_ops: List[ast.cmpop] = []
                changed = False
                for o in node.ops:
                    if isinstance(o, ast.Gt):
                        new_ops.append(ast.GtE())
                        changed = True
                    elif isinstance(o, ast.GtE):
                        new_ops.append(ast.Gt())
                        changed = True
                    elif isinstance(o, ast.Lt):
                        new_ops.append(ast.LtE())
                        changed = True
                    elif isinstance(o, ast.LtE):
                        new_ops.append(ast.Lt())
                        changed = True
                    else:
                        new_ops.append(o)
                if changed:
                    node.ops = new_ops
                    self._record_mutation(node, ast.unparse(node))
                    return node
        return self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "condition_inversion":
            if isinstance(node.op, ast.Not):
                self._record_mutation(node, ast.unparse(node.operand))
                return node.operand
        return self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "logical_swap":
            new_op = flip_bool_op(node.op)
            if new_op is not None:
                node.op = new_op
                self._record_mutation(node, ast.unparse(node))
                return node
        return self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "boundary_shift":
            new_op = swap_arith_op(node.op, include_mult_div=False)
            if new_op is not None:
                node.op = new_op
                self._record_mutation(node, ast.unparse(node))
                return node
        return self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "boundary_shift":
            new_op = swap_arith_op(node.op, include_mult_div=True)
            if new_op is not None:
                node.op = new_op
                self._record_mutation(node, ast.unparse(node))
                return node
        return self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "return_stub":
            if isinstance(node.value, ast.Constant) and type(node.value.value) is bool:
                node.value.value = not node.value.value
            elif node.value is None or (isinstance(node.value, ast.Constant) and node.value.value is None):
                node.value = ast.Constant(value=False)
            else:
                node.value = ast.Constant(value=None)
            self._record_mutation(node, ast.unparse(node))
            return node
        return self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "void_statement_delete":
            if isinstance(node.value, ast.Call) or (
                isinstance(node.value, ast.Await) and isinstance(node.value.value, ast.Call)
            ):
                self._record_mutation(node, "pass")
                return ast.Pass()
        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if not self.mutated and self._matches_line(node) and self.operator == "literal_mutation":
            if type(node.value) is bool:
                node.value = not node.value
                self._record_mutation(node, ast.unparse(node))
                return node
        return node


def mutate_python_source(src: str, target_line: int, operator: str) -> Tuple[str, str]:
    """Surgically mutates Python source code at 1-indexed target_line with operator."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src, ""

    mutator = PythonAstMutator(operator=operator, target_line=target_line)
    mutator.visit(tree)

    lines = src.splitlines(keepends=True)
    if not mutator.mutated or not mutator.span or mutator.replacement_text is None:
        return src, ""

    start_l, start_c, end_l, end_c = mutator.span
    mutated_src = replace_source_segment_utf8(src, start_l, start_c, end_l, end_c, mutator.replacement_text)
    if mutated_src == src:
        return src, ""
    try:
        ast.parse(mutated_src)
    except SyntaxError:
        return src, ""

    diff = "".join(difflib.unified_diff(lines, mutated_src.splitlines(keepends=True), lineterm=""))
    return mutated_src, diff


def mutate_token_source(code: str, lang: str = "ts") -> Tuple[str, str]:
    """Polyglot token-level mutation fallback for TypeScript/JavaScript/Rust (string/comment-safe)."""
    masked = _mask_strings_and_comments(code)
    replacements = (
        ("===", "!==", "condition_inversion"), ("!==", "===", "condition_inversion"),
        ("==", "!=", "condition_inversion"), ("!=", "==", "condition_inversion"),
        ("&&", "||", "logical_swap"), ("||", "&&", "logical_swap"),
        (" + 1", " - 1", "boundary_shift"), (" - 1", " + 1", "boundary_shift"),
        (" >= ", " < ", "condition_inversion"), (" <= ", " > ", "condition_inversion"),
        (" > 0", " >= 0", "boundary_shift"), (" < 0", " <= 0", "boundary_shift"),
        (" > ", " <= ", "condition_inversion"), (" < ", " >= ", "condition_inversion"),
    )

    for token, repl, op in replacements:
        mutated = _replace_masked(code, masked, token, repl)
        if mutated is not None:
            return mutated, op

    for pat, repl in ((r"\btrue\b", "false"), (r"\bfalse\b", "true")):
        mutated = _replace_masked(code, masked, pat, repl, regex=True)
        if mutated is not None:
            return mutated, "literal_mutation"

    control_keywords = {"if", "while", "for", "switch", "catch", "function", "return"}
    if "=" not in masked and "return" not in masked:
        tokens_in_line = set(re.findall(r"\b[a-zA-Z_]\w*\b", masked))
        if not (tokens_in_line & control_keywords):
            m = re.search(r"\b([a-zA-Z_]\w*\s*\([^;)]*\);?)", masked)
            if m:
                orig_call = code[m.start(): m.end()]
                mutated = code[: m.start()] + f"/* {orig_call} */" + code[m.end():]
                if mutated != code and mutated.count("(") == mutated.count(")"):
                    return mutated, "void_statement_delete"

    return code, ""


def generate_function_mutants(func_code: str, max_mutants: int = 6) -> List[FunctionMutant]:
    """Generates up to max_mutants diverse mutants for a Python function or block."""
    tree = ast.parse(func_code)
    func_name = ""
    by_op: Dict[str, List[Tuple[int, str]]] = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not func_name:
            func_name = node.name
        if not hasattr(node, "lineno"):
            continue
        line_num = node.lineno
        if isinstance(node, ast.Compare):
            by_op.setdefault("condition_inversion", []).append((line_num, "condition_inversion"))
            for op_node in node.ops:
                if isinstance(op_node, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                    by_op.setdefault("boundary_shift", []).append((line_num, "boundary_shift"))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            by_op.setdefault("condition_inversion", []).append((line_num, "condition_inversion"))
        elif isinstance(node, ast.BoolOp):
            by_op.setdefault("logical_swap", []).append((line_num, "logical_swap"))
        elif isinstance(node, (ast.BinOp, ast.AugAssign)) and isinstance(node.op, (ast.Add, ast.Sub)):
            by_op.setdefault("boundary_shift", []).append((line_num, "boundary_shift"))
        elif isinstance(node, ast.Return):
            by_op.setdefault("return_stub", []).append((line_num, "return_stub"))
        elif isinstance(node, ast.Expr) and (
            isinstance(node.value, ast.Call)
            or (isinstance(node.value, ast.Await) and isinstance(node.value.value, ast.Call))
        ):
            by_op.setdefault("void_statement_delete", []).append((line_num, "void_statement_delete"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            by_op.setdefault("literal_mutation", []).append((line_num, "literal_mutation"))

    selected: List[Tuple[int, str]] = []
    ops_list = list(by_op.keys())
    idx = 0
    max_loops = 100
    while len(selected) < max_mutants and any(by_op.values()) and max_loops > 0:
        max_loops -= 1
        op = ops_list[idx % len(ops_list)]
        idx += 1
        if by_op.get(op):
            cand = by_op[op].pop(0)
            if cand not in selected:
                selected.append(cand)

    mutants: List[FunctionMutant] = []
    for line_no, op in selected:
        mut_src, diff = mutate_python_source(func_code, line_no, op)
        if mut_src and mut_src != func_code:
            mutants.append(FunctionMutant(
                mutated_code=mut_src,
                operator=op,
                line_number=line_no,
                diff_snippet=diff,
                function_name=func_name,
            ))

    return mutants
