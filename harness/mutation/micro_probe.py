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
5. Affected Test Execution: Strictly execute Tier 1A affected tests via harness.discovery (shell=False).
6. Baseline Verification: Confirm unmutated tests pass before counting mutant failures as killed.
7. Inline Pragma: Support '# agyis: no-mutant <reason>' for verified equivalent mutants.
8. Crash Safety: Locked in-memory backups, try...finally restoration, atexit, and lock-free signal traps.
"""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
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
    run_micro_mutation_probe,
)
from harness.mutation.probe_operators import (
    ACTIVE_BACKUPS,
    CANONICAL_OPERATORS,
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
    check_baseline_cached,
    clear_backup,
    extract_diff_mutation_candidates,
    generate_function_mutants,
    has_no_mutant_pragma,
    is_arid_line,
    is_test_file,
    mutate_python_source,
    mutate_token_source,
    parse_diff_lines,
    register_backup,
    resolve_repo_target,
    run_targeted_test_cmd,
)

_RUNNER_ERROR_EXIT_CODES = frozenset({126, 127})

__all__ = [
    "ACTIVE_BACKUPS",
    "CANONICAL_OPERATORS",
    "FunctionMutant",
    "FunctionMutationCollector",
    "MUTATABLE_EXTENSIONS",
    "Mutant",
    "MutationCandidate",
    "MutationConfig",
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
    "clear_backup",
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
    "register_backup",
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
    Validates baseline test health, executes affected test suites with shell=False,
    and guarantees repo-contained locked backups with zero source corruption.
    """
    _install_safety_handlers()
    cfg = config or MutationConfig()
    repo_root = (cfg.repo_root or Path.cwd()).resolve()
    allowed_ops = tuple(cfg.operators) if cfg.operators else CANONICAL_OPERATORS

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
        except (subprocess.SubprocessError, OSError) as exc:
            if cfg.verbose:
                sys.stderr.write(f"[!] git diff failed in {repo_root}: {exc}\n")
            diff_text = ""

    # 2. Fast Path: Clean working tree
    if not diff_text.strip() and not files:
        return MutationResult(total_mutants=0, killed_mutants=0, survived_mutants=[], exit_code=0)

    # 3. Candidate Discovery
    candidates = extract_diff_mutation_candidates(diff_text)
    if files:
        file_set = {str(Path(f).resolve()) for f in files} | {str(f) for f in files}
        candidates = [
            c for c in candidates
            if str((repo_root / c.file_path).resolve()) in file_set or c.file_path in file_set
        ]

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

    # 5. Plan mutants across repo-contained candidate files
    all_planned: List[Tuple[str, Path, str, FunctionMutant]] = []

    for rel_path, file_candidates in by_file.items():
        file_path = resolve_repo_target(repo_root, rel_path)
        if file_path is None:
            if cfg.verbose:
                sys.stderr.write(f"[!] Skipping out-of-repo or symlinked target: {rel_path}\n")
            continue

        try:
            original_content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            if cfg.verbose:
                sys.stderr.write(f"[!] Could not read {file_path}: {exc}\n")
            continue

        lines = original_content.splitlines()

        # Check line-level escape pragmas (same line or preceding line)
        active_candidates: List[MutationCandidate] = []
        for cand in file_candidates:
            line_idx = cand.line_number - 1
            if line_idx < 0 or line_idx >= len(lines):
                continue
            line_text = lines[line_idx]

            if has_no_mutant_pragma(line_text):
                suppressed_by_pragma += 1
                continue
            if line_idx > 0 and has_no_mutant_pragma(lines[line_idx - 1]):
                suppressed_by_pragma += 1
                continue
            active_candidates.append(cand)

        if not active_candidates:
            continue

        is_python = rel_path.endswith(".py")
        if is_python:
            target_lines = {c.line_number for c in active_candidates}
            try:
                tree = ast.parse(original_content)
                func_map: Dict[int, str] = {}
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        start_l = node.lineno
                        end_l = getattr(node, "end_lineno", start_l + len(node.body))
                        for ln in range(start_l, end_l + 1):
                            if ln in target_lines:
                                func_map[ln] = node.name

                cands_by_func: Dict[str, List[Tuple[int, str]]] = {}
                for cand in active_candidates:
                    ln = cand.line_number
                    fname = func_map.get(ln, "<module>")
                    for op in allowed_ops:
                        cands_by_func.setdefault(fname, []).append((ln, op))

                for fname, op_cands in cands_by_func.items():
                    count = 0
                    seen_ops: Set[str] = set()
                    for ln, op in op_cands:
                        if count >= cfg.max_mutants_per_function:
                            break
                        if op in seen_ops:
                            continue
                        file_mut_src, diff_snip = mutate_python_source(
                            original_content,
                            target_line=ln,
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
                                    line_number=ln,
                                    diff_snippet=diff_snip,
                                    function_name=fname,
                                ),
                            ))
                            seen_ops.add(op)
                            count += 1
            except (SyntaxError, ValueError, TypeError) as exc:
                if cfg.verbose:
                    sys.stderr.write(f"[!] AST mutation planning failed for {rel_path}: {exc}\n")
        else:
            for cand in active_candidates:
                mut_line, op = mutate_token_source(cand.content, lang=Path(rel_path).suffix.lstrip("."))
                if mut_line != cand.content and (not cfg.operators or op in allowed_ops):
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

    # 7. Run planned mutants with baseline verification and locked backups
    baseline_cache: Dict[str, Tuple[bool, str]] = {}
    errors: List[str] = []

    for rel_path, file_path, original_content, pm in all_planned:
        total_mutants += 1
        resolved = resolve_affected_tests(
            repo_root=repo_root,
            modified_files=[rel_path],
            mode="diff",
        )
        if resolved.is_empty:
            survived_mutants.append(SurvivingMutant(
                file_path=rel_path,
                function_name=pm.function_name,
                line_number=pm.line_number,
                operator=pm.operator,
                diff_snippet=pm.diff_snippet,
                test_target="<none>",
            ))
            if cfg.fail_fast:
                break
            continue

        clean_cmd, guarded_env = inject_non_interactive_guards(resolved.runner_cmd)
        if "PYTHONPATH" not in guarded_env or str(repo_root) not in guarded_env.get("PYTHONPATH", ""):
            guarded_env["PYTHONPATH"] = f"{repo_root}:{guarded_env.get('PYTHONPATH', '')}".rstrip(":")

        # Baseline test check on unmutated code once per unique command
        base_ok, base_err = check_baseline_cached(
            baseline_cache, clean_cmd, guarded_env, repo_root, cfg.timeout_sec
        )
        if not base_ok:
            errors.append(base_err)
            if cfg.verbose:
                sys.stderr.write(f"[!] {base_err}\n")
            if cfg.fail_fast:
                break
            continue

        register_backup(file_path, original_content)
        try:
            file_path.write_text(pm.mutated_code, encoding="utf-8")
            if cfg.verbose:
                sys.stderr.write(f"[*] Mutating {rel_path}:{pm.line_number} ({pm.operator})\n")
            try:
                proc = run_targeted_test_cmd(clean_cmd, guarded_env, repo_root, timeout=cfg.timeout_sec)
                if proc.returncode in _RUNNER_ERROR_EXIT_CODES:
                    errors.append(f"Test runner error (exit {proc.returncode}) for {rel_path}:{pm.line_number}")
                elif proc.returncode != 0:
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
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                errors.append(f"Mutation test execution error for {rel_path}:{pm.line_number}: {exc}")
        finally:
            try:
                file_path.write_text(original_content, encoding="utf-8")
            finally:
                clear_backup(file_path)

    error_message = "; ".join(errors) if errors else None
    exit_code = 1 if (len(survived_mutants) > 0 or len(errors) > 0) else 0
    return MutationResult(
        total_mutants=total_mutants,
        killed_mutants=killed_mutants,
        survived_mutants=survived_mutants,
        exit_code=exit_code,
        suppressed_by_pragma=suppressed_by_pragma,
        error_message=error_message,
    )
