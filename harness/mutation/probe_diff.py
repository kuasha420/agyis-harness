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
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set

from harness.discovery import inject_non_interactive_guards, resolve_affected_tests
from harness.mutation.probe_operators import (
    ACTIVE_BACKUPS,
    _install_safety_handlers,
    flip_bool_op,
    has_no_mutant_pragma,
    invert_compare_op,
    is_arid_line,
    is_test_file,
    replace_source_segment_utf8,
    swap_arith_op,
)


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


def parse_diff_lines(diff_text: str) -> Dict[str, Set[int]]:
    """
    Parses unified diff text to extract modified line numbers per file.
    Returns mapping from relative file path to set of modified 1-indexed line numbers.
    """
    modified_lines: Dict[str, Set[int]] = {}
    current_file: Optional[str] = None
    current_line = 0

    diff_file_pat = re.compile(r"^diff --git a/(.+?) b/(.+?)$")
    hunk_pat = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for line in diff_text.splitlines():
        m_file = diff_file_pat.match(line)
        if m_file:
            current_file = m_file.group(2)
            if current_file not in modified_lines:
                modified_lines[current_file] = set()
            continue

        if line.startswith("+++ "):
            path_part = line[4:].strip()
            if path_part.startswith("b/"):
                path_part = path_part[2:]
            if path_part and path_part != "/dev/null":
                current_file = path_part
                if current_file not in modified_lines:
                    modified_lines[current_file] = set()
            continue

        m_hunk = hunk_pat.match(line)
        if m_hunk:
            current_line = int(m_hunk.group(1))
            continue

        if current_file is not None and "current_line" in locals():
            if line.startswith("+") and not line.startswith("+++"):
                modified_lines[current_file].add(current_line)
                current_line += 1
            elif line.startswith(" "):
                current_line += 1
            elif line.startswith("-"):
                pass

    return modified_lines


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
    """AST Visitor collecting candidate AST nodes for mutation in a function."""

    def __init__(self, target_lines: Set[int], source_lines: List[str]):
        self.target_lines = target_lines
        self.source_lines = source_lines

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
            return True
        return False

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
) -> List[Mutant]:
    """Generates 5-6 mutants for a modified function using the 5 operators."""
    collector = FunctionMutationCollector(target_lines, source_lines)
    collector.visit(func_node)

    mutants: List[Mutant] = []
    func_name = func_node.name

    def _add_mutant(node: ast.AST, operator: str, replacement: str) -> None:
        mutant_counter[0] += 1
        m_id = f"mutant_{mutant_counter[0]}"
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
        diff_str = _compute_unified_diff(source_code, mutated_src, str(file_path))

        mutants.append(
            Mutant(
                mutant_id=m_id,
                file_path=file_path,
                function_name=func_name,
                line_number=lineno,
                operator=operator,
                original_source=source_code,
                mutated_source=mutated_src,
                diff=diff_str,
            )
        )

    # 1. Condition Inversion: == <-> !=, < <-> >=, <= <-> >, in <-> not in, is <-> is not
    if collector.comparisons:
        cmp_node = collector.comparisons[0]
        if len(cmp_node.ops) == 1:
            new_op = invert_compare_op(cmp_node.ops[0])
            if new_op is not None:
                mutated_cmp = copy.deepcopy(cmp_node)
                mutated_cmp.ops = [new_op]
                _add_mutant(cmp_node, "condition_inversion", ast.unparse(mutated_cmp))

    # 2. Boundary Shift: + 1 <-> - 1, + <-> -, * <-> /
    if collector.binops:
        binop = collector.binops[0]
        new_op_bin = swap_arith_op(binop.op, include_mult_div=True)
        if new_op_bin is not None:
            mutated_bin = copy.deepcopy(binop)
            mutated_bin.op = new_op_bin
            _add_mutant(binop, "boundary_shift", ast.unparse(mutated_bin))
    if collector.augassigns:
        aug = collector.augassigns[0]
        new_op_aug = swap_arith_op(aug.op, include_mult_div=True)
        if new_op_aug is not None:
            mutated_aug = copy.deepcopy(aug)
            mutated_aug.op = new_op_aug
            _add_mutant(aug, "boundary_shift", ast.unparse(mutated_aug))

    # 3. Logical Flip: and <-> or, not x <-> x
    if collector.boolops:
        boolop = collector.boolops[0]
        new_op_bool = flip_bool_op(boolop.op)
        if new_op_bool is not None:
            mutated_bop = copy.deepcopy(boolop)
            mutated_bop.op = new_op_bool
            _add_mutant(boolop, "logical_flip", ast.unparse(mutated_bop))
    elif collector.not_unaryops:
        unop = collector.not_unaryops[0]
        _add_mutant(unop, "logical_flip", ast.unparse(unop.operand))

    # 4. Statement Drop: Replace statement with pass
    if collector.statements:
        stmt = collector.statements[0]
        _add_mutant(stmt, "statement_drop", "pass")

    # 5. Return Negation / Replacement: return x -> return None, return True -> return False
    if collector.returns:
        ret_stmt = collector.returns[0]
        if ret_stmt.value is None or (isinstance(ret_stmt.value, ast.Constant) and ret_stmt.value.value is None):
            _add_mutant(ret_stmt, "return_negation", "return True")
        elif isinstance(ret_stmt.value, ast.Constant) and isinstance(ret_stmt.value.value, bool):
            new_val = not ret_stmt.value.value
            _add_mutant(ret_stmt, "return_negation", f"return {new_val}")
        else:
            _add_mutant(ret_stmt, "return_negation", "return None")

    return mutants


