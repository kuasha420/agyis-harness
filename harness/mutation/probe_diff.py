# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Route A diff-targeted mutant collection and micro-mutation probe runner."""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field
import difflib
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from harness.discovery import inject_non_interactive_guards, resolve_affected_tests
from harness.mutation.probe_operators import (
    ACTIVE_BACKUPS,
    _install_safety_handlers,
    check_baseline_cached,
    clear_backup,
    flip_bool_op,
    has_no_mutant_pragma,
    invert_compare_op,
    is_arid_line,
    is_test_file,
    parse_diff_lines,
    register_backup,
    replace_source_segment_utf8,
    resolve_repo_target,
    run_targeted_test_cmd,
    swap_arith_op,
)

_RUNNER_ERROR_EXIT_CODES = frozenset({126, 127})


def _mp_attr(name: str, default: Any) -> Any:
    """Resolve patched attributes on the micro_probe facade without import cycles."""
    mod = sys.modules.get("harness.mutation.micro_probe")
    return getattr(mod, name, default) if mod is not None else default


@dataclass
class Mutant:
    mutant_id: str
    file_path: Path
    function_name: str
    line_number: int
    operator: str
    original_source: str
    mutated_source: str
    diff: str
    status: str = "pending"  # "pending" | "killed" | "survived" | "error"
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mutant_id": self.mutant_id,
            "file_path": str(self.file_path),
            "function_name": self.function_name,
            "line_number": self.line_number,
            "operator": self.operator,
            "diff": self.diff,
            "status": self.status,
            "error_message": self.error_message,
        }


@dataclass
class MutationReport:
    total_mutants: int
    killed: int
    survived: int
    errors: int
    score: float
    surviving_mutants: List[Mutant] = field(default_factory=list)
    passed: bool = True
    report_text: str = ""
    ecosystem_tool: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_mutants": self.total_mutants,
            "killed": self.killed,
            "survived": self.survived,
            "errors": self.errors,
            "score": round(self.score, 2),
            "passed": self.passed,
            "ecosystem_tool": self.ecosystem_tool,
            "surviving_mutants": [m.to_dict() for m in self.surviving_mutants],
        }


def _replace_source_segment(
    source: str,
    lineno: int,
    col_offset: int,
    end_lineno: int,
    end_col_offset: int,
    replacement: str,
) -> str:
    """Replaces an exact AST segment using UTF-8 byte offsets without modifying other lines."""
    return replace_source_segment_utf8(source, lineno, col_offset, end_lineno, end_col_offset, replacement)


def _compute_unified_diff(original: str, mutated: str, file_path: str) -> str:
    """Computes a clean unified diff between original and mutated source."""
    diff_lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        mutated.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=2,
    )
    return "".join(diff_lines)


def detect_ecosystem_tools(repo_root: Path) -> Optional[str]:
    """Detects external mutation test runners configured in the repository."""
    repo_root = Path(repo_root)
    if (
        (repo_root / "stryker.config.json").is_file()
        or (repo_root / "stryker.conf.json").is_file()
        or (repo_root / "stryker.config.mjs").is_file()
    ):
        return "stryker"
    if (
        (repo_root / "cargo-mutants.toml").is_file()
        or (repo_root / ".cargo/mutants.toml").is_file()
    ):
        return "cargo-mutants"
    return None


