# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Polyglot Project Test Runner Discovery (RFC-051 / Issue #81).

Inspects workspace directory trees to detect native project test runners across:
- JavaScript/TypeScript: pnpm, npm, yarn, bun, vitest, playwright, jest
- Rust: Cargo, Nextest
- Python: pytest, unittest
- Go: go test
- C/C++: ctest, make test
- JVM: Gradle, Maven
- .NET: dotnet test
- Shell: bash tests/*.sh
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from harness.discovery_manifest import (
    detect_node_runner_command,
    detect_non_node_runner,
    guard_package_manager_cmd,
    has_non_python_test_surface,
    pm_exec_prefix,
    read_test_manifest,
    resolve_manifest_full_command,
    resolve_node_package_manager,
)


def detect_project_test_runner(cwd: Union[Path, str, None] = None) -> Optional[str]:
    """
    Inspects cwd for client project test runners:
      * .agyis/test_manifest.json (tier_3_full / tier_2b_full / test:full)
      * package.json / packageManager / lockfiles -> 'pnpm test', 'yarn test', 'bun test', 'npm test', Playwright/Vitest/Jest
      * Cargo.toml, pyproject.toml, go.mod, Gradle, Maven, .NET, CMake, Makefile, Elixir, tests/*.sh
    Returns None if no recognized runner is identified.
    """
    root = Path.cwd() if cwd is None else Path(cwd)
    try:
        if not root.is_dir():
            return None
        manifest_cmd = resolve_manifest_full_command(root)
        if manifest_cmd:
            return manifest_cmd
        node_cmd = detect_node_runner_command(root)
        if node_cmd:
            return node_cmd
        return detect_non_node_runner(root)
    except OSError:
        return None


EXEMPT_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".mp4", ".mp3", ".wav", ".bin", ".exe", ".tar", ".gz", ".zip", ".pdf",
    ".lock", ".sum", ".pyc", ".pyo", ".pyd", ".DS_Store",
    ".md", ".markdown", ".txt", ".rst",
}


def is_git_repo(cwd: Union[Path, str, None] = None) -> bool:
    """Verifies that cwd is inside a valid git working tree."""
    target_dir = Path(cwd or Path.cwd()).resolve()
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=target_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except (FileNotFoundError, OSError):
        return False


def is_ephemeral_scratch_path(file_path: str, cwd: Path | str | None = None) -> bool:
    """
    Determines if a file path represents an ephemeral scratch file or is outside
    the target workspace root. Scratch files do not trigger code dirty state.

    Rules:
    1. Paths containing .gemini/antigravity/brain/ and /scratch/ return True.
    2. When cwd is provided: files outside cwd (not target_path.is_relative_to(workspace_root)) return True.
    3. When cwd is not provided: paths in system temp directories (/tmp/, /var/tmp/) return True.
    """
    if not file_path or not isinstance(file_path, str):
        return False

    norm = file_path.replace("\\", "/").strip()
    if norm.startswith("./"):
        norm = norm[2:]

    # Rule 0: REA ephemeral scratch paths
    if norm.startswith(".rea/") or "/.rea/" in norm:
        return True
    if norm.startswith("decompiled/") or "/decompiled/" in norm:
        return True
    if norm.startswith("artifacts/rea/") or "/artifacts/rea/" in norm:
        return True

    # Rule 1: Antigravity brain and workspace ephemeral scratch paths
    if ".gemini/antigravity/brain" in norm and "/scratch/" in norm:
        return True
    if norm.startswith("scratch/") or "/scratch/" in norm:
        return True
    if norm.startswith(".agents/scratch/") or "/.agents/scratch/" in norm:
        return True

    # Rule 2: When cwd is provided, check if path resolves outside cwd
    if cwd is not None:
        try:
            workspace_root = Path(cwd).resolve()
            p = Path(file_path)
            target_path = p.resolve() if p.is_absolute() else (workspace_root / p).resolve()
            if not target_path.is_relative_to(workspace_root):
                return True
        except (ValueError, OSError):
            pass
    else:
        # Rule 3: When cwd is not provided, paths in system temp directories return True
        if norm.startswith("/tmp/") or norm == "/tmp" or norm.startswith("/var/tmp/") or norm == "/var/tmp":
            return True
        try:
            p = Path(file_path)
            if p.is_absolute():
                resolved = p.resolve()
                for temp_base in (Path("/tmp"), Path("/var/tmp"), Path(tempfile.gettempdir())):
                    if resolved.is_relative_to(temp_base.resolve()):
                        return True
        except (ValueError, OSError):
            pass

    return False


def get_git_modified_files(
    cwd: Union[Path, str, None] = None,
    branch: Optional[str] = None,
) -> List[str]:
    """
    Extracts modified, added, staged, unstaged, and untracked code files.
    - Default (branch=None): strict working tree anchor:
      `git diff --name-only HEAD` + untracked files from `git status --porcelain -uall`.
    - branch=<ref>: finds merge-base via `git merge-base HEAD <ref>` and diffs from base.
    - Filters binary, exempt, and internal files.
    - Returns clean, sorted, deduplicated relative POSIX path list.
    """
    target_dir = Path(cwd or Path.cwd()).resolve()
    if not is_git_repo(target_dir):
        return []

    modified_files: Set[str] = set()

    # Check if HEAD exists
    head_check = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=target_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    has_head = head_check.returncode == 0

    if has_head:
        if branch:
            # Find merge-base with target branch
            mb_res = subprocess.run(
                ["git", "merge-base", "HEAD", branch],
                cwd=target_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            base_ref = mb_res.stdout.strip() if mb_res.returncode == 0 and mb_res.stdout.strip() else branch
            diff_res = subprocess.run(
                ["git", "diff", "--name-only", base_ref],
                cwd=target_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if diff_res.returncode == 0:
                for line in diff_res.stdout.splitlines():
                    f = line.strip()
                    if f:
                        modified_files.add(Path(f).as_posix())
        else:
            # Strict working tree anchor: diff HEAD captures staged & unstaged modifications
            diff_res = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=target_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if diff_res.returncode == 0:
                for line in diff_res.stdout.splitlines():
                    f = line.strip()
                    if f:
                        modified_files.add(Path(f).as_posix())

    # Untracked and staged/unstaged files via git status --porcelain -uall
    status_res = subprocess.run(
        ["git", "status", "--porcelain", "-uall"],
        cwd=target_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if status_res.returncode == 0:
        for line in status_res.stdout.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                status_code, path_part = parts[0], parts[1]
                if "->" in path_part:
                    path_part = path_part.split("->")[-1].strip()
                path_part = path_part.strip().strip('"')
                if status_code == "??" or not has_head:
                    modified_files.add(Path(path_part).as_posix())
                elif has_head and not branch:
                    modified_files.add(Path(path_part).as_posix())

    # Discover git submodules
    submodules: Set[str] = set()
    gm_path = target_dir / ".gitmodules"
    if gm_path.is_file():
        try:
            for line in gm_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith("path") and "=" in line:
                    parts = line.split("=", 1)
                    if parts[0].strip() == "path":
                        sub_p = parts[1].strip().replace("\\", "/").rstrip("/")
                        if sub_p:
                            submodules.add(sub_p)
        except Exception:
            pass

    # Filter out exempt extensions, directory prefixes, submodules, and ephemeral scratch paths
    filtered_files: List[str] = []
    for f in modified_files:
        p = Path(f)
        if p.suffix.lower() in EXEMPT_EXTENSIONS:
            continue
        posix_str = p.as_posix()
        if posix_str.startswith(".git/") or posix_str.startswith(".system_generated/"):
            continue
        if any(posix_str == sm or posix_str.startswith(sm + "/") for sm in submodules):
            continue
        target_path = target_dir / posix_str
        if target_path.is_dir() and ((target_path / ".git").is_file() or (target_path / ".git").is_dir()):
            continue
        if is_ephemeral_scratch_path(posix_str, cwd=target_dir):
            continue
        filtered_files.append(posix_str)

    filtered_files.sort()
    return filtered_files


@dataclass
class ResolvedTests:
    """Outcome of tiered affected test dependency resolution."""
    runner_cmd: str
    test_files: List[str]
    source_files: List[str]
    tier: int  # 1: Native, 2: Structural, 3: Directory/Package Fallback, 0: Empty
    tier_name: str  # "native", "structural", "fallback", "empty", "full"
    scope: str  # "diff", "affected", "pkg", "full"
    package: Optional[str] = None
    is_empty: bool = False


def is_test_file_path(p_str: str) -> bool:
    """Returns True if a relative path appears to be a test file."""
    p = Path(p_str)
    name = p.name
    if name.startswith("test_") and p.suffix == ".py":
        return True
    if name.endswith("_test.py"):
        return True
    if re.search(r"\.(test|spec)\.(ts|js|tsx|jsx|mts|mjs)$", name):
        return True
    if p.parts and ("tests" in p.parts or "test" in p.parts or "__tests__" in p.parts):
        if p.suffix in (".py", ".ts", ".js", ".tsx", ".jsx", ".rs", ".go"):
            return True
    return False


def _resolve_native_js_rust_tests(
    root: Path,
    files: List[str],
    js_ts_files: List[str],
    rust_files: List[str],
    pm_exec: str,
    cargo_cmd: str,
    has_vitest: bool,
    has_jest: bool,
    has_cargo: bool,
    mode: str,
    pkg: Optional[str],
) -> Optional[ResolvedTests]:
    """Resolve Level 1 native runner commands for Vitest, Jest, and Cargo workspaces."""
    if has_vitest or has_jest:
        if rust_files and not js_ts_files:
            return ResolvedTests(
                runner_cmd=cargo_cmd, test_files=[], source_files=files,
                tier=1, tier_name="native", scope=mode, package=pkg,
            )
        target_files = js_ts_files or files
        files_arg = " ".join(shlex.quote(f) for f in target_files)
        js_cmd = (
            f"{pm_exec}vitest related {files_arg} --run"
            if has_vitest
            else f"{pm_exec}jest --findRelatedTests {files_arg} --passWithNoTests"
        )
        cmd = f"{js_cmd} && {cargo_cmd}" if (rust_files and js_ts_files) else js_cmd
        return ResolvedTests(
            runner_cmd=cmd, test_files=[], source_files=files,
            tier=1, tier_name="native", scope=mode, package=pkg,
        )
    if has_cargo and rust_files and not js_ts_files:
        return ResolvedTests(
            runner_cmd=cargo_cmd, test_files=[], source_files=files,
            tier=1, tier_name="native", scope=mode, package=pkg,
        )
    return None


def _resolve_js_file_runner_cmd(root: Path, quoted_tests: str, pkg_data: Optional[Dict[str, Any]]) -> str:
    """Resolve targeted JS/TS test file execution without injecting broken npm --no-watch flags."""
    has_node_markers = (root / "package.json").is_file() or any(
        (root / lf).is_file()
        for lf in ("pnpm-lock.yaml", ".pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock", "bunfig.toml")
    )
    pm = resolve_node_package_manager(root, pkg_data)
    pm_exec = pm_exec_prefix(pm) if has_node_markers else ""
    scripts = pkg_data.get("scripts", {}) if isinstance(pkg_data, dict) and isinstance(pkg_data.get("scripts"), dict) else {}
    deps = (
        {**(pkg_data.get("dependencies") or {}), **(pkg_data.get("devDependencies") or {})}
        if isinstance(pkg_data, dict) else {}
    )
    test_script = str(scripts.get("test", ""))
    if "@playwright/test" in deps or "playwright" in deps or any(root.glob("playwright.config.*")):
        return f"{pm_exec}playwright test {quoted_tests}"
    if "node --test" in test_script or "node --test" in str(scripts):
        return f"node --test {quoted_tests}"
    if "tsx" in test_script:
        return f"{pm_exec}tsx --test {quoted_tests}"
    if pm == "yarn":
        return f"yarn test {quoted_tests}"
    return f"{pm} test -- {quoted_tests}"


def resolve_affected_tests(
    repo_root: Union[Path, str, None] = None,
    modified_files: Optional[List[str]] = None,
    mode: str = "diff",
    branch: Optional[str] = None,
    pkg: Optional[str] = None,
) -> ResolvedTests:
    """
    Tiered dependency resolver (RFC-051 Phase 2 R2):
    Level 1: Native runner capabilities (vitest related, jest --findRelatedTests)
    Level 2: Structural heuristic mapping (direct test files, co-located tests, mapped tests/ dir)
    Level 3: Enclosing directory / package scope fallback
    """
    root = Path(repo_root or Path.cwd()).resolve()
    files = get_git_modified_files(cwd=root, branch=branch) if modified_files is None else list(modified_files)

    if pkg:
        prefix_matches = (f"packages/{pkg}/", f"apps/{pkg}/", f"{pkg}/")
        files = [f for f in files if any(f.startswith(p) for p in prefix_matches)]

    if not files:
        return ResolvedTests(
            runner_cmd="", test_files=[], source_files=[],
            tier=0, tier_name="empty", scope=mode, package=pkg, is_empty=True,
        )

    js_ts_exts = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".svelte", ".vue", ".html", ".css"}
    js_ts_files = [f for f in files if Path(f).suffix.lower() in js_ts_exts]
    rust_files = [
        f for f in files
        if Path(f).suffix.lower() == ".rs" or (Path(f).parts and Path(f).parts[0] in ("src-tauri", "native"))
    ]

    package_json = root / "package.json"
    pkg_data: Optional[Dict[str, Any]] = None
    has_vitest = bool(list(root.glob("vitest.config.*")))
    has_jest = bool(list(root.glob("jest.config.*")))
    try:
        if package_json.is_file():
            loaded = json.loads(package_json.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                pkg_data = loaded
                deps = {**(loaded.get("dependencies") or {}), **(loaded.get("devDependencies") or {})}
                scripts = loaded.get("scripts") or {}
                if not has_vitest and ("vitest" in deps or "vitest" in str(scripts.get("test", ""))):
                    has_vitest = True
                if not has_jest and ("jest" in deps or "jest" in str(scripts.get("test", ""))):
                    has_jest = True
    except Exception:
        pass

    has_node_lock = any(
        (root / lf).is_file()
        for lf in ("pnpm-lock.yaml", ".pnpm-lock.yaml", "bun.lockb", "bun.lock", "bunfig.toml", "yarn.lock")
    )
    pm_exec = pm_exec_prefix(resolve_node_package_manager(root, pkg_data)) if (package_json.is_file() or has_node_lock) else ""

    cargo_manifest_arg = ""
    has_cargo = False
    for sub in ("src-tauri", "native"):
        if (root / sub / "Cargo.toml").is_file():
            cargo_manifest_arg = f" --manifest-path {sub}/Cargo.toml"
            has_cargo = True
            break
    if not has_cargo and (root / "Cargo.toml").is_file():
        has_cargo = True
    cargo_cmd = f"cargo test{cargo_manifest_arg}"

    level1 = _resolve_native_js_rust_tests(
        root, files, js_ts_files, rust_files, pm_exec, cargo_cmd,
        has_vitest, has_jest, has_cargo, mode, pkg,
    )
    if level1 is not None:
        return level1

    # Level 2: Structural heuristic mapping
    matched_test_files: Set[str] = set()
    for f in files:
        p = Path(f)
        if is_test_file_path(f):
            if (root / f).is_file():
                matched_test_files.add(f)
            continue

        stem, suffix = p.stem, p.suffix
        candidates: List[Path] = [
            p.parent / f"{stem}.test{suffix}",
            p.parent / f"{stem}.spec{suffix}",
            p.parent / f"test_{stem}{suffix}",
            p.parent / "__tests__" / f"{stem}.test{suffix}",
        ]
        if p.parts and p.parts[0] == "src":
            rel_dir = Path(*p.parts[1:-1]) if len(p.parts) > 2 else Path(".")
            candidates.extend([
                Path("tests") / rel_dir / f"test_{stem}{suffix}",
                Path("tests") / rel_dir / f"{stem}.test{suffix}",
                Path("tests") / rel_dir / f"{stem}.spec{suffix}",
                Path("tests") / f"test_{stem}{suffix}",
            ])
        elif p.parts and p.parts[0] == "harness":
            candidates.append(Path("tests") / f"test_{stem}.py")
        else:
            candidates.extend([
                Path("tests") / p.parent / f"test_{stem}{suffix}",
                Path("tests") / f"test_{stem}{suffix}",
                Path("tests") / f"{stem}.test{suffix}",
            ])

        for cand in candidates:
            if (root / cand).is_file():
                matched_test_files.add(cand.as_posix())

    if matched_test_files:
        sorted_tests = sorted(matched_test_files)
        quoted_tests = " ".join(shlex.quote(t) for t in sorted_tests)
        if any(t.endswith(".py") for t in sorted_tests):
            if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists() or (root / "setup.cfg").exists():
                cmd = f"pytest {quoted_tests}"
            else:
                cmd = f"python3 -m unittest {quoted_tests}"
        elif any(t.endswith((".ts", ".tsx", ".js", ".jsx")) for t in sorted_tests):
            cmd = _resolve_js_file_runner_cmd(root, quoted_tests, pkg_data)
        elif any(t.endswith(".rs") for t in sorted_tests):
            cmd = f"{cargo_cmd} {quoted_tests}"
        elif any(t.endswith(".go") for t in sorted_tests):
            cmd = f"go test {quoted_tests}"
        else:
            cmd = f"python3 -m unittest {quoted_tests}"

        return ResolvedTests(
            runner_cmd=cmd, test_files=sorted_tests, source_files=files,
            tier=2, tier_name="structural", scope=mode, package=pkg,
        )

    # Level 3: Enclosing directory / package scope fallback
    for f in files:
        p = Path(f)
        for parent in [p] + list(p.parents):
            pkg_manifest = root / parent / "package.json"
            if pkg_manifest.is_file() and parent != Path("."):
                try:
                    data = json.loads(pkg_manifest.read_text(encoding="utf-8"))
                    detected_pkg = data.get("name") or parent.name
                    return ResolvedTests(
                        runner_cmd=f"pnpm --filter {detected_pkg} test",
                        test_files=[], source_files=files,
                        tier=3, tier_name="fallback", scope=mode, package=detected_pkg,
                    )
                except Exception:
                    pass

    fallback_tests: Set[str] = set()
    for f in files:
        p = Path(f)
        dirs_to_check: List[Path] = []
        if p.parts and p.parts[0] == "src":
            rel_dir = Path(*p.parts[1:-1]) if len(p.parts) > 2 else Path(".")
            dirs_to_check.append(root / "tests" / rel_dir)
        dirs_to_check.extend([root / p.parent, root / p.parent / "__tests__"])
        for d in dirs_to_check:
            if d.is_dir():
                try:
                    for item in d.iterdir():
                        if item.is_file() and is_test_file_path(item.as_posix()):
                            fallback_tests.add(item.relative_to(root).as_posix())
                except OSError:
                    pass

    if fallback_tests:
        sorted_fallback = sorted(fallback_tests)
        quoted_fallback = " ".join(shlex.quote(t) for t in sorted_fallback)
        if any(t.endswith(".py") for t in sorted_fallback):
            cmd = f"python3 -m unittest {quoted_fallback}"
        else:
            cmd = _resolve_js_file_runner_cmd(root, quoted_fallback, pkg_data)
        return ResolvedTests(
            runner_cmd=cmd, test_files=sorted_fallback, source_files=files,
            tier=3, tier_name="fallback", scope=mode, package=pkg,
        )

    runner = detect_project_test_runner(root)
    if not runner:
        runner = "" if has_non_python_test_surface(root) else "python3 -m unittest discover -s tests"
    return ResolvedTests(
        runner_cmd=runner, test_files=[], source_files=files,
        tier=3, tier_name="fallback", scope=mode, package=pkg,
    )


def is_non_interactive_context() -> bool:
    """Returns True if running in an agent, CI, or non-TTY context."""
    for env_key in (
        "CI",
        "CONTINUOUS_INTEGRATION",
        "ANTIGRAVITY",
        "ANTIGRAVITY_AGENT",
        "GEMINI_CLI",
        "AGYIS_AGENT",
        "PSL_AGENT",
    ):
        if os.environ.get(env_key, "").lower() in ("true", "1", "yes"):
            return True
    if os.environ.get("ANTIGRAVITY_CONVERSATION_ID", "").strip():
        return True
    if os.environ.get("DEBIAN_FRONTEND", "").lower() == "noninteractive":
        return True
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return True
    except (AttributeError, ValueError, OSError):
        return True
    return False


def inject_non_interactive_guards(
    cmd: str,
    env: Optional[Dict[str, str]] = None,
    cwd: Union[Path, str, None] = None,
) -> Tuple[str, Dict[str, str]]:
    """Guards test subshells by injecting CI=true and safe non-watch flags."""
    new_env = dict(env if env is not None else os.environ)
    new_env["CI"] = "true"
    new_env["NONINTERACTIVE"] = "true"
    return guard_package_manager_cmd(cmd.strip(), cwd=cwd), new_env
