# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Diff-Aware In-Harness Micro-Mutator Engine (ADR-014, ADR-015, Epic #51 Phase 3.1).

Architectural Invariants Enforced:
1. Diff-Targeted: Only mutate uncommitted working tree lines in git diff HEAD.
2. Arid-Line Suppression: Skip imports, type annotations, comments, docstrings, logs.
3. 5-6 Mutation Operators: Condition invert, logic swap, boundary shift, return stub, void delete.
4. Diversity Sampling: Cap at 5-6 mutants per modified function.
5. Affected Test Execution: Strictly execute Tier 1A affected tests via harness.discovery.
6. Actionable Feedback: Emit clear unified diff snippets and surviving mutant locations.
7. Inline Pragma: Support '# agyis: no-mutant <reason>' for verified equivalent mutants.
8. Crash Safety: Atomic in-memory backups, try...finally restoration, atexit, and signal traps.
"""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Set, Tuple

from harness.discovery import (
    inject_non_interactive_guards,
    resolve_affected_tests,
)
from harness.mutation.probe_diff import (
    FunctionMutationCollector,
    Mutant,
    MutationReport,
    _compute_unified_diff,
    _replace_source_segment,
    detect_ecosystem_tools,
    generate_mutants_for_diff,
    generate_mutants_for_file,
    generate_mutants_for_function,
    parse_diff_lines,
    run_micro_mutation_probe,
)
from harness.mutation.probe_operators import (
    ACTIVE_BACKUPS,
    MUTATABLE_EXTENSIONS,
    PRAGMA_PATTERN,
    TYPE_ANNOTATION_ONLY,
    FunctionMutant,
    MutationCandidate,
    MutationConfig,
    MutationResult,
    PythonAstMutator,
    SurvivingMutant,
    _SAFETY_HANDLERS_INSTALLED,
    _SAFETY_LOCK,
    _install_safety_handlers,
    _restore_all_backups,
    _sig_handler,
    apply_operator,
    extract_diff_mutation_candidates,
    generate_function_mutants,
    has_no_mutant_pragma,
    is_arid_line,
    is_test_file,
    mutate_python_source,
    mutate_token_source,
)

__all__ = [
    "ACTIVE_BACKUPS",
    "FunctionMutant",
    "FunctionMutationCollector",
    "MUTATABLE_EXTENSIONS",
    "Mutant",
    "MutationCandidate",
    "MutationConfig",
    "MutationReport",
    "MutationResult",
    "PRAGMA_PATTERN",
    "PythonAstMutator",
    "SurvivingMutant",
    "TYPE_ANNOTATION_ONLY",
    "_SAFETY_HANDLERS_INSTALLED",
    "_SAFETY_LOCK",
    "_compute_unified_diff",
    "_install_safety_handlers",
    "_replace_source_segment",
    "_restore_all_backups",
    "_sig_handler",
    "apply_operator",
    "detect_ecosystem_tools",
    "extract_diff_mutation_candidates",
    "generate_function_mutants",
    "generate_mutants_for_diff",
    "generate_mutants_for_file",
    "generate_mutants_for_function",
    "has_no_mutant_pragma",
    "is_arid_line",
    "is_test_file",
    "mutate_python_source",
    "mutate_token_source",
    "parse_diff_lines",
    "run_micro_mutation",
    "run_micro_mutation_probe",
]


def run_micro_mutation(
    target_diff: Optional[str] = None,
    files: Optional[List[str]] = None,
    config: Optional[MutationConfig] = None,
) -> MutationResult:
    """
    Executes diff-aware in-harness micro-mutation testing against uncommitted diffs.
    Runs affected test suites for each mutant and reports surviving mutants.
    Guarantees hermetic in-memory backups and zero source corruption.
    """
    _install_safety_handlers()
    cfg = config or MutationConfig()
    repo_root = cfg.repo_root or Path.cwd().resolve()

    # 1. Diff Extraction
    if target_diff is not None:
        diff_text = target_diff
    else:
        try:
            res = subprocess.run(
                ["git", "diff", "-U0", "HEAD"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            diff_text = res.stdout if res.returncode == 0 else ""
        except Exception:
            diff_text = ""

    # 2. Fast Path: Clean working tree
    if not diff_text.strip() and not files:
        return MutationResult(total_mutants=0, killed_mutants=0, survived_mutants=[], exit_code=0)

    # 3. Candidate Discovery
    candidates = extract_diff_mutation_candidates(diff_text)
    if files:
        file_set = {str(Path(f).resolve()) for f in files} | {str(f) for f in files}
        candidates = [c for c in candidates if str((repo_root / c.file_path).resolve()) in file_set or c.file_path in file_set]

    if not candidates:
        return MutationResult(total_mutants=0, killed_mutants=0, survived_mutants=[], exit_code=0)

    # 4. Group by file
    by_file: Dict[str, List[MutationCandidate]] = {}
    for c in candidates:
        by_file.setdefault(c.file_path, []).append(c)

    total_mutants = 0
    killed_mutants = 0
    survived_mutants: List[SurvivingMutant] = []
    suppressed_by_pragma = 0

    # 5. Plan mutants across candidate files
    all_planned: List[Tuple[str, Path, str, FunctionMutant]] = []

    for rel_path, file_candidates in by_file.items():
        file_path = repo_root / rel_path
        if not file_path.is_file():
            continue

        try:
            original_content = file_path.read_text(encoding="utf-8")
        except Exception:
            continue

        lines = original_content.splitlines()

        # Check line-level escape pragmas (same line or preceding line)
        active_candidates: List[MutationCandidate] = []
        for cand in file_candidates:
            line_idx = cand.line_number - 1
            if line_idx < 0 or line_idx >= len(lines):
                continue
            line_text = lines[line_idx]

            # Same line pragma
            if has_no_mutant_pragma(line_text):
                suppressed_by_pragma += 1
                continue

            # Preceding line pragma
            if line_idx > 0 and has_no_mutant_pragma(lines[line_idx - 1]):
                suppressed_by_pragma += 1
                continue

            active_candidates.append(cand)

        if not active_candidates:
            continue

        # Generate planned mutants
        is_python = rel_path.endswith(".py")
        if is_python:
            target_lines = {c.line_number for c in active_candidates}
            # Walk AST to locate functions and candidates
            try:
                tree = ast.parse(original_content)
                # Map each target line to enclosing function name
                func_map: Dict[int, str] = {}
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        start_l = node.lineno
                        end_l = getattr(node, "end_lineno", start_l + len(node.body))
                        for l in range(start_l, end_l + 1):
                            if l in target_lines:
                                func_map[l] = node.name

                # Try operators on target lines
                cands_by_func: Dict[str, List[Tuple[int, str]]] = {}
                for cand in active_candidates:
                    l = cand.line_number
                    fname = func_map.get(l, "<module>")
                    for op in ("condition_inversion", "logical_swap", "boundary_shift", "return_stub", "void_statement_delete", "literal_mutation"):
                        cands_by_func.setdefault(fname, []).append((l, op))

                for fname, op_cands in cands_by_func.items():
                    # Diversity sample per function: cap at max_mutants_per_function
                    count = 0
                    seen_ops: Set[str] = set()
                    for l, op in op_cands:
                        if count >= cfg.max_mutants_per_function:
                            break
                        if op in seen_ops:
                            continue
                        file_mut_src, diff_snip = mutate_python_source(
                            original_content,
                            target_line=l,
                            operator=op,
                        )
                        if file_mut_src and file_mut_src != original_content:
                            all_planned.append((
                                rel_path,
                                file_path,
                                original_content,
                                FunctionMutant(
                                    mutated_code=file_mut_src,
                                    operator=op,
                                    line_number=l,
                                    diff_snippet=diff_snip,
                                    function_name=fname,
                                ),
                            ))
                            seen_ops.add(op)
                            count += 1
            except (SyntaxError, OSError, ValueError, TypeError):
                pass
        else:
            # Polyglot TS/JS/Rust fallback
            for cand in active_candidates:
                mut_line, op = mutate_token_source(cand.content, lang=Path(rel_path).suffix.lstrip("."))
                if mut_line != cand.content:
                    file_lines = list(lines)
                    file_lines[cand.line_number - 1] = mut_line
                    file_mut_src = "\n".join(file_lines) + ("\n" if original_content.endswith("\n") else "")
                    diff_snip = f"- {cand.content}\n+ {mut_line}"
                    all_planned.append((
                        rel_path,
                        file_path,
                        original_content,
                        FunctionMutant(
                            mutated_code=file_mut_src,
                            operator=op,
                            line_number=cand.line_number,
                            diff_snippet=diff_snip,
                            function_name="<external>",
                        ),
                    ))

    # 6. Hard mutant cap enforcement: fail-fast if exceeded
    if len(all_planned) > cfg.max_mutants_total:
        return MutationResult(
            total_mutants=len(all_planned),
            killed_mutants=0,
            survived_mutants=[],
            exit_code=1,
            suppressed_by_pragma=suppressed_by_pragma,
            error_message=(
                f"Exceeded hard mutant cap of {cfg.max_mutants_total} mutants per inner-loop run "
                f"(generated {len(all_planned)} mutants). Scope your diff or apply inline "
                f"'# agyis: no-mutant' pragmas to prevent runaway mutation loops."
            ),
        )

    # 7. Run planned mutants
    for rel_path, file_path, original_content, pm in all_planned:
        total_mutants += 1
        ACTIVE_BACKUPS[file_path] = original_content
        file_path.write_text(pm.mutated_code, encoding="utf-8")
        try:
            resolved = resolve_affected_tests(
                repo_root=repo_root,
                modified_files=[rel_path],
                mode="diff",
            )
            if rel_path == "harness/cli.py" and "tests/test_cli.py" in resolved.runner_cmd:
                extra_cli_tests = [
                    t for t in ("tests/test_test_smells.py", "tests/test_micro_probe.py")
                    if (repo_root / t).is_file()
                ]
                if extra_cli_tests:
                    resolved.runner_cmd += " " + " ".join(extra_cli_tests)

            if resolved.is_empty:
                survived_mutants.append(SurvivingMutant(
                    file_path=rel_path,
                    function_name=pm.function_name,
                    line_number=pm.line_number,
                    operator=pm.operator,
                    diff_snippet=pm.diff_snippet,
                    test_target="<none>",
                ))
            else:
                clean_cmd, guarded_env = inject_non_interactive_guards(resolved.runner_cmd)
                if "PYTHONPATH" not in guarded_env or str(repo_root) not in guarded_env.get("PYTHONPATH", ""):
                    guarded_env["PYTHONPATH"] = f"{repo_root}:{guarded_env.get('PYTHONPATH', '')}".rstrip(":")
                try:
                    proc = subprocess.run(
                        clean_cmd,
                        shell=True,
                        env=guarded_env,
                        cwd=str(repo_root),
                        capture_output=True,
                        text=True,
                        timeout=cfg.timeout_sec,
                    )
                    if proc.returncode != 0:
                        killed_mutants += 1
                    else:
                        survived_mutants.append(SurvivingMutant(
                            file_path=rel_path,
                            function_name=pm.function_name,
                            line_number=pm.line_number,
                            operator=pm.operator,
                            diff_snippet=pm.diff_snippet,
                            test_target=resolved.runner_cmd,
                        ))
                        if cfg.fail_fast:
                            break
                except subprocess.TimeoutExpired:
                    killed_mutants += 1
        finally:
            file_path.write_text(original_content, encoding="utf-8")
            ACTIVE_BACKUPS.pop(file_path, None)

    exit_code = 1 if len(survived_mutants) > 0 else 0
    return MutationResult(
        total_mutants=total_mutants,
        killed_mutants=killed_mutants,
        survived_mutants=survived_mutants,
        exit_code=exit_code,
        suppressed_by_pragma=suppressed_by_pragma,
    )

