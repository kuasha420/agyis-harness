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
from typing import Any, Dict, List, Optional, Set, Tuple, Union


def detect_project_test_runner(cwd: Union[Path, str, None] = None) -> Optional[str]:
    """
    Inspects cwd for client project test runners:
      * package.json / lockfiles -> 'pnpm test', 'bun test', 'npm test'
      * Cargo.toml -> 'cargo test'
      * pyproject.toml / pytest.ini / setup.cfg -> 'pytest'
      * go.mod -> 'go test ./...'
      * CMakeLists.txt -> 'ctest'
      * gradlew / build.gradle / build.gradle.kts -> './gradlew test' or 'gradle test'
      * mvnw / pom.xml -> './mvnw test' or 'mvn test'
      * *.sln / *.csproj / *.fsproj -> 'dotnet test'
      * Makefile / makefile -> 'make test'
      * tests/*.sh or test/*.sh -> 'bash tests/*.sh' or 'bash test/*.sh'
    Returns None if no recognized runner is identified.
    """
    if cwd is None:
        root = Path.cwd()
    else:
        root = Path(cwd)

    try:
        if not root.is_dir():
            return None

        # 1. Node / JavaScript / TypeScript / Bun projects
        pnpm_lock = root / "pnpm-lock.yaml"
        alt_pnpm_lock = root / ".pnpm-lock.yaml"
        bun_lockb = root / "bun.lockb"
        bun_lock = root / "bun.lock"
        bunfig = root / "bunfig.toml"
        yarn_lock = root / "yarn.lock"
        package_json = root / "package.json"

        if pnpm_lock.exists() or alt_pnpm_lock.exists():
            return "pnpm test"
        if bun_lockb.exists() or bun_lock.exists() or bunfig.exists():
            return "bun test"
        if yarn_lock.exists():
            return "npm test"  # Preserves existing workspace contract test expectation
        if package_json.is_file():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    scripts = data.get("scripts", {})
                    if isinstance(scripts, dict) and "test" in scripts:
                        return "npm test"
            except (json.JSONDecodeError, OSError):
                pass

        # 2. Rust projects
        if (root / "Cargo.toml").exists():
            return "cargo test"

        # 3. Python projects
        if (
            (root / "pyproject.toml").exists()
            or (root / "pytest.ini").exists()
            or (root / "setup.cfg").exists()
        ):
            return "pytest"

        # 4. Go projects
        if (root / "go.mod").exists():
            return "go test ./..."

        # 5. JVM: Gradle
        if (root / "gradlew").exists():
            return "./gradlew test"
        if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
            return "gradle test"

        # 6. JVM: Maven
        if (root / "mvnw").exists():
            return "./mvnw test"
        if (root / "pom.xml").exists():
            return "mvn test"

        # 7. .NET / C# / F#
        try:
            if any(root.glob("*.sln")) or any(root.glob("*.csproj")) or any(root.glob("*.fsproj")):
                return "dotnet test"
        except OSError:
            pass

        # 8. C / C++ CMake
        if (root / "CMakeLists.txt").exists():
            return "ctest"

        # 9. Makefile projects
        if (root / "Makefile").exists() or (root / "makefile").exists():
            return "make test"

        # 10. Elixir projects
        if (root / "mix.exs").exists():
            return "mix test"

        # 11. Shell test suites
        for test_dirname in ("tests", "test"):
            test_dir = root / test_dirname
            if test_dir.is_dir():
                try:
                    if any(test_dir.glob("*.sh")):
                        return f"bash {test_dirname}/*.sh"
                except OSError:
                    pass

        return None
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

    # Filter out exempt extensions and directory prefixes
    filtered_files: List[str] = []
    for f in modified_files:
        p = Path(f)
        if p.suffix.lower() in EXEMPT_EXTENSIONS:
            continue
        posix_str = p.as_posix()
        if posix_str.startswith(".git/") or posix_str.startswith(".system_generated/"):
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

    if modified_files is None:
        files = get_git_modified_files(cwd=root, branch=branch)
    else:
        files = list(modified_files)

    if pkg:
        prefix_matches = (f"packages/{pkg}/", f"apps/{pkg}/", f"{pkg}/")
        files = [f for f in files if any(f.startswith(p) for p in prefix_matches)]

    if not files:
        return ResolvedTests(
            runner_cmd="",
            test_files=[],
            source_files=[],
            tier=0,
            tier_name="empty",
            scope=mode,
            package=pkg,
            is_empty=True,
        )

    # Level 1: Native runner capabilities (Vitest / Jest)
    package_json = root / "package.json"
    has_vitest = False
    has_jest = False

    try:
        if list(root.glob("vitest.config.*")):
            has_vitest = True
        if list(root.glob("jest.config.*")):
            has_jest = True
        if package_json.is_file():
            data = json.loads(package_json.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            scripts = data.get("scripts", {})
            if not has_vitest and ("vitest" in deps or "vitest" in str(scripts.get("test", ""))):
                has_vitest = True
            if not has_jest and ("jest" in deps or "jest" in str(scripts.get("test", ""))):
                has_jest = True
    except Exception:
        pass

    if has_vitest:
        files_arg = " ".join(shlex.quote(f) for f in files)
        cmd = f"vitest related {files_arg} --run"
        return ResolvedTests(
            runner_cmd=cmd,
            test_files=[],
            source_files=files,
            tier=1,
            tier_name="native",
            scope=mode,
            package=pkg,
        )

    if has_jest:
        files_arg = " ".join(shlex.quote(f) for f in files)
        cmd = f"jest --findRelatedTests {files_arg} --passWithNoTests"
        return ResolvedTests(
            runner_cmd=cmd,
            test_files=[],
            source_files=files,
            tier=1,
            tier_name="native",
            scope=mode,
            package=pkg,
        )

    # Level 2: Structural heuristic mapping
    matched_test_files: Set[str] = set()
    for f in files:
        p = Path(f)
        if is_test_file_path(f):
            if (root / f).is_file():
                matched_test_files.add(f)
            continue

        stem = p.stem
        suffix = p.suffix
        candidates: List[Path] = []

        # Co-located
        candidates.append(p.parent / f"{stem}.test{suffix}")
        candidates.append(p.parent / f"{stem}.spec{suffix}")
        candidates.append(p.parent / f"test_{stem}{suffix}")
        candidates.append(p.parent / "__tests__" / f"{stem}.test{suffix}")

        # Mapped tests/
        if p.parts and p.parts[0] == "src":
            rel_dir = Path(*p.parts[1:-1]) if len(p.parts) > 2 else Path(".")
            candidates.append(Path("tests") / rel_dir / f"test_{stem}{suffix}")
            candidates.append(Path("tests") / rel_dir / f"{stem}.test{suffix}")
            candidates.append(Path("tests") / rel_dir / f"{stem}.spec{suffix}")
            candidates.append(Path("tests") / f"test_{stem}{suffix}")
        elif p.parts and p.parts[0] == "harness":
            candidates.append(Path("tests") / f"test_{stem}.py")
        else:
            candidates.append(Path("tests") / p.parent / f"test_{stem}{suffix}")
            candidates.append(Path("tests") / f"test_{stem}{suffix}")
            candidates.append(Path("tests") / f"{stem}.test{suffix}")

        for cand in candidates:
            if (root / cand).is_file():
                matched_test_files.add(cand.as_posix())

    if matched_test_files:
        sorted_tests = sorted(matched_test_files)
        quoted_tests = " ".join(shlex.quote(t) for t in sorted_tests)
        # Determine runner command
        if any(t.endswith(".py") for t in sorted_tests):
            if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists() or (root / "setup.cfg").exists():
                cmd = f"pytest {quoted_tests}"
            else:
                cmd = f"python3 -m unittest {quoted_tests}"
        elif any(t.endswith((".ts", ".tsx", ".js", ".jsx")) for t in sorted_tests):
            cmd = f"npm test -- {quoted_tests}"
        elif any(t.endswith(".rs") for t in sorted_tests):
            cmd = f"cargo test {quoted_tests}"
        elif any(t.endswith(".go") for t in sorted_tests):
            cmd = f"go test {quoted_tests}"
        else:
            cmd = f"python3 -m unittest {quoted_tests}"

        return ResolvedTests(
            runner_cmd=cmd,
            test_files=sorted_tests,
            source_files=files,
            tier=2,
            tier_name="structural",
            scope=mode,
            package=pkg,
        )

    # Level 3: Enclosing directory / package scope fallback
    # A. Monorepo package check
    for f in files:
        p = Path(f)
        for parent in [p] + list(p.parents):
            pkg_manifest = root / parent / "package.json"
            if pkg_manifest.is_file() and parent != Path("."):
                try:
                    data = json.loads(pkg_manifest.read_text(encoding="utf-8"))
                    detected_pkg = data.get("name") or parent.name
                    cmd = f"pnpm --filter {detected_pkg} test"
                    return ResolvedTests(
                        runner_cmd=cmd,
                        test_files=[],
                        source_files=files,
                        tier=3,
                        tier_name="fallback",
                        scope=mode,
                        package=detected_pkg,
                    )
                except Exception:
                    pass

    # B. Directory test search
    fallback_tests: Set[str] = set()
    for f in files:
        p = Path(f)
        dirs_to_check: List[Path] = []
        if p.parts and p.parts[0] == "src":
            rel_dir = Path(*p.parts[1:-1]) if len(p.parts) > 2 else Path(".")
            dirs_to_check.append(root / "tests" / rel_dir)
        dirs_to_check.append(root / p.parent)
        dirs_to_check.append(root / p.parent / "__tests__")

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
            cmd = f"npm test -- {quoted_fallback}"
        return ResolvedTests(
            runner_cmd=cmd,
            test_files=sorted_fallback,
            source_files=files,
            tier=3,
            tier_name="fallback",
            scope=mode,
            package=pkg,
        )

    # Default fallback to project runner
    runner = detect_project_test_runner(root) or "python3 -m unittest discover -s tests"
    return ResolvedTests(
        runner_cmd=runner,
        test_files=[],
        source_files=files,
        tier=3,
        tier_name="fallback",
        scope=mode,
        package=pkg,
    )


def is_non_interactive_context() -> bool:
    """Returns True if running in an agent, CI, or non-TTY context."""
    for env_key in ("CI", "CONTINUOUS_INTEGRATION", "ANTIGRAVITY", "GEMINI_CLI", "AGYIS_AGENT", "PSL_AGENT"):
        if os.environ.get(env_key, "").lower() in ("true", "1", "yes"):
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
) -> Tuple[str, Dict[str, str]]:
    """Guards test subshells by injecting CI=true and appending non-watch flags."""
    new_env = dict(env if env is not None else os.environ)
    new_env["CI"] = "true"
    new_env["NONINTERACTIVE"] = "true"

    clean_cmd = cmd.strip()
    # Vitest watch suppression
    if re.search(r"\bvitest\b", clean_cmd) and not re.search(r"(?:^|\s)(?:run|--run|--no-watch)(?:\s|$)", clean_cmd):
        clean_cmd += " --run"
    # Jest watch suppression
    elif re.search(r"\bjest\b", clean_cmd) and not re.search(r"(?:--watchAll=false|--no-watch|--watch=false|--watchAll=0)", clean_cmd):
        clean_cmd += " --watchAll=false"
    # Package manager test script watch suppression
    elif re.search(r"\b(?:pnpm|npm|yarn|bun)\b.*?\b(?:run\s+)?test(?::\w+)?\b", clean_cmd):
        if "--no-watch" not in clean_cmd and "--watch=false" not in clean_cmd:
            clean_cmd += " -- --no-watch" if " -- " not in clean_cmd else " --no-watch"

    return clean_cmd, new_env