class FunctionMutationCollector(ast.NodeVisitor):
    """AST Visitor collecting candidate AST nodes in a single function (skips nested defs)."""

    def __init__(
        self,
        target_lines: Set[int],
        source_lines: List[str],
        root_func: Optional[ast.AST] = None,
    ):
        self.target_lines = target_lines
        self.source_lines = source_lines
        self._root_func = root_func

        self.comparisons: List[ast.Compare] = []
        self.binops: List[ast.BinOp] = []
        self.augassigns: List[ast.AugAssign] = []
        self.boolops: List[ast.BoolOp] = []
        self.not_unaryops: List[ast.UnaryOp] = []
        self.statements: List[ast.stmt] = []
        self.returns: List[ast.Return] = []

    def _line_in_target(self, node: ast.AST) -> bool:
        lineno = getattr(node, "lineno", -1)
        if lineno in self.target_lines:
            if 1 <= lineno <= len(self.source_lines):
                line_str = self.source_lines[lineno - 1]
                if has_no_mutant_pragma(line_str) or is_arid_line(line_str):
                    return False
                if lineno > 1 and has_no_mutant_pragma(self.source_lines[lineno - 2]):
                    return False
            return True
        return False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._root_func is None or node is self._root_func:
            self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._root_func is None or node is self._root_func:
            self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self._root_func is None or node is self._root_func:
            self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if self._line_in_target(node):
            self.comparisons.append(node)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if self._line_in_target(node):
            self.binops.append(node)
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if self._line_in_target(node):
            self.boolops.append(node)
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if isinstance(node.op, ast.Not) and self._line_in_target(node):
            self.not_unaryops.append(node)
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if self._line_in_target(node):
            self.returns.append(node)
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        if self._line_in_target(node):
            self.statements.append(node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._line_in_target(node):
            self.statements.append(node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if self._line_in_target(node):
            self.augassigns.append(node)
            self.statements.append(node)
        self.generic_visit(node)


def generate_mutants_for_function(
    file_path: Path,
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    source_code: str,
    source_lines: List[str],
    target_lines: Set[int],
    mutant_counter: List[int],
    max_mutants: int = 6,
) -> List[Mutant]:
    """Generates up to max_mutants diverse mutants across AST nodes in a modified function."""
    collector = FunctionMutationCollector(target_lines, source_lines, root_func=func_node)
    collector.visit(func_node)

    func_name = func_node.name
    buckets: List[List[Tuple[ast.AST, str, str]]] = []

    # 1. Condition Inversion
    cond_bucket: List[Tuple[ast.AST, str, str]] = []
    for cmp_node in collector.comparisons:
        if len(cmp_node.ops) == 1:
            new_op = invert_compare_op(cmp_node.ops[0])
            if new_op is not None:
                mutated_cmp = copy.deepcopy(cmp_node)
                mutated_cmp.ops = [new_op]
                cond_bucket.append((cmp_node, "condition_inversion", ast.unparse(mutated_cmp)))
        elif len(cmp_node.ops) > 1:
            cond_bucket.append((cmp_node, "condition_inversion", f"not ({ast.unparse(cmp_node)})"))
    if cond_bucket:
        buckets.append(cond_bucket)

    # 2. Boundary Shift (BinOp and AugAssign given distinct buckets so neither starves the other)
    binop_bucket: List[Tuple[ast.AST, str, str]] = []
    for binop in collector.binops:
        new_op_bin = swap_arith_op(binop.op, include_mult_div=True)
        if new_op_bin is not None:
            mutated_bin = copy.deepcopy(binop)
            mutated_bin.op = new_op_bin
            binop_bucket.append((binop, "boundary_shift", ast.unparse(mutated_bin)))
    if binop_bucket:
        buckets.append(binop_bucket)

    aug_bucket: List[Tuple[ast.AST, str, str]] = []
    for aug in collector.augassigns:
        new_op_aug = swap_arith_op(aug.op, include_mult_div=True)
        if new_op_aug is not None:
            mutated_aug = copy.deepcopy(aug)
            mutated_aug.op = new_op_aug
            aug_bucket.append((aug, "boundary_shift", ast.unparse(mutated_aug)))
    if aug_bucket:
        buckets.append(aug_bucket)

    # 3. Logical Swap (canonical operator name)
    logic_bucket: List[Tuple[ast.AST, str, str]] = []
    for boolop in collector.boolops:
        new_op_bool = flip_bool_op(boolop.op)
        if new_op_bool is not None:
            mutated_bop = copy.deepcopy(boolop)
            mutated_bop.op = new_op_bool
            logic_bucket.append((boolop, "logical_swap", ast.unparse(mutated_bop)))
    for unop in collector.not_unaryops:
        logic_bucket.append((unop, "logical_swap", ast.unparse(unop.operand)))
    if logic_bucket:
        buckets.append(logic_bucket)

    # 4. Void Statement Delete (canonical operator name)
    stmt_bucket: List[Tuple[ast.AST, str, str]] = [
        (stmt, "void_statement_delete", "pass") for stmt in collector.statements
    ]
    if stmt_bucket:
        buckets.append(stmt_bucket)

    # 5. Return Stub (canonical operator name)
    ret_bucket: List[Tuple[ast.AST, str, str]] = []
    for ret_stmt in collector.returns:
        if ret_stmt.value is None or (isinstance(ret_stmt.value, ast.Constant) and ret_stmt.value.value is None):
            ret_bucket.append((ret_stmt, "return_stub", "return False"))
        elif isinstance(ret_stmt.value, ast.Constant) and isinstance(ret_stmt.value.value, bool):
            ret_bucket.append((ret_stmt, "return_stub", f"return {not ret_stmt.value.value}"))
        else:
            ret_bucket.append((ret_stmt, "return_stub", "return None"))
    if ret_bucket:
        buckets.append(ret_bucket)

    # Round-robin diversity selection across all non-empty buckets up to max_mutants
    selected: List[Tuple[ast.AST, str, str]] = []
    seen_spans: Set[Tuple[int, int, str]] = set()
    while len(selected) < max_mutants and any(buckets):
        progressed = False
        for bucket in buckets:
            if len(selected) >= max_mutants:
                break
            while bucket:
                node, op_name, replacement = bucket.pop(0)
                key = (getattr(node, "lineno", 1), getattr(node, "col_offset", 0), op_name)
                if key not in seen_spans:
                    seen_spans.add(key)
                    selected.append((node, op_name, replacement))
                    progressed = True
                    break
        if not progressed:
            break

    mutants: List[Mutant] = []
    for node, operator, replacement in selected:
        lineno = getattr(node, "lineno", 1)
        col_offset = getattr(node, "col_offset", 0)
        end_lineno = getattr(node, "end_lineno", lineno)
        end_col_offset = getattr(node, "end_col_offset", col_offset + len(replacement))
        mutated_src = _replace_source_segment(
            source=source_code,
            lineno=lineno,
            col_offset=col_offset,
            end_lineno=end_lineno,
            end_col_offset=end_col_offset,
            replacement=replacement,
        )
        if mutated_src == source_code:
            continue
        try:
            ast.parse(mutated_src)
        except SyntaxError:
            continue
        mutant_counter[0] += 1
        mutants.append(
            Mutant(
                mutant_id=f"mutant_{mutant_counter[0]}",
                file_path=file_path,
                function_name=func_name,
                line_number=lineno,
                operator=operator,
                original_source=source_code,
                mutated_source=mutated_src,
                diff=_compute_unified_diff(source_code, mutated_src, str(file_path)),
            )
        )

    return mutants


def generate_mutants_for_file(
    file_path: Path,
    target_lines: Set[int],
    mutant_counter: List[int],
) -> List[Mutant]:
    """Generates mutants for a single Python file across its modified functions."""
    if not file_path.is_file() or file_path.is_symlink() or file_path.suffix.lower() not in (".py", ".pyi"):
        return []

    try:
        source_code = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source_code, filename=str(file_path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []

    source_lines = source_code.splitlines(keepends=True)
    mutants: List[Mutant] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_start = node.lineno
            fn_end = getattr(node, "end_lineno", fn_start + len(node.body))
            fn_lines = {ln for ln in target_lines if fn_start <= ln <= fn_end}
            if fn_lines:
                mutants.extend(
                    generate_mutants_for_function(
                        file_path=file_path,
                        func_node=node,
                        source_code=source_code,
                        source_lines=source_lines,
                        target_lines=fn_lines,
                        mutant_counter=mutant_counter,
                    )
                )

    return mutants


def generate_mutants_for_diff(
    repo_root: Path,
    diff_text: Optional[str] = None,
) -> List[Mutant]:
    """Diff-aware mutant generator with repo containment and timeout guards."""
    repo_root = Path(repo_root).resolve()
    if diff_text is not None:
        diff_lines_map = parse_diff_lines(diff_text)
    else:
        try:
            res = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
                timeout=10.0,
            )
            diff_lines_map = parse_diff_lines(res.stdout) if res.returncode == 0 and res.stdout else {}
        except (subprocess.SubprocessError, OSError) as exc:
            sys.stderr.write(f"[!] Warning: git diff failed in {repo_root}: {exc}\n")
            diff_lines_map = {}

    mutants: List[Mutant] = []
    mutant_counter = [0]

    for rel_path, line_set in diff_lines_map.items():
        if not line_set or is_test_file(rel_path):
            continue
        file_path = resolve_repo_target(repo_root, rel_path)
        if file_path is None:
            continue
        if file_path.suffix.lower() in (".py", ".pyi"):
            mutants.extend(generate_mutants_for_file(file_path, line_set, mutant_counter))

    return mutants


def _resolve_probe_test_cmd(
    repo_root: Path,
    file_path: Path,
    explicit_test_cmd: Optional[str],
) -> Optional[str]:
    """Resolves a targeted test command for file_path without falling back to full unittest discover."""
    if explicit_test_cmd:
        return explicit_test_cmd
    try:
        rel_file = str(file_path.relative_to(repo_root))
    except ValueError:
        rel_file = str(file_path)
    resolve_fn = _mp_attr("resolve_affected_tests", resolve_affected_tests)
    resolved = resolve_fn(repo_root=repo_root, modified_files=[rel_file], mode="diff")
    if not resolved.is_empty and resolved.runner_cmd:
        return resolved.runner_cmd
    stem_test = repo_root / "tests" / f"test_{file_path.stem}.py"
    if stem_test.is_file():
        return f"python3 -m unittest {stem_test.relative_to(repo_root)}"
    return None


def run_micro_mutation_probe(
    repo_root: Path,
    diff_text: Optional[str] = None,
    test_cmd: Optional[str] = None,
    timeout_sec: float = 10.0,
) -> MutationReport:
    """Runs diff-aware micro-mutation probe with baseline check, shell=False, and strict pass gate."""
    _mp_attr("_install_safety_handlers", _install_safety_handlers)()
    repo_root = Path(repo_root).resolve()
    ecosystem_tool = detect_ecosystem_tools(repo_root)

    gen_fn = _mp_attr("generate_mutants_for_diff", generate_mutants_for_diff)
    mutants = gen_fn(repo_root, diff_text=diff_text)
    if len(mutants) > 20:
        return MutationReport(
            total_mutants=len(mutants),
            killed=0,
            survived=0,
            errors=1,
            score=0.0,
            passed=False,
            ecosystem_tool=ecosystem_tool,
            report_text=(
                f"✖ Exceeded hard mutant cap of 20 mutants per inner-loop run (generated {len(mutants)}). "
                f"Scope your diff or apply '# agyis: no-mutant' pragmas to non-critical logic to prevent runaway loops."
            ),
        )

    if not mutants:
        return MutationReport(
            total_mutants=0,
            killed=0,
            survived=0,
            errors=0,
            score=100.0,
            passed=True,
            ecosystem_tool=ecosystem_tool,
            report_text="✔ 0 mutants generated for current diff (clean working tree or arid lines). Mutation score: 100.0%.",
        )

    killed = 0
    survived = 0
    errors = 0
    surviving_mutants: List[Mutant] = []
    baseline_cache: Dict[str, Tuple[bool, str]] = {}

    for mutant in mutants:
        safe_path = resolve_repo_target(repo_root, mutant.file_path)
        if safe_path is None:
            mutant.status = "error"
            mutant.error_message = f"Refused mutation outside repository root or symlink: {mutant.file_path}"
            errors += 1
            continue

        cmd_to_run = _resolve_probe_test_cmd(repo_root, safe_path, test_cmd)
        if not cmd_to_run:
            mutant.status = "survived"
            mutant.error_message = "No targeted test suite found for modified file"
            survived += 1
            surviving_mutants.append(mutant)
            continue

        clean_cmd, guarded_env = inject_non_interactive_guards(cmd_to_run)
        if "PYTHONPATH" not in guarded_env or str(repo_root) not in guarded_env.get("PYTHONPATH", ""):
            guarded_env["PYTHONPATH"] = f"{repo_root}:{guarded_env.get('PYTHONPATH', '')}".rstrip(":")

        # Baseline check once per unique command before mutating source
        base_ok, base_err = check_baseline_cached(
            baseline_cache, clean_cmd, guarded_env, repo_root, timeout_sec
        )
        if not base_ok:
            mutant.status = "error"
            mutant.error_message = base_err
            errors += 1
            continue

        original_content = safe_path.read_text(encoding="utf-8")
        register_backup(safe_path, original_content)
        try:
            safe_path.write_text(mutant.mutated_source, encoding="utf-8")
            res = run_targeted_test_cmd(clean_cmd, guarded_env, repo_root, timeout=timeout_sec)
            if res.returncode in _RUNNER_ERROR_EXIT_CODES:
                mutant.status = "error"
                mutant.error_message = f"Test runner exited with command error code {res.returncode}"
                errors += 1
            elif res.returncode != 0:
                mutant.status = "killed"
                killed += 1
            else:
                mutant.status = "survived"
                survived += 1
                surviving_mutants.append(mutant)
        except subprocess.TimeoutExpired:
            mutant.status = "killed"
            killed += 1
        except (OSError, ValueError, subprocess.SubprocessError) as ex:
            mutant.status = "error"
            mutant.error_message = str(ex)
            errors += 1
        finally:
            try:
                safe_path.write_text(original_content, encoding="utf-8")
            finally:
                clear_backup(safe_path)

    total = len(mutants)
    score = (killed / total) * 100.0 if total > 0 else 100.0
    passed = killed > 0 and survived == 0 and errors == 0

    lines: List[str] = [
        f"Micro-Mutation Probe: {total} mutants generated across diff.",
        f"Killed: {killed} | Survived: {survived} | Errors: {errors} | Score: {score:.1f}%",
    ]
    if ecosystem_tool:
        lines.append(f"Ecosystem Mutation Runner Detected: {ecosystem_tool}")

    if surviving_mutants:
        lines.append("\n✖ SURVIVING MUTANTS DETECTED (Insufficient Test Coverage):")
        for sm in surviving_mutants:
            lines.append(f"\n--- [{sm.mutant_id}] {sm.file_path}:{sm.line_number} in {sm.function_name}() ({sm.operator}) ---")
            lines.append(sm.diff.strip())
        lines.append(
            "\nTip: Add assertions for these code paths, or annotate intentional exclusions with "
            "'# agyis: no-mutant <reason>'."
        )
    elif errors > 0:
        lines.append(f"\n✖ MUTATION PROBE FAILED: {errors} execution/baseline error(s) prevented verification.")
    elif passed:
        lines.append("\n✔ All mutants killed! Diff verification passed.")

    report_text = "\n".join(lines)

    return MutationReport(
        total_mutants=total,
        killed=killed,
        survived=survived,
        errors=errors,
        score=score,
        surviving_mutants=surviving_mutants,
        passed=passed,
        report_text=report_text,
        ecosystem_tool=ecosystem_tool,
    )
