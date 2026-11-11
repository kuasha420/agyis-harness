# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Pure Classifiers, Predicates, and Constants for Completion Fence Hook (ADR-022).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile

from harness.discovery import detect_project_test_runner
from harness.trajectory.health import (
    ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR,
    ROLE_SWARM_ORCHESTRATOR,
    SOFT_EPOCH_STEP_ADVISORY,
    normalize_role_str,
)
from harness.utils.workspace import is_harness_workspace

# Declarative cleanroom specification extensions (only these qualify for pure spec_dirty)
DECLARATIVE_SPEC_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".markdown", ".json", ".yaml", ".yml", ".proto", ".schema", ".fbs", ".toml", ".txt",
})

TIER_RANKS: dict[str, int] = {"diff": 1, "affected": 2, "mutation": 2, "pkg": 3, "full": 4}

EXECUTIONER_HORIZON_STEPS: int = SOFT_EPOCH_STEP_ADVISORY
CODE_MUTATION_TOOLS: frozenset[str] = frozenset({"write_to_file", "replace_file_content", "edit_file"})

# Non-code files that do not trigger code dirty state
EXEMPT_FILENAMES: frozenset[str] = frozenset({
    ".gitignore", ".gitattributes", ".editorconfig", "package-lock.json",
    "uv.lock", "poetry.lock", "cargo.lock", "yarn.lock", "pnpm-lock.yaml", ".pnpm-lock.yaml",
})

EXEMPT_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".markdown", ".txt", ".rst", ".adoc", ".png", ".jpg", ".jpeg",
    ".gif", ".svg", ".ico", ".webp", ".bmp", ".tiff", ".lock",
})

CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".rs", ".go", ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
    ".java", ".kt", ".kts", ".scala", ".rb", ".php", ".sh", ".bash", ".zsh",
    ".swift", ".cs", ".sql", ".html", ".css", ".scss", ".sass", ".less", ".vue", ".svelte",
})

COMMAND_PREFIX: str = (
    r"(?:^|[;&|(]\s*)(?:\b(?:sudo|nohup|exec|time|command)\s+|\benv\s+)?(?:\b[A-Za-z_][A-Za-z0-9_]*=[^\s]+\s+)*\s*"
)

UNIVERSAL_TEST_RUNNER_PATTERNS: tuple[re.Pattern, ...] = (
    # 1. Python runners: pytest, unittest, harness.cli test, tox, nox
    re.compile(
        COMMAND_PREFIX
        + r"(?:pytest(?=[\s;&|)]|$)|python3?(?:\.\d+)?(?:\.exe)?\s+-m\s+(?:unittest(?=[\s;&|)]|$)|pytest(?=[\s;&|)]|$)|harness(?:\.cli)?\s+test\b)|tox\b|nox\b)"
    ),
    # 2. JS/TS/Node/Bun package manager invocations: pnpm, npm, yarn, bun test/t
    re.compile(
        COMMAND_PREFIX
        + r"(?:pnpm|npm|yarn|bun)\s+(?:(?:--filter|-C|--prefix)\s+[^\s]+\s+|(?:-w|-r|--workspace-root|--recursive)\s+)*(?:run\s+)?(?:test(?::\w+)?|t)\b"
    ),
    # 3. Direct test frameworks & npx/pnpx/bunx/yarn dlx runners: vitest, playwright, jest
    re.compile(
        COMMAND_PREFIX
        + r"(?:(?:npx|pnpx|bunx|yarn(?:\s+dlx)?|pnpm(?:\s+exec)?|bun)\s+)?(?:vitest(?!\s+init\b)(?:\s+(?:run|--run))?|playwright\s+test|jest)(?=[\s;&|)]|$)"
    ),
    # 4. Node native test runner (node --test)
    re.compile(COMMAND_PREFIX + r"node(?:\.exe)?\s+--test\b"),
    # 5. Monorepo runners: turborepo
    re.compile(COMMAND_PREFIX + r"turbo(?:\s+run)?\s+test\b"),
    # 6. Rust runners: cargo test, cargo nextest
    re.compile(COMMAND_PREFIX + r"cargo\s+(?:nextest(?:\s+run)?|test)\b"),
    # 7. Go runners: go test, gotestsum
    re.compile(COMMAND_PREFIX + r"(?:go\s+test\b|gotestsum\b)"),
    # 8. CMake / CTest
    re.compile(COMMAND_PREFIX + r"ctest(?=[\s;&|)]|$)"),
    # 9. Make / Ninja test targets
    re.compile(COMMAND_PREFIX + r"(?:make|ninja)\s+(?:test|check|verify)\b"),
    # 10. Java Maven: mvn, ./mvnw test / verify
    re.compile(COMMAND_PREFIX + r"(?:\./)?(?:mvn|mvnw)(?:\.cmd|\.sh)?\s+(?:test|verify)\b"),
    # 11. Java / Kotlin Gradle: gradle, ./gradlew test / check
    re.compile(COMMAND_PREFIX + r"(?:\./)?(?:gradle|gradlew)(?:\.bat)?\s+(?:test|check)\b"),
    # 12. .NET / C# / F#: dotnet test
    re.compile(COMMAND_PREFIX + r"dotnet(?:\.exe)?\s+test\b"),
    # 13. Elixir: mix test
    re.compile(COMMAND_PREFIX + r"mix\s+test\b"),
    # 14. Agyis / PSL project CLI
    re.compile(
        COMMAND_PREFIX
        + r"(?:(?:\./)?(?:agyis|psl)\s+test\b|python3?(?:\.\d+)?\s+-m\s+harness(?:\.cli)?\s+test\b)"
    ),
    # 14. Cleanroom REA & spec verification
    re.compile(
        COMMAND_PREFIX
        + r"(?:rea\s+(?:verify|verify-reconstruction|test|evaluate-coverage)\b|(?:\./)?agyis\s+verify\b)"
    ),
    # 15. Shell test suites
    re.compile(COMMAND_PREFIX + r"(?:(?:bash|sh)\s+|\./)tests?/[^\s]+\.sh\b"),
)