def generate_mutants_for_file(
    file_path: Path,
    target_lines: Set[int],
    mutant_counter: List[int],
) -> List[Mutant]:
    """Generates mutants for a single Python file across its modified functions."""
    if not file_path.is_file() or file_path.suffix.lower() not in (".py", ".pyi"):
        return []

    try:
        source_code = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source_code, filename=str(file_path))
    except Exception:
        return []

    source_lines = source_code.splitlines(keepends=True)
    mutants: List[Mutant] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_start = node.lineno
            fn_end = getattr(node, "end_lineno", fn_start + len(node.body))
            fn_lines = {ln for ln in target_lines if fn_start <= ln <= fn_end}
            if fn_lines:
                fn_mutants = generate_mutants_for_function(
                    file_path=file_path,
                    func_node=node,
                    source_code=source_code,
                    source_lines=source_lines,
                    target_lines=fn_lines,
                    mutant_counter=mutant_counter,
                )
                mutants.extend(fn_mutants)

    return mutants


def generate_mutants_for_diff(
    repo_root: Path,
    diff_text: Optional[str] = None,
) -> List[Mutant]:
    """
    Diff-aware mutant generator (Route A compatibility).
    """
    repo_root = Path(repo_root).resolve()
    if diff_text is not None:
        diff_lines_map = parse_diff_lines(diff_text)
    else:
        # Fallback to working tree git diff
        try:
            res = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            diff_lines_map = parse_diff_lines(res.stdout) if res.stdout else {}
        except Exception:
            diff_lines_map = {}

    mutants: List[Mutant] = []
    mutant_counter = [0]

    for rel_path, line_set in diff_lines_map.items():
        if not line_set:
            continue
        file_path = (repo_root / rel_path).resolve()
        if not file_path.exists():
            continue
        if file_path.suffix.lower() in (".py", ".pyi"):
            if is_test_file(rel_path):
                continue
            file_mutants = generate_mutants_for_file(file_path, line_set, mutant_counter)
            mutants.extend(file_mutants)

    return mutants


def run_micro_mutation_probe(
    repo_root: Path,
    diff_text: Optional[str] = None,
    test_cmd: Optional[str] = None,
) -> MutationReport:
    """
    Runs diff-aware micro-mutation probe against modified lines in repository.
    (Route A compatibility entrypoint).
    """
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

    for mutant in mutants:
        original_content = mutant.file_path.read_text(encoding="utf-8")
        ACTIVE_BACKUPS[mutant.file_path] = original_content
        try:
            mutant.file_path.write_text(mutant.mutated_source, encoding="utf-8")
            if test_cmd:
                cmd_to_run = test_cmd
            else:
                try:
                    rel_file = str(mutant.file_path.relative_to(repo_root))
                except ValueError:
                    rel_file = str(mutant.file_path)
                resolve_fn = _mp_attr("resolve_affected_tests", resolve_affected_tests)
                resolved = resolve_fn(
                    repo_root=repo_root,
                    modified_files=[rel_file],
                    mode="diff",
                )
                if not resolved.is_empty:
                    cmd_to_run = resolved.runner_cmd
                elif (repo_root / "tests").is_dir():
                    cmd_to_run = "python3 -m unittest discover -s tests"
                else:
                    cmd_to_run = "python3 -m unittest"

            clean_cmd, guarded_env = inject_non_interactive_guards(cmd_to_run)
            if "PYTHONPATH" not in guarded_env or str(repo_root) not in guarded_env.get("PYTHONPATH", ""):
                guarded_env["PYTHONPATH"] = f"{repo_root}:{guarded_env.get('PYTHONPATH', '')}".rstrip(":")

            res = subprocess.run(
                clean_cmd,
                shell=True,
                env=guarded_env,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            if res.returncode != 0:
                mutant.status = "killed"
                killed += 1
            else:
                mutant.status = "survived"
                survived += 1
                surviving_mutants.append(mutant)
        except subprocess.TimeoutExpired:
            mutant.status = "killed"
            killed += 1
        except Exception as ex:
            mutant.status = "error"
            mutant.error_message = str(ex)
            errors += 1
        finally:
            mutant.file_path.write_text(original_content, encoding="utf-8")
            ACTIVE_BACKUPS.pop(mutant.file_path, None)

    total = len(mutants)
    score = (killed / total) * 100.0 if total > 0 else 100.0
    passed = (survived == 0)

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
    else:
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
