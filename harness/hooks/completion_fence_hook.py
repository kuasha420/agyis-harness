#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness: Deterministic Stop-Hook Verification Fence (ADR-022)

Intercepts agent completion (`Stop` event) to ensure that code modifications
have been verified by running tests before allowing the agent to exit.
Intercepts file modifications in `PreToolUse` to mark session state dirty.
Features an anti-deadlock safety valve tripping after 2 blocks.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from harness.discovery import detect_project_test_runner, get_git_modified_files
from harness.utils.state import get_state_dir
from harness.utils.workspace import is_harness_workspace

__all__ = [
    "EXEMPT_EXTENSIONS",
    "EXEMPT_FILENAMES",
    "CODE_EXTENSIONS",
    "DECLARATIVE_SPEC_EXTENSIONS",
    "COMMAND_PREFIX",
    "UNIVERSAL_TEST_RUNNER_PATTERNS",
    "HARNESS_TEST_RUNNER_PATTERNS",
    "SHELL_MUTATION_PATTERNS",
    "get_state_file",
    "get_brain_dir",
    "is_code_file",
    "is_cleanroom_contract_file",
    "is_ephemeral_scratch_path",
    "is_test_command",
    "is_manifest_verified",
    "extract_exit_code",
    "load_state",
    "save_state",
    "record_edit",
    "record_verification",
    "clear_spec_dirty",
    "reset_state",
    "evaluate_stop",
    "check_command_verification",
    "check_background_task_detachment",
    "sync_background_tasks",
    "check_shell_command_mutation",
    "handle_post_tool_use",
    "classify_test_tier",
    "is_commit_or_pr_command",
    "is_test_file",
    "is_mutation_test_command",
    "check_has_mutable_code",
    "TIER_RANKS",
    "ROLE_DEEP_EXECUTION",
    "ROLE_FLIGHT_DIRECTOR",
    "ROLE_FORENSIC_AUDITOR",
    "EXECUTIONER_HORIZON_STEPS",
    "CODE_MUTATION_TOOLS",
    "normalize_role",
    "check_pre_tool_use",
    "check_completion_fence_pre_tool",
    "main",
]



def get_state_file(conv_id: str = "default", state_dir: Path | None = None) -> Path:
    """Returns the state file path for a specific conversation."""
    target_dir = state_dir or get_state_dir()
    safe_conv_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", conv_id)
    return target_dir / f"verification_state_{safe_conv_id}.json"


# Declarative cleanroom specification extensions (only these qualify for pure spec_dirty)
DECLARATIVE_SPEC_EXTENSIONS: frozenset[str] = frozenset({
    ".md",
    ".markdown",
    ".json",
    ".yaml",
    ".yml",
    ".proto",
    ".schema",
    ".fbs",
    ".toml",
    ".txt",
})


TIER_RANKS: dict[str, int] = {
    "diff": 1,
    "affected": 2,
    "mutation": 2,
    "pkg": 3,
    "full": 4,
}

ROLE_FLIGHT_DIRECTOR: str = "flight_director"
ROLE_SWARM_ORCHESTRATOR: str = "swarm_orchestrator"
ROLE_DEEP_EXECUTION: str = "deep_execution"
ROLE_FORENSIC_AUDITOR: str = "forensic_auditor"

EXECUTIONER_HORIZON_STEPS: int = 50
CODE_MUTATION_TOOLS: frozenset[str] = frozenset({
    "write_to_file",
    "replace_file_content",
    "edit_file",
})


def normalize_role(val: str | None) -> str | None:
    """Normalizes an agent role identifier to the canonical taxonomy."""
    if not val or not isinstance(val, str):
        return None
    norm = val.strip().lower().replace("-", "_")
    if norm in (
        ROLE_DEEP_EXECUTION,
        "agyis_builder",
        "agyis_custodian",
        "agyis_architect",
        "architect",
        "implementer",
        "master_implementer",
        "executioner",
        "builder",
        "custodian",
        "harness_custodian",
        "git_custodian",
        "harness_builder",
        "deep_coding",
        "deep_coder",
        "coder",
        "execution",
        "monolithic_swe_pairing",
        "monolithic",
        "monolith",
        "swe_pairing",
        "pairing",
        "swe",
    ):
        return ROLE_DEEP_EXECUTION
    if norm in (
        ROLE_FORENSIC_AUDITOR,
        "agyis_reviewer",
        "agyis_auditor",
        "agyis_investigator",
        "reviewer",
        "harness_reviewer",
        "harness_auditor",
        "investigator",
        "detective",
        "forensic",
        "verifier",
        "auditor",
        "hammer",
        "forensics",
        "inspector",
    ):
        return ROLE_FORENSIC_AUDITOR
    if norm in (
        ROLE_SWARM_ORCHESTRATOR,
        "orchestrator",
        "swarm",
        "mesh_coordinator",
        "mesh",
    ):
        return ROLE_SWARM_ORCHESTRATOR
    if norm in (
        ROLE_FLIGHT_DIRECTOR,
        "agyis_coordinator",
        "agyis_planner",
        "planner",
        "coordinator",
        "cockpit_director",
        "flight_director",
        "flight",
        "director",
        "cockpit",
        "root",
    ):
        return ROLE_FLIGHT_DIRECTOR

    if "executioner" in norm or "builder" in norm or "custodian" in norm or "deep_execution" in norm or "deep_coding" in norm:
        return ROLE_DEEP_EXECUTION
    if "hammer" in norm or "auditor" in norm or "forensic" in norm or "reviewer" in norm:
        return ROLE_FORENSIC_AUDITOR
    if "orchestrator" in norm or "swarm" in norm:
        return ROLE_SWARM_ORCHESTRATOR
    if "flight" in norm or "cockpit" in norm or "planner" in norm:
        return ROLE_FLIGHT_DIRECTOR
    return norm


def check_pre_tool_use(
    tool_name: str,
    tool_args: dict,
    payload: dict | None = None,
    step_count: int | None = None,
    role: str | None = None,
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
) -> dict:
    """
    Evaluates PreToolUse constraints including the Hard Horizon Fence (Issue #86).
    When role is ROLE_DEEP_EXECUTION and step_count >= 50:
    Blocks code mutation tools (write_to_file, replace_file_content, edit_file).
    Permits verification grace (run_command test commands) and read-only tools.
    Exempts non-executioner roles (flight_director, forensic_auditor).
    """
    effective_step = step_count
    if effective_step is None and payload:
        for k in (
            "step_count",
            "stepCount",
            "step",
            "current_step",
            "currentStep",
            "step_idx",
            "stepIdx",
            "initialNumSteps",
            "initial_num_steps",
            "invocationNum",
            "invocation_num",
        ):
            if k in payload:
                v = payload[k]
                if isinstance(v, (int, float)):
                    effective_step = int(v)
                    break
                elif isinstance(v, str) and v.strip().isdigit():
                    effective_step = int(v.strip())
                    break

    effective_role = role
    if effective_role is None and payload:
        for rk in ("role", "agent_role", "subagent_role", "archetype", "agentType", "agent_type"):
            rv = payload.get(rk)
            if isinstance(rv, str) and rv.strip():
                effective_role = rv.strip()
                break
    if not effective_role:
        effective_role = os.environ.get("AGYIS_ROLE") or os.environ.get("PSL_AGENT_ROLE")

    norm_role = normalize_role(effective_role)

    # Exemption: Non-executioner roles are strictly exempt
    if norm_role and norm_role != ROLE_DEEP_EXECUTION:
        return {"decision": "allow"}

    # Hard Horizon Fence at step >= 50
    if norm_role == ROLE_DEEP_EXECUTION and effective_step is not None and effective_step >= EXECUTIONER_HORIZON_STEPS:
        if tool_name in CODE_MUTATION_TOOLS:
            return {
                "decision": "deny",
                "reason": (
                    "HARD HORIZON FENCE TRIGGERED (20-Step Remedy Budget Exhausted / 50 Steps Reached). "
                    "Further code mutation is strictly blocked to prevent cognitive cliff collapse. "
                    "All local modifications are preserved intact on disk. You are granted 1 Verification Grace turn to run tests. "
                    "You MUST immediately message the parent agent via send_message with your stage transition payload and STOP calling tools."
                ),
            }

    return {"decision": "allow"}


