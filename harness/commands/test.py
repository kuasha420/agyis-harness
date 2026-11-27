# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Test suite runner CLI command (ADR-014, ADR-015, RFC-051 Phase 2).
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional
import unittest

from harness.discovery import (
    detect_project_test_runner,
    inject_non_interactive_guards,
    resolve_affected_tests,
)
from harness.hooks import completion_fence_hook
from harness.utils import theme

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _record_verification_all(success: bool, tier: str = "full") -> None:
    try:
        completion_fence_hook.record_verification(success=success, tier=tier)
    except TypeError:
        completion_fence_hook.record_verification(success=success)
    state_dir = completion_fence_hook.get_state_dir()
    if state_dir.exists():
        for sf in state_dir.glob("verification_state_*.json"):
            cid = sf.stem.replace("verification_state_", "")
            try:
                completion_fence_hook.record_verification(success=success, tier=tier, conv_id=cid)
            except TypeError:
                completion_fence_hook.record_verification(success=success, conv_id=cid)


def _is_agyis_source_repo(cwd: Path) -> bool:
    """Returns True strictly when cwd is the agyis-harness source repository checkout."""
    resolved_cwd = cwd.resolve()
    resolved_repo = REPO_ROOT.resolve()
    has_source_layout = (resolved_cwd / "tests").is_dir() and (resolved_cwd / "pyproject.toml").is_file()
    if not has_source_layout:
        return False
    if resolved_cwd == resolved_repo:
        return True
    if (resolved_cwd / "harness" / "cli.py").is_file():
        try:
            pyproj = (resolved_cwd / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
            return '"agyis-harness"' in pyproj or "'agyis-harness'" in pyproj or "psl-agy-harness" in pyproj
        except OSError:
            return False
    return False


def _same_resolved_dir(raw_path: str, target: Path) -> bool:
    try:
        return Path(raw_path).resolve() == target
    except OSError:
        return os.path.abspath(raw_path) == str(target)


def _build_delegated_test_cmd(runner_py: str, args: argparse.Namespace) -> List[str]:
    """Forward test CLI arguments to the delegated checkout runner."""
    cmd = [runner_py, "-m", "harness.cli", "test"]
    if getattr(args, "verbose", False):
        cmd.append("--verbose")
    start_dir = getattr(args, "start_dir", None)
    if start_dir is not None:
        cmd.extend(["--start-dir", str(start_dir)])
    if getattr(args, "diff", False):
        cmd.append("--diff")
    branch = getattr(args, "branch", None)
    if branch:
        cmd.extend(["--branch", str(branch)])
    if getattr(args, "affected", False):
        cmd.append("--affected")
    pkg = getattr(args, "pkg", None)
    if pkg:
        cmd.extend(["--pkg", str(pkg)])
    if getattr(args, "full", False):
        cmd.append("--full")
    if getattr(args, "harmonize", False):
        cmd.append("--harmonize")
    if getattr(args, "dry_run", False):
        cmd.append("--dry-run")
    if getattr(args, "mutation", False):
        cmd.append("--mutation")
    if getattr(args, "json", False):
        cmd.append("--json")
    if getattr(args, "no_buffer", False):
        cmd.append("--no-buffer")
    return cmd


def _delegate_to_cwd_checkout(cwd: Path, args: argparse.Namespace) -> int:
    """Delegate `agyis test` to the active source checkout in cwd when loaded from another root."""
    venv_py = cwd / ".venv" / "bin" / "python"
    runner_py = (
        os.path.abspath(str(venv_py))
        if venv_py.is_file() and os.access(str(venv_py), os.X_OK)
        else sys.executable
    )
    cmd = _build_delegated_test_cmd(runner_py, args)

    env = os.environ.copy()
    existing_pypath = env.get("PYTHONPATH", "")
    pypath_parts = [p for p in existing_pypath.split(os.pathsep) if p and not _same_resolved_dir(p, cwd)]
    env["PYTHONPATH"] = os.pathsep.join([str(cwd), *pypath_parts]) if pypath_parts else str(cwd)
    env["_AGYIS_TEST_REEXEC"] = "1"

    has_real_fds = True
    try:
        sys.stdout.fileno()
        sys.stderr.fileno()
    except (AttributeError, io.UnsupportedOperation, ValueError):
        has_real_fds = False

    if has_real_fds:
        proc = subprocess.run(cmd, cwd=str(cwd), env=env)
        return proc.returncode

    proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True)
    if isinstance(proc.stdout, str) and proc.stdout:
        sys.stdout.write(proc.stdout)
    if isinstance(proc.stderr, str) and proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


def _emit_test_json(payload: Dict[str, Any]) -> None:
    """Emit structured JSON output for test runs."""
    print(json.dumps(payload, indent=2))