HARNESS_TEST_RUNNER_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(COMMAND_PREFIX + r"(?:(?:\./)?(?:agyis|psl)\s+test\b)"),
    re.compile(
        COMMAND_PREFIX
        + r"python3?(?:\.\d+)?\s+-m\s+(?:harness(?:\.cli)?\s+test|unittest(?=[\s;&|)]|$)|pytest(?=[\s;&|)]|$))"
    ),
    re.compile(COMMAND_PREFIX + r"pytest(?=[\s;&|)]|$)"),
    re.compile(
        COMMAND_PREFIX
        + r"(?:rea\s+(?:verify|verify-reconstruction|test|evaluate-coverage)\b|(?:\./)?agyis\s+verify\b)"
    ),
)

SHELL_MUTATION_PATTERNS = (
    re.compile(r"\bsed\s+(?:-[a-zA-Z]*i|--in-place)\b"),
    re.compile(r"\b(?:git\s+(?:apply|restore|checkout\s+--)|patch)\b"),
)


normalize_role = normalize_role_str


def classify_test_tier(command: str) -> str:
    """Classifies a recognized test command into its verification tier (RFC-051 Phase 2 R4)."""
    cmd_clean = command.strip()

    # 0. Diff-aware micro-mutation testing
    if "--mutation" in cmd_clean:  # agyis: no-mutant mutation string literal
        return "mutation"

    # 1. Tier 1A: Diff-targeted
    if re.search(r"(?:--diff\b|:(?:diff|related)\b|\bvitest\s+(?:run\s+)?related\b|--findRelatedTests\b|--picked\b)", cmd_clean):
        return "diff"

    # 2. Tier 1B: Affected blast-radius
    if re.search(r"(?:--affected\b|:affected\b|\bnx\s+affected\b)", cmd_clean):
        return "affected"
    # Targeted test file invocations (e.g. pytest tests/test_foo.py, vitest run src/a.test.ts)
    if not re.search(r"\bdiscover\b", cmd_clean):
        if re.search(r"\b(?:pytest|unittest|vitest|jest)\b.*\b(?:tests?/[^\s;&|]+\.py|\S+\.(?:test|spec)\.[a-zA-Z0-9]+)\b", cmd_clean):
            return "affected"
        if re.search(r"\bcargo\s+test\s+(?:--test\b|-t\b)", cmd_clean):
            return "affected"

    # 3. Tier 2A: Package-scoped
    if re.search(r"(?:--pkg\b|:pkg\b|--filter\s+[^\s]+\s+test\b|-p\s+[^\s]+\b|--package\b)", cmd_clean):
        return "pkg"

    # 4. Tier 2B: Full suite (default for unqualified test commands)
    return "full"


def is_commit_or_pr_command(command: str) -> bool:
    """Detects git commit, push, or gh PR creation commands."""
    clean = command.strip()
    if re.search(r"\b(?:git\s+commit|gh\s+pr\s+create|git\s+push)\b", clean):
        if "--help" in clean or "--dry-run" in clean:
            return False
        return True
    return False