check_completion_fence_pre_tool = check_pre_tool_use



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
    p = Path(file_path)
    name = p.name.lower()
    if (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py"):
        return True
    for ext in (
        ".test.ts",
        ".spec.ts",
        ".test.js",
        ".spec.js",
        ".test.tsx",
        ".spec.tsx",
        ".test.jsx",
        ".spec.jsx",
        ".test.mjs",
        ".spec.mjs",
        ".test.cjs",
        ".spec.cjs",
    ):
        if name.endswith(ext):
            return True
    return False


def is_mutation_test_command(command: str) -> bool:
    """Detects commands running diff-aware micro-mutation testing."""
    if not command or not command.strip():  # agyis: no-mutant empty command check
        return False  # agyis: no-mutant empty command check
    clean = command.strip()
    return bool(re.search(r"(?:^|[\s=])--mutation\b", clean) and re.search(r"\b(?:test|harness|agyis|psl|micro_probe)\b", clean))  # agyis: no-mutant regex matching


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



# Non-code files that do not trigger code dirty state
EXEMPT_FILENAMES: frozenset[str] = frozenset({
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    "package-lock.json",
    "uv.lock",
    "poetry.lock",
    "cargo.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".pnpm-lock.yaml",
})

EXEMPT_EXTENSIONS: frozenset[str] = frozenset({
    ".md",
    ".markdown",
    ".txt",
    ".rst",
    ".adoc",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".bmp",
    ".tiff",
    ".lock",
})

CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".rs",
    ".go",
    ".c",
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hpp",
    ".java",
    ".kt",
    ".kts",
    ".scala",
    ".rb",
    ".php",
    ".sh",
    ".bash",
    ".zsh",
    ".swift",
    ".cs",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".svelte",
})


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

    # Rule 1: Antigravity ephemeral scratch transcripts/scripts
    if ".gemini/antigravity/brain" in norm and "/scratch/" in norm:
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


def load_state(conv_id: str = "default", state_dir: Path | None = None) -> dict:
    """Loads state for conversation or returns clean baseline."""
    state_file = get_state_file(conv_id, state_dir)
    default_state = {
        "conversation_id": conv_id,
        "code_dirty": False,
        "spec_dirty": False,
        "handoff_modified": False,
        "verified_tier": None,
        "mutation_verified": False,  # agyis: no-mutant default false load
        "surviving_mutants": [],
        "last_mutation_timestamp": None,
        "session_modified_files": [],
        "turn_mutated": False,
        "turn_modified_files": [],
        "active_turn_id": None,
        "last_modified_files": [],
        "block_count": 0,
        "gate2_block_count": 0,
        "last_verified_at": None,
        "last_dirtied_at": None,
        "cwd": None,
        "pending_background_tests": {},
        "processed_task_ids": [],
    }
    if state_file.exists():
        try:
            content = state_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                return {
                    "conversation_id": str(data.get("conversation_id", conv_id)),
                    "code_dirty": bool(data.get("code_dirty", False)),
                    "spec_dirty": bool(data.get("spec_dirty", False)),
                    "handoff_modified": bool(data.get("handoff_modified", False)),
                    "verified_tier": data.get("verified_tier"),
                    "mutation_verified": bool(data.get("mutation_verified", False)),  # agyis: no-mutant load default false
                    "surviving_mutants": list(data.get("surviving_mutants", [])),
                    "last_mutation_timestamp": data.get("last_mutation_timestamp"),
                    "session_modified_files": list(data.get("session_modified_files", [])),
                    "turn_mutated": bool(data.get("turn_mutated", False)),
                    "turn_modified_files": list(data.get("turn_modified_files", [])),
                    "active_turn_id": data.get("active_turn_id"),
                    "last_modified_files": list(data.get("last_modified_files", [])),
                    "block_count": int(data.get("block_count", 0)),
                    "gate2_block_count": int(data.get("gate2_block_count", 0)),
                    "last_verified_at": data.get("last_verified_at"),
                    "last_dirtied_at": data.get("last_dirtied_at"),
                    "cwd": data.get("cwd"),
                    "pending_background_tests": dict(data.get("pending_background_tests", {})),
                    "processed_task_ids": list(data.get("processed_task_ids", [])),
                }
        except (json.JSONDecodeError, OSError, ValueError):
            return default_state
    return default_state


def save_state(state: dict, conv_id: str = "default", state_dir: Path | None = None) -> None:
    """Saves state atomically to disk."""
    target_dir = state_dir or get_state_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    state_file = get_state_file(conv_id, target_dir)
    safe_conv_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", conv_id)
    tmp_file = target_dir / f".tmp_verification_state_{safe_conv_id}_{os.getpid()}.json"
    try:
        tmp_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp_file.replace(state_file)
    except OSError:
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def record_edit(
    file_path: str,
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
    turn_id: str | None = None,
) -> dict:
    """
    Records a file edit. Phase-aware decoupling (ADR-028):
    - Cleanroom contracts (docs/specs/**, .agents/ledger/**) with declarative extensions
      (.md, .json, .yaml, etc.) set spec_dirty = True (pure spec dirty).
    - Non-declarative code files in specs (.py, .ts, .rs, etc.) trigger code_dirty = True
      and spec_dirty = True (DEF-01 code-in-specs dual dirty guard).
    - Code files outside specs set code_dirty = True.
    - Ephemeral scratch paths (.rea/**, decompiled/**, artifacts/rea/**, /scratch/)
      are filtered out without modifying state.
    """
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    effective_cwd = cwd if cwd is not None else state.get("cwd")

    if is_ephemeral_scratch_path(file_path, cwd=effective_cwd):
        return state

    if turn_id is not None:
        current_turn = state.get("active_turn_id")
        if current_turn is not None and turn_id != current_turn:
            state["active_turn_id"] = turn_id
            state["turn_mutated"] = False
            state["turn_modified_files"] = []
            state["handoff_modified"] = False
        elif current_turn is None:
            state["active_turn_id"] = turn_id

    p = Path(file_path)
    suffix = p.suffix.lower()
    p_name = p.name.lower()
    p_str = p.as_posix().lower()

    is_handoff = (p_name == "handoff.md" or (p_name.startswith("handoff") and p_name.endswith(".md")))
    if is_handoff:
        state["handoff_modified"] = True

    dirtied = False
    if is_cleanroom_contract_file(file_path):
        if suffix in DECLARATIVE_SPEC_EXTENSIONS:
            state["spec_dirty"] = True
            state["turn_mutated"] = True
            dirtied = True
        else:
            # Code-in-Specs guard (DEF-01): non-declarative code in specs triggers dual dirty state
            state["code_dirty"] = True
            state["spec_dirty"] = True
            state["turn_mutated"] = True
            dirtied = True
    elif is_code_file(file_path):
        state["code_dirty"] = True
        state["turn_mutated"] = True
        dirtied = True

    if dirtied:
        state["block_count"] = 0
        state["last_dirtied_at"] = datetime.now(timezone.utc).isoformat()
        state["verified_tier"] = None
        is_code = bool(is_code_file(file_path) or file_path == "<shell-mutation>" or (is_cleanroom_contract_file(file_path) and suffix not in DECLARATIVE_SPEC_EXTENSIONS))  # agyis: no-mutant code file check
        if is_code:
            state["mutation_verified"] = False  # agyis: no-mutant invalidate mutation
            state["surviving_mutants"] = []
        modified = state.get("last_modified_files", [])
        if file_path not in modified:
            modified.append(file_path)
        state["last_modified_files"] = modified
        turn_mod = state.get("turn_modified_files", [])
        if file_path not in turn_mod:
            turn_mod.append(file_path)
        state["turn_modified_files"] = turn_mod
        sess_mod = state.get("session_modified_files", [])
        if file_path not in sess_mod and (is_code_file(file_path) or file_path == "<shell-mutation>"):
            sess_mod.append(file_path)
        state["session_modified_files"] = sess_mod
        if cwd is not None:
            state["cwd"] = str(cwd)
        save_state(state, conv_id=conv_id, state_dir=state_dir)
    elif is_handoff:
        modified = state.get("last_modified_files", [])
        if file_path not in modified:
            modified.append(file_path)
        state["last_modified_files"] = modified
        if cwd is not None:
            state["cwd"] = str(cwd)
        save_state(state, conv_id=conv_id, state_dir=state_dir)
    return state