def _run_guarded_shell_runner(
    runner_cmd: str,
    cwd: Path,
    as_json: bool,
    mode: str,
    tier: str,
    dry_run: bool = False,
    dry_run_label: Optional[str] = None,
) -> int:
    """Execute a shell test runner command with non-interactive CI guards and optional JSON reporting."""
    if dry_run:
        if as_json:
            _emit_test_json({
                "passed": True,
                "success": True,
                "mode": mode,
                "tier": tier,
                "dry_run": True,
                "command": runner_cmd,
                "exit_code": 0,
            })
        else:
            print(dry_run_label or theme.badge("PASS", f"[DRY-RUN] Would execute: {runner_cmd}"))
        return 0

    clean_cmd, guarded_env = inject_non_interactive_guards(runner_cmd)
    if as_json:
        run_res = subprocess.run(
            clean_cmd,
            shell=True,
            env=guarded_env,
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )
        success = run_res.returncode == 0
        _record_verification_all(success=success, tier=tier)
        _emit_test_json({
            "passed": success,
            "success": success,
            "mode": mode,
            "tier": tier,
            "command": runner_cmd,
            "exit_code": run_res.returncode,
            "stdout": run_res.stdout or "",
            "stderr": run_res.stderr or "",
        })
        return run_res.returncode

    run_res = subprocess.run(clean_cmd, shell=True, env=guarded_env, cwd=str(cwd))
    success = run_res.returncode == 0
    _record_verification_all(success=success, tier=tier)
    return run_res.returncode