def is_test_file(file_path: str | Path) -> bool:
    """
    Identifies test files subject to static AST smell linting.
    Supports Python (test_*.py, *_test.py) and JS/TS (*.test.[tj]s[x], *.spec.[tj]s[x]).
    """
    if not file_path:
        return False  # agyis: no-mutant empty path check
    name = Path(file_path).name.lower()
    if (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py"):
        return True
    return name.endswith((
        ".test.ts", ".spec.ts", ".test.js", ".spec.js",
        ".test.tsx", ".spec.tsx", ".test.jsx", ".spec.jsx",
        ".test.mjs", ".spec.mjs", ".test.cjs", ".spec.cjs",
    ))


def is_mutation_test_command(command: str) -> bool:
    """Detects commands running diff-aware micro-mutation testing."""
    if not command or not command.strip():  # agyis: no-mutant empty command check
        return False  # agyis: no-mutant empty command check
    clean = command.strip()
    return bool(re.search(r"(?:^|[\s=])--mutation\b", clean) and re.search(r"\b(?:test|harness|agyis|psl|micro_probe)\b", clean))  # agyis: no-mutant regex matching


def is_code_file(path_str: str) -> bool:
    """
    Determines if a file path represents code that requires verification.
    Exempts documentation, asset/image files, lockfiles, and git configs.
    """
    if path_str == "<shell-mutation>":
        return True
    p = Path(path_str)
    name = p.name.lower()
    suffix = p.suffix.lower()

    if name in EXEMPT_FILENAMES:
        return False
    if suffix in EXEMPT_EXTENSIONS or name.endswith(".lock"):
        return False
    return suffix in CODE_EXTENSIONS


def is_cleanroom_contract_file(path_str: str) -> bool:
    """
    Determines if a file path represents a cleanroom contract file
    (in docs/specs/** or .agents/ledger/**) that requires verification,
    overriding default .md and .json exemptions.
    """
    if not path_str or not isinstance(path_str, str):
        return False
    norm = path_str.replace("\\", "/").strip().lower()
    if norm.startswith("./"):
        norm = norm[2:]

    if norm.startswith("docs/specs/") or "/docs/specs/" in norm:
        return True
    if norm.startswith(".agents/ledger/") or "/.agents/ledger/" in norm:
        return True

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


def check_has_mutable_code(files: list[str], cwd: Path | str | None = None) -> bool:
    """
    Checks whether modified code files contain any mutable functions or logic.
    If only comments, arid lines, or top-level constants were modified, returns False
    satisfying the Empty Diff Invariant without requiring micro-mutation execution.
    """
    if not files:
        return False  # agyis: no-mutant empty files check
    for f in files:
        if f == "<shell-mutation>":  # agyis: no-mutant shell mutation marker
            return True
        if is_ephemeral_scratch_path(f, cwd=cwd):
            continue
        if is_code_file(f) and not is_test_file(f):  # agyis: no-mutant code filter check
            f_path = Path(f)
            if not f_path.is_absolute() and cwd:  # agyis: no-mutant path resolution
                f_path = Path(cwd) / f_path
            if f_path.is_file():
                try:
                    content = f_path.read_text(encoding="utf-8")
                    if str(f).endswith(".py"):
                        from harness.mutation.micro_probe import generate_function_mutants
                        if generate_function_mutants(content):
                            return True
                    else:
                        from harness.mutation.micro_probe import mutate_token_source
                        mutated, op = mutate_token_source(content)
                        if op:
                            return True
                except Exception:
                    return True
            else:
                return True
    return False


def extract_exit_code(payload: dict) -> int | None:
    """
    Robustly extracts exit code from direct payload (exitCode, exit_code)
    and nested structures (toolResponse, result).
    Returns integer exit code, or None if no exit code could be determined.
    """
    if not isinstance(payload, dict):
        return None

    # 1. Direct fields
    for key in ("exitCode", "exit_code", "returncode"):
        val = payload.get(key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass

    # 2. Check nested structures: toolResponse, result, response, output, toolOutput, content, stdout
    for key in ("toolResponse", "result", "response", "output", "toolOutput", "content", "stdout"):
        val = payload.get(key)
        if isinstance(val, dict):
            # Direct check in dict
            for sub_key in ("exitCode", "exit_code", "returncode", "code"):
                sub_val = val.get(sub_key)
                if sub_val is not None:
                    try:
                        return int(sub_val)
                    except (ValueError, TypeError):
                        pass
            # Check nested sub-dict inside val
            for sub_dict_key in ("result", "toolResponse", "response", "data"):
                sub_dict = val.get(sub_dict_key)
                if isinstance(sub_dict, dict):
                    for sub_key in ("exitCode", "exit_code", "returncode", "code"):
                        sub_val = sub_dict.get(sub_key)
                        if sub_val is not None:
                            try:
                                return int(sub_val)
                            except (ValueError, TypeError):
                                pass
            # Check string fields inside dict (e.g., output, content, stdout)
            for text_key in ("output", "content", "stdout"):
                text_val = val.get(text_key)
                if isinstance(text_val, str):
                    m = re.search(r"(?:failed with exit code|exited with code)\s*[:=]?\s*(\d+)", text_val, re.I)
                    if m:
                        try:
                            return int(m.group(1))
                        except (ValueError, TypeError):
                            pass
        elif isinstance(val, str):
            # String JSON parsing attempt
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    sub_code = extract_exit_code(parsed)
                    if sub_code is not None:
                        return sub_code
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
            # Regex match on string content
            m = re.search(r"(?:failed with exit code|exited with code)\s*[:=]?\s*(\d+)", val, re.I)
            if m:
                try:
                    return int(m.group(1))
                except (ValueError, TypeError):
                    pass

    return None


def is_test_command(command: str, cwd: Path | str | None = None) -> bool:
    """
    Checks whether a command line executes a recognized test runner.
    If cwd is specified and is identified as the harness repository,
    strictly enforces harness test commands.
    Otherwise:
      1. Dynamically queries detect_project_test_runner(cwd) for project-native match.
      2. Evaluates against expanded UNIVERSAL_TEST_RUNNER_PATTERNS polyglot regex union.
    """
    if not command or not command.strip():
        return False
    cmd_clean = command.strip()

    if re.search(r"(?:^|\s)(?:--help|-h|--version)\b", cmd_clean):
        return False
    if re.search(r"(?:^|\s)-V\b", cmd_clean) and not re.search(r"\bctest\b", cmd_clean):
        return False

    if cwd is not None and is_harness_workspace(cwd):
        return any(pat.search(cmd_clean) is not None for pat in HARNESS_TEST_RUNNER_PATTERNS)

    if cwd is not None:
        detected = detect_project_test_runner(cwd)
        if detected:
            escaped = re.escape(detected).replace(r"\*", r"[^\s]+")
            det_pat = re.compile(COMMAND_PREFIX + escaped + r"\b")
            if det_pat.search(cmd_clean) is not None:
                return True

    return any(pat.search(cmd_clean) is not None for pat in UNIVERSAL_TEST_RUNNER_PATTERNS)


def is_manifest_verified(cwd: Path | str | None = None) -> bool:
    """
    Validates cleanroom obligation ledger or manifest against formal schema:
    1. If .agents/ledger/obligation_ledger.json exists, enforces strict REA 6.8.0
       schema via validate_obligation_ledger() and verifies all obligations are satisfied.
    2. Fallback: validates .agents/ledger/manifest.json against REA 6.8.0 or legacy schema.
    """
    effective_cwd = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    ledger_path = effective_cwd / ".agents" / "ledger" / "obligation_ledger.json"
    manifest_path = effective_cwd / ".agents" / "ledger" / "manifest.json"

    # 1. Prefer typed obligation_ledger.json adhering to REA 6.8.0
    if ledger_path.is_file():
        try:
            from harness.cleanroom.obligation import validate_obligation_ledger
            valid, errors = validate_obligation_ledger(ledger_path)
            if not valid:
                return False
            data = json.loads(ledger_path.read_text(encoding="utf-8"))
            reviewed = data.get("reviewed_obligations", [])
            for ob in reviewed:
                if ob.get("disposition") not in ("satisfied", "verified", "waived"):
                    return False
            return True
        except Exception:
            return False

    # 2. Check manifest.json
    if not manifest_path.is_file():
        return False

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False

        # If manifest.json is in REA 6.8.0 typed format:
        if "evidence_bundle" in data and "reviewed_obligations" in data:
            from harness.cleanroom.obligation import validate_obligation_ledger
            valid, errors = validate_obligation_ledger(manifest_path)
            if not valid:
                return False
            reviewed = data.get("reviewed_obligations", [])
            for ob in reviewed:
                if ob.get("disposition") not in ("satisfied", "verified", "waived"):
                    return False
            return True

        # Legacy manifest validation:
        if data.get("status") != "verified":
            return False

        evidence_hash = data.get("evidence_hash")
        if not isinstance(evidence_hash, str) or not re.match(r"^[a-f0-9]{64}$", evidence_hash):
            return False

        obligations = data.get("obligations")
        if not isinstance(obligations, list) or len(obligations) == 0:
            return False

        for ob in obligations:
            if not isinstance(ob, dict):
                return False
            if ob.get("status") != "satisfied":
                return False

        return True
    except (json.JSONDecodeError, OSError):
        return False