def record_verification(
    success: bool = True,
    tier: str = "full",
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> dict:
    """
    Records test verification results with verification tier tracking (RFC-051 Phase 2 R4).
    If successful, clears code_dirty, spec_dirty, turn_mutated, resets last_modified_files,
    records verified_tier, and clears session_modified_files if tier in ('pkg', 'full').
    """
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    if success:
        state["code_dirty"] = False
        state["spec_dirty"] = False
        state["turn_mutated"] = False
        state["turn_modified_files"] = []
        state["last_modified_files"] = []
        state["block_count"] = 0
        state["last_verified_at"] = datetime.now(timezone.utc).isoformat()
        if tier == "mutation":  # agyis: no-mutant tier string check
            state["mutation_verified"] = True
            state["surviving_mutants"] = []
            state["last_mutation_timestamp"] = datetime.now(timezone.utc).isoformat()
            existing_tier = state.get("verified_tier")
            if TIER_RANKS.get(existing_tier or "", 0) < TIER_RANKS.get("mutation", 0):  # agyis: no-mutant semantically equivalent rank update
                state["verified_tier"] = "mutation"
        else:
            state["verified_tier"] = tier
        if state.get("verified_tier") in ("pkg", "full") and state.get("mutation_verified", False):  # agyis: no-mutant mutation_verified requirement
            state["session_modified_files"] = []
        save_state(state, conv_id=conv_id, state_dir=state_dir)
    else:
        state["code_dirty"] = True
        state["verified_tier"] = None
        if tier == "mutation":  # agyis: no-mutant failure mutation tier check
            state["mutation_verified"] = False  # agyis: no-mutant failure mutation invalidation
        save_state(state, conv_id=conv_id, state_dir=state_dir)
    return state


def clear_spec_dirty(
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> dict:
    """
    Clears spec_dirty state following cleanroom verification.
    If code_dirty is False, removes cleanroom spec files from last_modified_files and resets block_count.
    """
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    state["spec_dirty"] = False
    if not state.get("code_dirty", False):
        state["last_modified_files"] = [
            f for f in state.get("last_modified_files", [])
            if not is_cleanroom_contract_file(f)
        ]
        state["turn_modified_files"] = [
            f for f in state.get("turn_modified_files", [])
            if not is_cleanroom_contract_file(f)
        ]
        if not state["turn_modified_files"]:
            state["turn_mutated"] = False
        state["block_count"] = 0
    state["last_verified_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state, conv_id=conv_id, state_dir=state_dir)
    return state


def reset_state(
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> dict:
    """Resets the verification state to clean baseline."""
    state = {
        "conversation_id": conv_id,
        "code_dirty": False,
        "spec_dirty": False,
        "handoff_modified": False,
        "verified_tier": None,
        "mutation_verified": False,  # agyis: no-mutant clean state default
        "surviving_mutants": [],
        "last_mutation_timestamp": None,
        "session_modified_files": [],
        "turn_mutated": False,
        "turn_modified_files": [],
        "active_turn_id": None,
        "last_modified_files": [],
        "block_count": 0,
        "gate2_block_count": 0,
        "last_verified_at": None,
        "last_dirtied_at": None,
        "cwd": None,
        "pending_background_tests": {},
        "processed_task_ids": [],
    }
    save_state(state, conv_id=conv_id, state_dir=state_dir)
    return state


def is_manifest_verified(cwd: Path | str | None = None) -> bool:
    """
    Validates .agents/ledger/manifest.json against the formal cleanroom schema:
    1. Valid JSON object.
    2. 'status': 'verified'.
    3. 'evidence_hash': 64-char lowercase hexadecimal string.
    4. 'obligations': non-empty array where every obligation has 'status': 'satisfied'.
    """
    effective_cwd = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    manifest_path = effective_cwd / ".agents" / "ledger" / "manifest.json"
    if not manifest_path.is_file():
        return False

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False

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


def handle_post_tool_use(
    tool_name: str,
    args: dict,
    result: dict,
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> None:
    """
    PostToolUse handler: intercepts MCP tools (verify_reconstruction,
    evaluate_reconstruction_coverage) and clears spec_dirty state upon success.
    """
    if tool_name == "call_mcp_tool":
        inner_tool = args.get("ToolName", "")
        if inner_tool in ("verify_reconstruction", "evaluate_reconstruction_coverage"):
            status = result.get("status") if isinstance(result, dict) else None
            is_err = result.get("isError") or result.get("is_error") if isinstance(result, dict) else False
            if status != "error" and not is_err:
                clear_spec_dirty(conv_id=conv_id, state_dir=state_dir)
    elif "verify_reconstruction" in tool_name or "evaluate_reconstruction_coverage" in tool_name:
        status = result.get("status") if isinstance(result, dict) else None
        is_err = result.get("isError") or result.get("is_error") if isinstance(result, dict) else False
        if status != "error" and not is_err:
            clear_spec_dirty(conv_id=conv_id, state_dir=state_dir)
    elif tool_name in ("run_command", "execute_command", "bash"):
        cmd = args.get("CommandLine") or args.get("command") or ""
        exit_code = result.get("exit_code") or result.get("returncode")
        if exit_code is None:
            is_err = result.get("isError") or result.get("is_error") or False
            status = result.get("status")
            if status != "error" and not is_err:
                exit_code = 0
        if exit_code == 0 and cmd:
            cmd_lower = cmd.lower()
            if any(
                p in cmd_lower
                for p in ("verify --spec", "verify-reconstruction", "agyis verify", "harness.cli verify")
            ):
                clear_spec_dirty(conv_id=conv_id, state_dir=state_dir)


def get_brain_dir(
    conv_id: str,
    payload: Optional[dict] = None,
    brain_dir: Optional[Path | str] = None,
) -> Optional[Path]:
    """
    Resolves the Antigravity conversation brain directory:
    1. Explicit brain_dir argument / override.
    2. payload['brain_dir'], payload['brainDirectory'], payload['artifactDirectoryPath'] or payload['transcriptPath'].
    3. Standard user location: ~/.gemini/antigravity/brain/<conv_id>.
    """
    if brain_dir:
        p = Path(brain_dir).resolve()
        if p.is_dir():
            return p

    if payload:
        for k in ("brain_dir", "brainDirectory", "brainPath"):
            val = payload.get(k)
            if val:
                p = Path(val).resolve()
                if p.is_dir():
                    return p
        artifact_path = payload.get("artifactDirectoryPath")
        if artifact_path:
            p = Path(artifact_path).resolve()
            if p.is_dir():
                return p
        transcript_path = payload.get("transcriptPath")
        if transcript_path:
            p = Path(transcript_path).resolve().parent.parent
            if p.is_dir():
                return p

    # Standard Antigravity user location
    candidate = Path.home() / ".gemini" / "antigravity" / "brain" / conv_id
    if candidate.is_dir():
        return candidate

    return None


def check_background_task_detachment(
    tool_name: str,
    tool_args: dict,
    raw_output: str,
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
) -> Optional[dict]:
    """
    Detects if a run_command tool execution was detached as a background task.
    If the command is a recognized test runner, registers it in pending_background_tests.
    """
    if tool_name not in ("run_command", "execute_command", "bash"):
        return None

    if "Tool is running as a background task with task id:" not in raw_output:
        return None

    m_task = re.search(r"task id:\s*([^\s\n\r]+)", raw_output)
    if not m_task:
        return None
    task_id = m_task.group(1).strip()

    cmd = tool_args.get("CommandLine") or tool_args.get("command") or ""
    effective_cwd = cwd or tool_args.get("Cwd")
    if not cmd or not is_test_command(cmd, cwd=effective_cwd):
        return None

    m_log = re.search(r"Task logs are available at:\s*(?:file://)?([^\s\n\r]+)", raw_output)
    log_path = m_log.group(1).strip() if m_log else None

    task_tier = classify_test_tier(cmd)
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    pending = state.setdefault("pending_background_tests", {})
    pending[task_id] = {
        "command": cmd,
        "tier": task_tier,
        "cwd": str(effective_cwd) if effective_cwd else None,
        "log_path": log_path,
        "launched_at": datetime.now(timezone.utc).isoformat(),
    }
    save_state(state, conv_id=conv_id, state_dir=state_dir)
    return pending[task_id]


def sync_background_tasks(
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
    brain_dir: Path | str | None = None,
    payload: Optional[dict] = None,
) -> bool:
    """
    Scans background task completion messages in .system_generated/messages/
    and reconciles completed test runner tasks against the dirty state.

    Returns True if an exit code 0 test runner completion cleared code_dirty.
    """
    state = load_state(conv_id=conv_id, state_dir=state_dir)

    # Fast exit if clean and no pending tasks
    if not state.get("code_dirty") and not state.get("pending_background_tests"):
        return False

    target_brain = get_brain_dir(conv_id, payload=payload, brain_dir=brain_dir)
    if not target_brain:
        return False

    messages_dir = target_brain / ".system_generated" / "messages"
    if not messages_dir.is_dir():
        return False

    pending_tests = state.get("pending_background_tests", {})
    processed_ids = set(state.get("processed_task_ids", []))
    last_dirtied_at = state.get("last_dirtied_at")

    cleared_state = False

    try:
        msg_files = list(messages_dir.glob("*.json"))
    except OSError:
        return False

    parsed_messages = []
    for msg_file in msg_files:
        try:
            data = json.loads(msg_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            ts_str = data.get("timestamp")
            sort_val = 0.0
            if ts_str and isinstance(ts_str, str):
                try:
                    clean_ts = ts_str.replace("Z", "+00:00")
                    sort_val = datetime.fromisoformat(clean_ts).timestamp()
                except (ValueError, TypeError):
                    sort_val = 0.0
            if sort_val == 0.0:
                try:
                    sort_val = msg_file.stat().st_mtime
                except OSError:
                    sort_val = 0.0
            parsed_messages.append((sort_val, msg_file, data))
        except (OSError, json.JSONDecodeError):
            continue

    parsed_messages.sort(key=lambda x: x[0])

    for _, msg_file, data in parsed_messages:
        try:
            sender = str(data.get("sender", ""))
            content = str(data.get("content", ""))

            if not ("/task-" in sender or "task-" in sender or "The command exited with code" in content or "failed with exit code" in content):
                continue

            task_id = sender.split("/")[-1] if "/task-" in sender else None
            if not task_id:
                m_id = re.search(r"Task id\s*\"(?:[^\"]+/)?(task-\d+)\"", content)
                if m_id:
                    task_id = m_id.group(1)

            if not task_id or task_id in processed_ids:
                continue

            m_exit = re.search(r"(?:failed with exit code|exited with code)\s*[:=]?\s*(\d+)", content)
            if not m_exit:
                continue
            exit_code = int(m_exit.group(1))

            cmd = None
            cmd_cwd = cwd
            source_meta = data.get("sourceMetadata")
            if isinstance(source_meta, dict):
                tool_obj = source_meta.get("tool") if isinstance(source_meta, dict) else None
                tool_call_obj = tool_obj.get("toolCall") if isinstance(tool_obj, dict) else None
                args_json_str = tool_call_obj.get("argumentsJson") if isinstance(tool_call_obj, dict) else None
                if args_json_str:
                    try:
                        args_obj = json.loads(args_json_str)
                        if isinstance(args_obj, dict):
                            cmd = args_obj.get("CommandLine") or args_obj.get("command")
                            cmd_cwd = args_obj.get("Cwd") or cmd_cwd
                    except (json.JSONDecodeError, TypeError):
                        pass

            if not cmd and task_id in pending_tests:
                cmd = pending_tests[task_id].get("command")
                cmd_cwd = pending_tests[task_id].get("cwd") or cmd_cwd

            if not cmd:
                for pending_k, pending_v in pending_tests.items():
                    if pending_k.endswith(task_id):
                        cmd = pending_v.get("command")
                        cmd_cwd = pending_v.get("cwd") or cmd_cwd
                        break

            if not cmd or not is_test_command(cmd, cwd=cmd_cwd):
                continue

            msg_timestamp = data.get("timestamp")
            if last_dirtied_at and msg_timestamp and msg_timestamp < last_dirtied_at:
                continue

            task_tier = pending_tests.get(task_id, {}).get("tier") or classify_test_tier(cmd)
            if exit_code == 0:
                record_verification(success=True, tier=task_tier, conv_id=conv_id, state_dir=state_dir)
                cleared_state = True
            else:
                record_verification(success=False, tier=task_tier, conv_id=conv_id, state_dir=state_dir)
                cur_st = load_state(conv_id=conv_id, state_dir=state_dir)
                cur_st["code_dirty"] = True
                cur_st["verified_tier"] = None
                save_state(cur_st, conv_id=conv_id, state_dir=state_dir)
                cleared_state = False

            processed_ids.add(task_id)
            to_del = [k for k in pending_tests if k == task_id or k.endswith("/" + task_id)]
            for k in to_del:
                del pending_tests[k]
        except Exception:
            continue

    state = load_state(conv_id=conv_id, state_dir=state_dir)
    state["processed_task_ids"] = list(processed_ids)
    state["pending_background_tests"] = pending_tests
    save_state(state, conv_id=conv_id, state_dir=state_dir)

    return cleared_state


SHELL_MUTATION_PATTERNS = (
    re.compile(r"\bsed\s+(?:-[a-zA-Z]*i|--in-place)\b"),
    re.compile(r"\b(?:git\s+(?:apply|restore|checkout\s+--)|patch)\b"),
)


def check_shell_command_mutation(
    cmd: str,
    cwd: Path | str | None = None,
    conv_id: str = "default",
    state_dir: Path | None = None,
    turn_id: str | None = None,
) -> bool:
    """Detects if a shell command mutated project code files."""
    if not cmd or not cmd.strip():
        return False
    cmd_clean = cmd.strip()

    # Redirection check: extract target filename
    m_redir = re.search(r"(?:>>|>)\s*([^\s;&|]+)", cmd_clean)
    if m_redir:
        target = m_redir.group(1).strip("\"'")
        is_benign = (
            target in ("/dev/null", "/tmp", "&1", "&2")
            or target.startswith(("/dev/", "/tmp/", "&"))
        )
        if not is_benign:
            if is_code_file(target) or is_cleanroom_contract_file(target):
                record_edit(target, conv_id=conv_id, state_dir=state_dir, cwd=cwd, turn_id=turn_id)
                return True

    # Tee check
    m_tee = re.search(r"\btee\s+(?:-[a-zA-Z]*a\s+)?([^\s;&|]+)", cmd_clean)
    if m_tee:
        target = m_tee.group(1).strip("\"'")
        is_benign = (
            target in ("/dev/null", "/tmp", "&1", "&2")
            or target.startswith(("/dev/", "/tmp/", "&"))
        )
        if not is_benign:
            if is_code_file(target) or is_cleanroom_contract_file(target):
                record_edit(target, conv_id=conv_id, state_dir=state_dir, cwd=cwd, turn_id=turn_id)
                return True

    # In-place sed, git apply, patch
    for pat in SHELL_MUTATION_PATTERNS:
        if pat.search(cmd_clean):
            m_sed_file = re.search(r"\bsed\s+-[^\s]*i[^\s]*\s+(?:'[^']*'|\"[^\"]*\"|[^\s]+)\s+([^\s;&|]+)", cmd_clean)
            target = m_sed_file.group(1).strip("\"'") if m_sed_file else "<shell-mutation>"
            record_edit(target, conv_id=conv_id, state_dir=state_dir, cwd=cwd, turn_id=turn_id)
            return True

    return False


def evaluate_stop(
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
    turn_id: str | None = None,
    brain_dir: Path | str | None = None,
    payload: Optional[dict] = None,
) -> dict:
    """
    Evaluates whether an agent may stop.
    Phase-aware cleanroom fence logic (ADR-022, ADR-028, RFC-051):
    1. Reconciles background tasks via sync_background_tasks().
    2. If neither code_dirty nor spec_dirty: allows stop.
    3. If turn_mutated is False: allows stop (unblocking conversational & read-only turns).
    4. If code_dirty is True and background test is in progress: waits for reactive wakeup.
    5. Pure spec_dirty: requires verified manifest.json or trips anti-deadlock.
    6. code_dirty: requires recognized project test suite pass or trips anti-deadlock.
    """
    if os.environ.get("PSL_COMPLETION_FENCE_DISABLED", "").lower() in ("1", "true", "yes"):
        return {"decision": "allow"}

    # 1. Reconcile background tasks first
    sync_background_tasks(
        conv_id=conv_id,
        state_dir=state_dir,
        cwd=cwd,
        brain_dir=brain_dir,
        payload=payload,
    )

    state = load_state(conv_id=conv_id, state_dir=state_dir)

    effective_cwd = cwd if cwd is not None else state.get("cwd")
    if effective_cwd is None:
        effective_cwd = Path.cwd()

    # Orchestrator / Cockpit / Flight Director exemption & Persona Truth Gate (ADR-014 / ADR-022 / Issue #72)
    role = (
        (payload.get("agent_role") if payload else "")
        or (payload.get("agentRole") if payload else "")
        or (payload.get("role") if payload else "")
        or os.environ.get("AGYIS_ROLE", "")
        or os.environ.get("PSL_AGENT_ROLE", "")
    ).lower()
    is_orchestrator = (
        any(r in role for r in ("cockpit", "orchestrator", "flight_director", "sentinel", "coordinator", "main", "main_agent"))
        or normalize_role(role) in (ROLE_FLIGHT_DIRECTOR, ROLE_SWARM_ORCHESTRATOR)
    ) and role not in ("agyis_builder", "agyis_reviewer", "agyis_custodian", "agyis_auditor")

    if is_orchestrator:
        # Check if subagents were dispatched during session (Anti-Code-Monkey Invariant)
        has_subagents = False
        teamwork_dir = Path(effective_cwd) / ".agents" / "teamwork"
        if teamwork_dir.is_dir():
            try:
                for child in teamwork_dir.iterdir():
                    if child.is_dir() and not child.name.startswith("."):
                        has_subagents = True
                        break
            except Exception:
                pass

        if not has_subagents and payload and (payload.get("subagents_dispatched") or payload.get("dispatched_subagents")):
            has_subagents = True

        if has_subagents:
            from harness.subagents.truth import validate_transition_payload_truth
            allow_synth = bool(os.environ.get("AGYIS_SYNTHETIC_TEST") == "1")
            is_truth_valid, truth_errors = validate_transition_payload_truth(
                Path(effective_cwd),
                allow_synthetic=allow_synth,
            )
            if not is_truth_valid:
                block_count = state.get("block_count", 0)
                if block_count < 2:
                    state["block_count"] = block_count + 1
                    save_state(state, conv_id=conv_id, state_dir=state_dir)
                    return {
                        "decision": "continue",
                        "reason": (
                            "Persona Truth Violation: Subagents were dispatched in this session, but no verified "
                            "psl_stage_transition_payload.json was found on disk. Root orchestrators cannot declare "
                            "completion without verified delegate artifacts (Anti-Code-Monkey Invariant)."
                        ),
                    }
                else:
                    state["block_count"] = 0
                    save_state(state, conv_id=conv_id, state_dir=state_dir)
                    return {
                        "decision": "allow",
                        "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite persona truth violation.",
                    }

            # Dual-Gate Verification Fence: Gate 2 (Auditor Verdict Fence)
            auditor_fence_disabled = (
                os.environ.get("PSL_AUDITOR_FENCE_DISABLED", "").lower() in ("1", "true", "yes")
                or os.environ.get("PSL_SOLO_MODE", "").lower() in ("1", "true", "yes")
            )
            if not auditor_fence_disabled:
                from harness.subagents.verdict import validate_audit_verdict
                effective_brain_dir = get_brain_dir(conv_id=conv_id, payload=payload, brain_dir=brain_dir)
                is_verdict_valid, verdict_reason, verdict_obj = validate_audit_verdict(
                    Path(effective_cwd),
                    brain_dir=effective_brain_dir,
                    allow_synthetic=allow_synth,
                )
                if not is_verdict_valid:
                    block_count = state.get("gate2_block_count", 0)
                    if block_count < 2:
                        state["gate2_block_count"] = block_count + 1
                        save_state(state, conv_id=conv_id, state_dir=state_dir)
                        return {
                            "decision": "continue",
                            "reason": (
                                f"Dual-Gate Verification Fence (Gate 2): {verdict_reason}. "
                                "Root orchestrators and coordinators require independent out-of-band auditor "
                                "clearance (agyis audit certify) before claiming milestone completion."
                            ),
                        }
                    else:
                        state["gate2_block_count"] = 0
                        save_state(state, conv_id=conv_id, state_dir=state_dir)
                        return {
                            "decision": "allow",
                            "warning": (
                                "Anti-deadlock valve tripped after 2 Gate 2 verification blocks. "
                                "Exiting despite missing/rejected auditor verdict."
                            ),
                        }
                else:
                    state["gate2_block_count"] = 0
                    save_state(state, conv_id=conv_id, state_dir=state_dir)

        return {"decision": "allow"}

    # Turn management: if turn_id is provided and differs from active_turn_id,
    # reset turn_mutated for the new turn
    if turn_id is not None:
        current_turn = state.get("active_turn_id")
        if current_turn is not None and turn_id != current_turn:
            state["active_turn_id"] = turn_id
            state["turn_mutated"] = False
            state["turn_modified_files"] = []
            save_state(state, conv_id=conv_id, state_dir=state_dir)
        elif current_turn is None:
            state["active_turn_id"] = turn_id
            save_state(state, conv_id=conv_id, state_dir=state_dir)

    code_dirty = state.get("code_dirty", False)
    spec_dirty = state.get("spec_dirty", False)
    turn_mutated = state.get("turn_mutated", False)
    verified_tier = state.get("verified_tier")

    effective_cwd = cwd if cwd is not None else state.get("cwd")
    if effective_cwd is None:
        effective_cwd = Path.cwd()

    # Truth Anchor: reconcile empty last_modified_files against git status
    # Eliminates phantom "untracked code files" blocks when git working tree is clean
    if code_dirty and not state.get("last_modified_files", []):
        git_mods = get_git_modified_files(effective_cwd)
        if not git_mods:
            state["code_dirty"] = False
            state["turn_mutated"] = False
            state["turn_modified_files"] = []
            state["block_count"] = 0
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            code_dirty = False
        else:
            state["last_modified_files"] = git_mods
            save_state(state, conv_id=conv_id, state_dir=state_dir)

    session_has_code = any(
        is_code_file(f) or f == "<shell-mutation>" for f in state.get("session_modified_files", [])
    ) or bool(code_dirty)

    # Check commit gate if payload specifically requested it
    if payload and payload.get("gate_type") == "commit" and session_has_code:
        current_rank = TIER_RANKS.get(verified_tier or "", 0)
        if current_rank < TIER_RANKS["pkg"]:
            return {
                "decision": "deny",
                "reason": (
                    "Commit Verification Required: Git commit and PR creation require full package or workspace test suite "
                    "('agyis test', 'agyis test --full', or 'pnpm test:full') before committing."
                ),
            }
        mutation_bypass = bool(os.environ.get("AGYIS_NO_MUTATION") == "1" or os.environ.get("PSL_FENCE_BYPASS") == "1")  # agyis: no-mutant bypass check
        has_mutables = False
        try:
            from harness.mutation.micro_probe import generate_mutants_for_diff
            diff_mutants = generate_mutants_for_diff(repo_root=Path(effective_cwd or Path.cwd()))
            if diff_mutants:
                has_mutables = True
        except Exception:
            pass
        if not has_mutables:
            has_mutables = check_has_mutable_code(
                state.get("session_modified_files", []),
                cwd=effective_cwd,
            )
        if not mutation_bypass and has_mutables and not state.get("mutation_verified", False):  # agyis: no-mutant default false check
            return {
                "decision": "deny",
                "reason": (
                    "Commit Verification Required: Git commit and PR creation require verified diff-aware micro-mutation testing "
                    "('agyis test --mutation') on modified code before committing (unverified mutants)."
                ),
            }

    # Turn-Level Static AST Test Smell Linting Fence
    smell_bypass = bool(os.environ.get("AGYIS_ANTI_SYNTHETIC_BYPASS") == "1" or os.environ.get("PSL_FENCE_BYPASS") == "1")  # agyis: no-mutant bypass check
    if not smell_bypass:
        turn_mods = state.get("turn_modified_files", [])
        last_mods = state.get("last_modified_files", [])
        candidate_files = list(dict.fromkeys(turn_mods + last_mods))
        test_files = [f for f in candidate_files if is_test_file(f)]
        if test_files:
            from harness.doctor.test_smells import audit_file_smells

            hard_rejections = []
            for tf in test_files:
                tf_path = Path(tf)
                if not tf_path.is_absolute() and effective_cwd:  # agyis: no-mutant path resolution
                    tf_path = Path(effective_cwd) / tf_path
                if tf_path.is_file():
                    try:
                        for smell in audit_file_smells(tf_path):
                            if getattr(smell, "severity", "").lower() in ("hard_rejection", "error", "reject", "hard_reject"):
                                hard_rejections.append(smell)
                    except Exception:
                        pass
            if hard_rejections:
                first_smell = hard_rejections[0]
                block_count = state.get("block_count", 0)
                if block_count < 2:
                    state["block_count"] = block_count + 1
                    save_state(state, conv_id=conv_id, state_dir=state_dir)
                    return {
                        "decision": "continue",
                        "reason": (
                            f"Anti-Synthetic AST Linter Error: Synthetic Test Smell Rejection ({first_smell.rule_id} / zero-state-tautology): {first_smell.message} "
                            f"in {first_smell.file_path}:{first_smell.line_number}. "
                            "Resolve the synthetic test smell before stopping, or bypass with # agyis: no-smell <reason>."
                        ),
                    }
                else:
                    state["turn_mutated"] = False  # agyis: no-mutant anti-deadlock reset
                    state["turn_modified_files"] = []
                    state["block_count"] = 0
                    save_state(state, conv_id=conv_id, state_dir=state_dir)
                    return {
                        "decision": "allow",
                        "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite synthetic test smell.",
                    }

    # Detect handoff gate: handoff.md in modified files or .agents/teamwork/, or explicit gate_type in ("handoff", "milestone")
    is_handoff_gate = bool(state.get("handoff_modified", False))
    if payload and (payload.get("gate_type") in ("handoff", "milestone") or payload.get("action") == "evaluate_handoff"):
        is_handoff_gate = True
    if os.environ.get("PSL_COMPLETION_FENCE_GATE", "").lower() in ("handoff", "milestone"):
        is_handoff_gate = True

    all_mods = set(
        state.get("last_modified_files", [])
        + state.get("turn_modified_files", [])
        + state.get("session_modified_files", [])
    )
    for f in all_mods:
        p_name = Path(f).name.lower()
        if p_name == "handoff.md" or (p_name.startswith("handoff") and p_name.endswith(".md")):
            is_handoff_gate = True
            break

    if is_handoff_gate and session_has_code:
        current_rank = TIER_RANKS.get(verified_tier or "", 0)
        required_rank = TIER_RANKS["affected"]  # Rank 2
        if current_rank < required_rank:
            block_count = state.get("block_count", 0)
            if block_count < 2:
                state["block_count"] = block_count + 1
                save_state(state, conv_id=conv_id, state_dir=state_dir)
                return {
                    "decision": "continue",
                    "reason": (
                        "Handoff Verification Required: Subagent handoff detected ('handoff.md'). "
                        "Subagent handoffs and milestone completion require Tier 1B affected tests "
                        "('agyis test --affected' or 'pnpm test:affected') before completing handoff."
                    ),
                }
            else:
                state["turn_mutated"] = False
                state["turn_modified_files"] = []
                state["handoff_modified"] = False
                state["block_count"] = 0
                save_state(state, conv_id=conv_id, state_dir=state_dir)
                return {
                    "decision": "allow",
                    "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite unverified handoff.",
                }

        mutation_bypass = bool(os.environ.get("AGYIS_NO_MUTATION") == "1" or os.environ.get("PSL_FENCE_BYPASS") == "1")  # agyis: no-mutant bypass check
        has_mutables = check_has_mutable_code(
            state.get("session_modified_files", []),
            cwd=effective_cwd,
        )
        if not mutation_bypass and has_mutables and not state.get("mutation_verified", False):  # agyis: no-mutant default false check
            block_count = state.get("block_count", 0)
            if block_count < 2:
                state["block_count"] = block_count + 1
                save_state(state, conv_id=conv_id, state_dir=state_dir)
                return {
                    "decision": "continue",
                    "reason": (
                        "Micro-Mutation Verification Required: Subagent handoff detected ('handoff.md'). "
                        "Subagent handoffs and milestone completion require verified diff-aware micro-mutation testing "
                        "('agyis test --mutation') on modified code before completing handoff."
                    ),
                }
            else:
                state["turn_mutated"] = False  # agyis: no-mutant anti-deadlock reset
                state["turn_modified_files"] = []
                state["handoff_modified"] = False  # agyis: no-mutant handoff flag reset
                state["block_count"] = 0
                save_state(state, conv_id=conv_id, state_dir=state_dir)
                return {
                    "decision": "allow",
                    "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite unverified handoff.",
                }

    if not code_dirty and not spec_dirty:
        state["turn_mutated"] = False
        state["turn_modified_files"] = []
        state["handoff_modified"] = False
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        return {"decision": "allow"}

    # Issue #80: Turn-Scoped Mutation Sensitivity Guard
    # If no code/spec mutations occurred during the active turn (e.g. read-only file views,
    # conversational answers, triage questions), allow stop without blocking.
    if not turn_mutated:
        state["turn_mutated"] = False
        state["turn_modified_files"] = []
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        return {"decision": "allow"}

    # Issue #79: If code_dirty is True and a background test is currently in progress,
    # inform the agent and await reactive wakeup before anti-deadlock trips
    pending_tests = state.get("pending_background_tests", {})
    if code_dirty and pending_tests:
        active_list = ", ".join(f"{t}: {info.get('command')}" for t, info in pending_tests.items())
        block_count = state.get("block_count", 0)
        if block_count < 2:
            state["block_count"] = block_count + 1
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            return {
                "decision": "continue",
                "reason": (
                    f"Background Test In Progress: Waiting for test task(s) to finish: [{active_list}]. "
                    "Await reactive wakeup before stopping."
                ),
            }

    # Pure spec_dirty: cleanroom contract edits without code changes
    if not code_dirty and spec_dirty:
        if is_manifest_verified(effective_cwd):
            clear_spec_dirty(conv_id=conv_id, state_dir=state_dir)
            state["turn_mutated"] = False
            state["turn_modified_files"] = []
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            return {"decision": "allow"}

        block_count = state.get("block_count", 0)
        if block_count < 2:
            state["block_count"] = block_count + 1
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            modified_files = [f for f in state.get("last_modified_files", []) if is_cleanroom_contract_file(f)]
            files_str = ", ".join(modified_files) if modified_files else "cleanroom contract files"
            return {
                "decision": "continue",
                "reason": (
                    f"Cleanroom Verification Required: Unverified cleanroom contract edits detected in: {files_str}. "
                    "Execute 'rea verify-reconstruction' or 'agyis verify --spec' before stopping."
                ),
            }
        else:
            state["turn_mutated"] = False
            state["turn_modified_files"] = []
            state["block_count"] = 0
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            return {
                "decision": "allow",
                "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite unverified edits.",
            }

    # code_dirty is True (either pure code or dual dirty state)
    block_count = state.get("block_count", 0)
    if block_count < 2:
        state["block_count"] = block_count + 1
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        modified_files = state.get("last_modified_files", [])
        files_str = ", ".join(modified_files) if modified_files else "untracked code files"

        has_contract = any(is_cleanroom_contract_file(f) for f in modified_files)
        has_code = any(not is_cleanroom_contract_file(f) or (Path(f).suffix.lower() not in DECLARATIVE_SPEC_EXTENSIONS) for f in modified_files)

        if has_contract and has_code:
            category = "code and cleanroom contract edits"
        elif has_contract:
            category = "cleanroom contract edits"
        else:
            category = "code edits"

        if is_harness_workspace(effective_cwd):
            reason = (
                f"Verification Required: Unverified {category} detected in: {files_str}. "
                "Execute 'agyis test' (or 'python3 -m harness.cli test') before stopping."
            )
        else:
            detected_runner = detect_project_test_runner(effective_cwd)
            runner_str = detected_runner if detected_runner else "e.g. npm test, cargo test, pytest"
            reason = (
                f"Verification Required: Unverified {category} detected in: {files_str}. "
                f"Execute your project test suite ({runner_str}) before stopping."
            )

        return {
            "decision": "continue",
            "reason": reason,
        }
    else:
        state["turn_mutated"] = False
        state["turn_modified_files"] = []
        state["block_count"] = 0
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        return {
            "decision": "allow",
            "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite unverified edits.",
        }


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


def check_command_verification(
    command: str,
    exit_code: int = 0,
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
) -> bool:
    """
    Evaluates whether a command invocation represents test verification.
    If the command matches a recognized test runner:
      - If exit_code == 0: auto-clears code dirty state via record_verification(success=True).
      - If exit_code != 0: records record_verification(success=False).
    Returns True if the command was recognized as a test runner, False otherwise.
    """
    effective_cwd = cwd
    if effective_cwd is None:
        state = load_state(conv_id=conv_id, state_dir=state_dir)
        effective_cwd = state.get("cwd")

    if not is_test_command(command, cwd=effective_cwd):
        return False

    tier = classify_test_tier(command)
    success = (exit_code == 0)
    record_verification(success=success, tier=tier, conv_id=conv_id, state_dir=state_dir)
    if not success:
        state = load_state(conv_id=conv_id, state_dir=state_dir)
        state["block_count"] = 0
        save_state(state, conv_id=conv_id, state_dir=state_dir)
    return True



def main() -> None:
    """CLI / hook entry point consuming protojson from stdin and writing to stdout."""
    try:
        raw_stdin = sys.stdin.read()
        if not raw_stdin.strip():
            result = evaluate_stop("default")
            print(json.dumps(result))
            return
        payload = json.loads(raw_stdin)
        if not isinstance(payload, dict):
            result = evaluate_stop("default")
            print(json.dumps(result))
            return
    except (json.JSONDecodeError, OSError):
        print(json.dumps({"decision": "allow"}))
        return

    conv_id = str(payload.get("conversationId") or payload.get("conversation_id") or "default")
    action = payload.get("action")
    workspace_paths = payload.get("workspacePaths") or []
    cwd = (
        payload.get("cwd")
        or payload.get("workspace")
        or payload.get("working_directory")
        or (workspace_paths[0] if workspace_paths else None)
    )
    turn_id = payload.get("turnId") or payload.get("turn_id")
    state_dir = Path(payload["state_dir"]) if ("state_dir" in payload or "stateDir" in payload) else None
    brain_dir = payload.get("brain_dir") or payload.get("brainDirectory") or payload.get("brainPath")

    if action == "record_edit":
        file_path = payload.get("file_path") or payload.get("path") or ""
        state = record_edit(file_path, conv_id=conv_id, state_dir=state_dir, cwd=cwd, turn_id=turn_id)
        print(json.dumps({"status": "ok", "state": state}))
    elif action == "record_verification":
        success = bool(payload.get("success", True))
        state = record_verification(success=success, conv_id=conv_id, state_dir=state_dir)
        print(json.dumps({"status": "ok", "state": state}))
    elif action == "task_completed":
        task_id = payload.get("task_id") or payload.get("taskId") or ""
        command = payload.get("command") or payload.get("CommandLine") or ""
        extracted = extract_exit_code(payload)
        exit_code = extracted if extracted is not None else 0
        state = load_state(conv_id=conv_id, state_dir=state_dir)
        matched = is_test_command(command, cwd=cwd)
        if matched:
            success = (exit_code == 0)
            pending = state.get("pending_background_tests", {})
            task_tier = pending.get(task_id, {}).get("tier") or classify_test_tier(command)
            record_verification(success=success, tier=task_tier, conv_id=conv_id, state_dir=state_dir)
            state = load_state(conv_id=conv_id, state_dir=state_dir)
            pending = state.get("pending_background_tests", {})
            if task_id in pending:
                del pending[task_id]
            for k in [k for k in pending if k.endswith("/" + task_id)]:
                del pending[k]
            processed = set(state.get("processed_task_ids", []))
            if task_id:
                processed.add(task_id)
            state["pending_background_tests"] = pending
            state["processed_task_ids"] = list(processed)
            save_state(state, conv_id=conv_id, state_dir=state_dir)
        print(json.dumps({"status": "ok", "matched": matched, "state": state}))
    elif action == "check_command_verification":
        command = payload.get("command") or payload.get("CommandLine") or ""
        extracted = extract_exit_code(payload)
        exit_code = extracted if extracted is not None else 0
        matched = check_command_verification(command, exit_code=exit_code, conv_id=conv_id, state_dir=state_dir, cwd=cwd)
        state = load_state(conv_id=conv_id, state_dir=state_dir)
        print(json.dumps({"status": "ok", "matched": matched, "state": state}))
    elif action == "clear_spec_dirty":
        state = clear_spec_dirty(conv_id=conv_id, state_dir=state_dir)
        print(json.dumps({"status": "ok", "state": state}))
    elif action == "reset":
        state = reset_state(conv_id=conv_id, state_dir=state_dir)
        print(json.dumps({"status": "ok", "state": state}))
    elif action == "evaluate_stop":
        result = evaluate_stop(
            conv_id=conv_id,
            state_dir=state_dir,
            cwd=cwd,
            turn_id=turn_id,
            brain_dir=brain_dir,
            payload=payload,
        )
        print(json.dumps(result))
    elif "toolCall" in payload:
        # PreToolUse / PostToolUse event: intercept file modifications and test runner commands
        tool_call = payload.get("toolCall") or {}
        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args") or {}
        if cwd is None:
            cwd = tool_args.get("Cwd") or tool_args.get("cwd")
        event = str(payload.get("hookEvent") or payload.get("hook_event") or payload.get("event") or "").strip().lower()
        if "post" in event:
            is_post_tool_use = True
        elif "pre" in event:
            is_post_tool_use = False
        else:
            is_post_tool_use = bool(
                "error" in payload
                or "toolResponse" in payload
                or "tool_response" in payload
                or "toolOutput" in payload
                or "tool_output" in payload
                or "toolResult" in payload
                or "tool_result" in payload
                or "result" in payload
                or "response" in payload
                or "exitCode" in payload
                or "exit_code" in payload
            )

        if turn_id is not None:
            state = load_state(conv_id=conv_id, state_dir=state_dir)
            if state.get("active_turn_id") is not None and turn_id != state.get("active_turn_id"):
                state["active_turn_id"] = turn_id
                state["turn_mutated"] = False
                state["turn_modified_files"] = []
                save_state(state, conv_id=conv_id, state_dir=state_dir)
            elif state.get("active_turn_id") is None:
                state["active_turn_id"] = turn_id
                save_state(state, conv_id=conv_id, state_dir=state_dir)

        if not is_post_tool_use:
            pre_check = check_pre_tool_use(
                tool_name=tool_name,
                tool_args=tool_args,
                payload=payload,
                conv_id=conv_id,
                state_dir=state_dir,
                cwd=cwd,
            )
            if pre_check.get("decision") == "deny":
                print(json.dumps(pre_check))
                return

        if tool_name in ("write_to_file", "replace_file_content", "edit_file"):
            target_file = (
                tool_args.get("TargetFile")
                or tool_args.get("FilePath")
                or tool_args.get("AbsolutePath")
                or tool_args.get("file_path", "")
            )
            if target_file:
                record_edit(target_file, conv_id=conv_id, state_dir=state_dir, cwd=cwd, turn_id=turn_id)
        elif tool_name in ("run_command", "execute_command", "bash"):
            cmd = tool_args.get("CommandLine") or tool_args.get("command") or ""
            if not is_post_tool_use and cmd:
                if is_commit_or_pr_command(cmd) or (payload.get("gate_type") == "commit"):
                    state = load_state(conv_id=conv_id, state_dir=state_dir)
                    session_has_code = any(
                        is_code_file(f) or f == "<shell-mutation>" for f in state.get("session_modified_files", [])
                    ) or bool(state.get("code_dirty"))
                    if session_has_code:
                        verified_tier = state.get("verified_tier")
                        current_rank = TIER_RANKS.get(verified_tier or "", 0)
                        if current_rank < TIER_RANKS["pkg"]:
                            reason = (
                                "Commit Verification Required: Git commit and PR creation require full package or workspace test suite "
                                "('agyis test', 'agyis test --full', or 'pnpm test:full') before committing."
                            )
                            print(json.dumps({"decision": "deny", "reason": reason}))
                            return
                        mutation_bypass = bool(os.environ.get("AGYIS_NO_MUTATION") == "1" or os.environ.get("PSL_FENCE_BYPASS") == "1")  # agyis: no-mutant bypass env check
                        has_mutables = check_has_mutable_code(
                            state.get("session_modified_files", []),
                            cwd=cwd,
                        )
                        if not mutation_bypass and has_mutables and not state.get("mutation_verified", False):  # agyis: no-mutant default false check
                            reason = (
                                "Commit Verification Required: Git commit and PR creation require verified diff-aware micro-mutation testing "
                                "('agyis test --mutation') on modified code before committing (unverified mutants)."
                            )
                            print(json.dumps({"decision": "deny", "reason": reason}))
                            return  # agyis: no-mutant commit deny return
                check_shell_command_mutation(cmd, cwd=cwd, conv_id=conv_id, state_dir=state_dir, turn_id=turn_id)
            elif is_post_tool_use:
                raw_out = str(payload.get("toolResponse") or payload.get("result") or payload.get("toolOutput") or "")
                check_background_task_detachment(
                    tool_name, tool_args, raw_out, conv_id=conv_id, state_dir=state_dir, cwd=cwd
                )
                check_shell_command_mutation(cmd, cwd=cwd, conv_id=conv_id, state_dir=state_dir, turn_id=turn_id)
                exit_code = extract_exit_code(payload)
                if exit_code is not None and cmd:
                    check_command_verification(cmd, exit_code=exit_code, conv_id=conv_id, state_dir=state_dir, cwd=cwd)
                    if is_mutation_test_command(cmd):
                        state = load_state(conv_id=conv_id, state_dir=state_dir)
                        if exit_code == 0:  # agyis: no-mutant mutation exit check
                            state["mutation_verified"] = True  # agyis: no-mutant record pass
                            state["surviving_mutants"] = []
                            state["last_mutation_timestamp"] = datetime.now(timezone.utc).isoformat()
                        else:
                            state["mutation_verified"] = False  # agyis: no-mutant record fail
                        save_state(state, conv_id=conv_id, state_dir=state_dir)  # agyis: no-mutant state persistence
                    if exit_code == 0:
                        cmd_lower = cmd.lower()
                        if any(
                            p in cmd_lower
                            for p in ("verify --spec", "verify-reconstruction", "agyis verify", "harness.cli verify")
                        ):
                            clear_spec_dirty(conv_id=conv_id, state_dir=state_dir)

        # PostToolUse contract: Antigravity expects exact JSON {}
        if is_post_tool_use:
            raw_result = payload.get("toolResponse") or payload.get("result") or payload.get("toolOutput") or {}
            if isinstance(raw_result, str):
                try:
                    result_dict = json.loads(raw_result)
                except (json.JSONDecodeError, ValueError):
                    result_dict = {"output": raw_result}
            elif isinstance(raw_result, dict):
                result_dict = raw_result
            else:
                result_dict = {}
            handle_post_tool_use(tool_name, tool_args, result_dict, conv_id=conv_id, state_dir=state_dir)
            print(json.dumps({}))
        else:
            print(json.dumps({"decision": "allow"}))
    elif "command" in payload or "CommandLine" in payload:
        cmd = payload.get("command") or payload.get("CommandLine") or ""
        extracted = extract_exit_code(payload)
        exit_code = extracted if extracted is not None else 0
        matched = check_command_verification(cmd, exit_code=exit_code, conv_id=conv_id, state_dir=state_dir, cwd=cwd)
        state = load_state(conv_id=conv_id, state_dir=state_dir)
        print(json.dumps({"status": "ok", "matched": matched, "state": state, "decision": "allow"}))
    else:
        # Default behavior: Stop hook evaluation
        result = evaluate_stop(
            conv_id=conv_id,
            state_dir=state_dir,
            cwd=cwd,
            turn_id=turn_id,
            brain_dir=brain_dir,
            payload=payload,
        )
        print(json.dumps(result))


if __name__ == "__main__":
    main()