def cmd_test(args: argparse.Namespace) -> int:
    """Runs the test suite with diff-awareness and tier-gated verification."""
    cwd = Path.cwd().resolve()
    as_json = bool(getattr(args, "json", False))

    if os.environ.get("_AGYIS_TEST_REEXEC"):
        os.environ.pop("_AGYIS_TEST_REEXEC", None)
    elif _is_agyis_source_repo(cwd) and REPO_ROOT.resolve() != cwd:
        return _delegate_to_cwd_checkout(cwd, args)

    # 1. Harmonization pre-step if requested
    if getattr(args, "harmonize", False):
        from harness.harmonize.test_runner import harmonize_test_runners
        dry_run = getattr(args, "dry_run", False)
        res = harmonize_test_runners(workspace_dir=cwd, dry_run=dry_run, apply=not dry_run)
        if not res.success:
            if as_json:
                _emit_test_json({"passed": False, "success": False, "mode": "harmonize", "error": res.message})
            else:
                sys.stderr.write(f"Harmonization error: {res.message}\n")
            return 1
        if dry_run:
            if as_json:
                _emit_test_json({"passed": True, "success": True, "mode": "harmonize", "dry_run": True, "message": res.message})
            else:
                print(theme.badge("PASS", f"[DRY-RUN] {res.message}"))
            return 0

    # 1.5. Micro-mutation testing if requested
    if getattr(args, "mutation", False):
        from harness.mutation.micro_probe import run_micro_mutation, MutationConfig
        config = MutationConfig(
            verbose=getattr(args, "verbose", False),
            repo_root=cwd,
        )
        result = run_micro_mutation(config=config)
        if result.error_message:
            if as_json:
                _emit_test_json({
                    "error": result.error_message,
                    "passed": False,
                    "total_mutants": result.total_mutants,
                    "killed": result.killed_mutants,
                    "survived": len(result.survived_mutants),
                    "exit_code": result.exit_code,
                })
            else:
                sys.stderr.write(theme.badge("FAIL", result.error_message, stream=sys.stderr) + "\n")
            _record_verification_all(success=False, tier="mutation")
            return result.exit_code or 1

        if as_json:
            score = 100.0 if result.total_mutants == 0 else (result.killed_mutants / result.total_mutants) * 100.0
            passed = len(result.survived_mutants) == 0
            payload = {
                "total_mutants": result.total_mutants,
                "killed": result.killed_mutants,
                "killed_mutants": result.killed_mutants,
                "survived": len(result.survived_mutants),
                "survived_mutants": [sm.to_dict() if hasattr(sm, "to_dict") else str(sm) for sm in result.survived_mutants],
                "score": score,
                "passed": passed,
            }
            _emit_test_json(payload)
            _record_verification_all(success=passed, tier="mutation")
            return 0 if passed else 1

        if result.total_mutants == 0:
            print(theme.badge("PASS", "0 mutants generated (clean working tree or only arid lines modified)."))
            _record_verification_all(success=True, tier="mutation")
            return 0

        print(f"\nMicro-mutation testing complete: {result.killed_mutants}/{result.total_mutants} killed.")
        if result.survived_mutants:
            for sm in result.survived_mutants:
                print(sm.to_actionable_report())
            _record_verification_all(success=False, tier="mutation")
            return 1
        print(theme.badge("PASS", "All mutants killed! Test suite verified."))
        _record_verification_all(success=True, tier="mutation")
        return 0

    is_diff = getattr(args, "diff", False)
    is_affected = getattr(args, "affected", False)
    branch = getattr(args, "branch", None)
    pkg = getattr(args, "pkg", None)
    is_full = getattr(args, "full", False)

    # 2. Diff-aware affected test resolution (if any diff flag provided and not --full)
    if (is_diff or is_affected or branch or pkg) and not is_full:
        mode = "affected" if is_affected else "diff"
        resolved = resolve_affected_tests(
            repo_root=cwd,
            mode=mode,
            branch=branch,
            pkg=pkg,
        )

        tier_to_record = "affected" if is_affected else ("pkg" if pkg else "diff")
        out_mode = "pkg" if pkg else mode

        if resolved.is_empty:
            _record_verification_all(success=True, tier=tier_to_record)
            if as_json:
                _emit_test_json({
                    "passed": True,
                    "success": True,
                    "mode": out_mode,
                    "tier": tier_to_record,
                    "empty": True,
                    "tests_run": 0,
                    "exit_code": 0,
                })
            else:
                print(theme.badge("PASS", f"0 affected tests detected for {mode} scope on clean working tree."))
            return 0

        return _run_guarded_shell_runner(
            runner_cmd=resolved.runner_cmd,
            cwd=cwd,
            as_json=as_json,
            mode=out_mode,
            tier=tier_to_record,
            dry_run=bool(getattr(args, "dry_run", False)),
            dry_run_label=theme.badge("PASS", f"[DRY-RUN] Would execute: {resolved.runner_cmd} (Tier {resolved.tier}: {resolved.tier_name})"),
        )

    # 3. Macro / Full Test Execution
    start_dir = getattr(args, "start_dir", None)

    if start_dir:
        test_dir = Path(start_dir)
    elif _is_agyis_source_repo(cwd):
        test_dir = cwd / "tests"
    else:
        # In external repositories, always consult detect_project_test_runner(cwd)
        # regardless of whether a local tests/ directory exists.
        external_runner = detect_project_test_runner(cwd)
        if external_runner:
            return _run_guarded_shell_runner(
                runner_cmd=external_runner,
                cwd=cwd,
                as_json=as_json,
                mode="external",
                tier="full",
                dry_run=bool(getattr(args, "dry_run", False)),
                dry_run_label=theme.badge("PASS", f"[DRY-RUN] Would execute full project runner: {external_runner}"),
            )

        local_tests_dir = cwd / "tests"
        if not local_tests_dir.is_dir():
            err_msg = f"Error: No recognized test runner or 'tests/' directory found in {cwd}"
            if as_json:
                _emit_test_json({"passed": False, "success": False, "mode": "unittest", "error": err_msg, "exit_code": 1})
            else:
                sys.stderr.write(f"{err_msg}\n")
            return 1
        test_dir = local_tests_dir

    # Standard python unittest discovery
    if not test_dir.exists():
        err_msg = f"Error: test directory not found at {test_dir}"
        if as_json:
            _emit_test_json({"passed": False, "success": False, "mode": "unittest", "error": err_msg, "exit_code": 1})
        else:
            sys.stderr.write(f"{err_msg}\n")
        return 1

    resolved_test_dir = test_dir.resolve()
    has_pkg_init = (resolved_test_dir / "__init__.py").is_file()
    top_dir = cwd if (resolved_test_dir == (cwd / "tests").resolve() and has_pkg_init) else resolved_test_dir

    orig_sys_path = list(sys.path)
    try:
        if str(cwd) in sys.path:
            sys.path.remove(str(cwd))
        sys.path.insert(0, str(cwd))
        if str(top_dir) != str(cwd) and str(top_dir) not in sys.path:
            sys.path.insert(1, str(top_dir))

        loader = unittest.TestLoader()
        suite = loader.discover(
            start_dir=str(test_dir),
            pattern="test_*.py",
            top_level_dir=str(top_dir),
        )
        if str(cwd) in sys.path:
            sys.path.remove(str(cwd))
        sys.path.insert(0, str(cwd))

        verbosity = 2 if getattr(args, "verbose", False) else 1
        buffer_output = not getattr(args, "no_buffer", False)
        if as_json:
            stream = io.StringIO()
            runner = unittest.TextTestRunner(stream=stream, verbosity=verbosity, buffer=True)
            result = runner.run(suite)
            success = bool(result.wasSuccessful())
            _record_verification_all(success=success, tier="full")
            _emit_test_json({
                "passed": success,
                "success": success,
                "mode": "unittest",
                "test_dir": str(test_dir),
                "tests_run": getattr(result, "testsRun", 0),
                "failures": len(getattr(result, "failures", [])),
                "errors": len(getattr(result, "errors", [])),
                "skipped": len(getattr(result, "skipped", [])),
                "exit_code": 0 if success else 1,
                "output": stream.getvalue(),
            })
            return 0 if success else 1

        runner = unittest.TextTestRunner(verbosity=verbosity, buffer=buffer_output)
        result = runner.run(suite)

        success = result.wasSuccessful()
        _record_verification_all(success=success, tier="full")
        return 0 if success else 1
    finally:
        sys.path[:] = orig_sys_path
