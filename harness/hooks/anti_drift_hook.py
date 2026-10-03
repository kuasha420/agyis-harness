#!/usr/bin/env python3
"""
PSL Harness: PreToolUse Anti-Drift Verification Gate (ADR-024)

Enforces plan boundaries by intercepting file modifications (write_to_file,
replace_file_content, edit_file) and checking them against declared file targets
in the active implementation plan (e.g. implementation_plan.md).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from typing import Optional

COMMON_FILE_EXTENSIONS: frozenset[str] = frozenset({
    "py", "pyi", "ts", "tsx", "js", "jsx", "mjs", "cjs", "json", "md", "markdown",
    "txt", "rst", "toml", "yaml", "yml", "rs", "go", "c", "cpp", "cc", "cxx",
    "h", "hpp", "java", "kt", "scala", "rb", "php", "sh", "bash", "zsh", "swift",
    "cs", "sql", "html", "css", "scss", "sass", "less", "vue", "svelte", "lock",
    "cfg", "ini"
})

SPECIAL_FILENAMES: frozenset[str] = frozenset({
    "dockerfile", "makefile", "license", "procfile", "psl", ".gitignore",
    ".gitattributes", ".editorconfig", "package.json", "pyproject.toml"
})

EXCLUDED_WORDS: frozenset[str] = frozenset({
    # Common tools & actions
    "write_to_file", "replace_file_content", "edit_file", "view_file", "grep_search",
    "run_command", "manage_task", "send_message", "schedule", "read_url_content",
    "read_browser_page", "pretooluse", "posttooluse", "preinvocation", "postinvocation",
    "stop", "allow", "deny", "ask", "force_ask",
    # CLI commands
    "python", "python3", "bash", "sh", "pytest", "uv", "npm", "pnpm", "cargo", "git",
    "cd", "ls", "cat", "echo", "grep", "mkdir", "rm", "touch",
    # Keywords
    "def", "class", "return", "import", "from", "if", "else", "elif", "for", "while",
    "try", "except", "finally", "with", "as", "pass", "raise", "yield", "lambda",
    "true", "false", "null", "none", "true,", "false,",
})


def _is_candidate_filepath(token: str) -> bool:
    """Checks whether a token represents a plausible relative or absolute file path."""
    if not token or len(token) < 2:
        return False
    if any(ch in token for ch in (" ", "\t", "\n", "\r")):
        return False
    if token.startswith(("-", "--", "http://", "https://", "$", ">", "<", "@", "%")):
        return False
    if any(op in token for op in ("&&", "||", "|", ";", "(", ")", "{", "}")):
        return False

    tok_lower = token.lower().rstrip(":,;.")
    if tok_lower in EXCLUDED_WORDS:
        return False

    # Check for known special filename
    base_name = Path(tok_lower).name
    if base_name in SPECIAL_FILENAMES:
        return True

    # Check if contains directory slash
    has_slash = ("/" in token) or ("\\" in token)

    # Check if has an extension
    if "." in base_name:
        parts = base_name.rsplit(".", 1)
        ext = parts[1].lower()
        # Ensure it's not a version or number (e.g. 1.0, 3.12, 1.0s)
        if ext in COMMON_FILE_EXTENSIONS:
            return True

    return has_slash


def _add_indexed_path(declared_files: set[str], path_str: str) -> None:
    """Normalizes and indexes a path, its relative subpaths, and its basename into the set."""
    clean = path_str.strip().strip("'\"`")
    clean = re.sub(r"[:;,.]+$", "", clean)
    if not clean:
        return

    # Normalize slashes
    norm = clean.replace("\\", "/")
    declared_files.add(norm)

    # Strip leading slash if any
    stripped = norm.lstrip("/")
    if stripped:
        declared_files.add(stripped)

    # Add all suffix subpaths (e.g. for a/b/c/file.py -> b/c/file.py, c/file.py, file.py)
    p = Path(stripped)
    parts = p.parts
    for i in range(len(parts)):
        sub = "/".join(parts[i:])
        if sub:
            declared_files.add(sub)


def parse_plan_files(content: str) -> set[str]:
    """
    Extracts declared file paths and basenames from implementation plan Markdown content.
    Extracts from:
    - Markdown file links: [basename](file:///path/to/file) or [basename](path/to/file)
    - Action headers: #### [MODIFY] [file](...) or #### [NEW] file.py
    - Backticked file paths: `path/to/file.py`
    """
    declared_files: set[str] = set()
    if not content:
        return declared_files

    # 1. Action headers: e.g. #### [MODIFY] [path](url) or #### [NEW] path/to/file.py
    header_pattern = re.compile(
        r"(?m)^#{1,6}\s*(?:\[?(?:MODIFY|NEW|DELETE|CREATE|UPDATE|EDIT|ADD|REMOVE)\]?\s*)+(.*)$",
        re.IGNORECASE,
    )
    for match in header_pattern.finditer(content):
        header_rest = match.group(1).strip()
        plain_tokens = header_rest.split()
        for tok in plain_tokens:
            tok_clean = tok.strip("`'\"[]():,)")
            if _is_candidate_filepath(tok_clean):
                _add_indexed_path(declared_files, tok_clean)

    # 2. Markdown links: [text](target)
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    for match in link_pattern.finditer(content):
        text = match.group(1).strip().strip("`")
        target = match.group(2).strip()

        # Clean target: strip file:// or file:///
        clean_target = re.sub(r"^file:///?", "/", target) if target.startswith("file://") else target
        clean_target = clean_target.split("#")[0].strip()
        clean_target = clean_target.split("?")[0].strip()

        if not (clean_target.startswith("http://") or clean_target.startswith("https://") or clean_target.startswith("mailto:")):
            if clean_target and _is_candidate_filepath(clean_target):
                _add_indexed_path(declared_files, clean_target)

        if text and _is_candidate_filepath(text):
            _add_indexed_path(declared_files, text)

    # 3. Backticked tokens: `path/to/file.py`
    backtick_pattern = re.compile(r"`([^`\n\r]+)`")
    for match in backtick_pattern.finditer(content):
        token = match.group(1).strip().strip("'\"")
        token = re.sub(r"[:;,.]+$", "", token)
        if _is_candidate_filepath(token):
            _add_indexed_path(declared_files, token)

    return declared_files


def is_exempt_file(path_str: str) -> bool:
    """
    Determines if a target file is exempt from anti-drift enforcement.
    Exemptions include:
    - Markdown documents (.md, .markdown)
    - Documentation / text (.txt, .rst, .adoc)
    - Artifact files (.agents/artifacts/*, brain directories)
    - Temporary scratch files (scratch/*, tmp/*, /tmp/*)
    """
    if not path_str or not path_str.strip():
        return True

    p = Path(path_str)
    suffix = p.suffix.lower()
    if suffix in (".md", ".markdown", ".txt", ".rst", ".adoc"):
        return True

    normalized = path_str.replace("\\", "/").lower()

    exempt_patterns = (
        ".agents/artifacts/",
        "scratch/",
        "/scratch/",
        "tmp/",
        "/tmp/",
        ".system_generated/",
        "/brain/",
        ".gemini/antigravity/",
    )
    for pattern in exempt_patterns:
        if pattern in normalized or normalized.startswith(pattern.lstrip("/")):
            return True

    parts = [part.lower() for part in p.parts]
    for exempt_dir in ("scratch", "tmp"):
        if exempt_dir in parts:
            return True

    return False


def check_drift(target_file: str, plan_files: set[str], strict: bool = False) -> dict:
    """
    Evaluates whether modifying target_file constitutes plan drift.

    Returns:
        {"decision": "allow"} when target_file is declared or exempt.
        {"decision": "ask", "reason": ...} when undeclared and strict mode is active.
        {"decision": "allow", "reason": ...} when undeclared under default non-strict mode.
    """
    if not target_file:
        return {"decision": "allow"}

    if is_exempt_file(target_file):
        return {"decision": "allow"}

    if not plan_files:
        return {"decision": "allow"}

    target_clean = target_file.replace("\\", "/").strip()
    target_name = Path(target_clean).name

    # 1. Exact match or basename match
    if target_clean in plan_files or target_clean.lstrip("/") in plan_files or target_name in plan_files:
        return {"decision": "allow"}

    # 2. Suffix / relative match
    for pf in plan_files:
        pf_clean = pf.replace("\\", "/").strip().lstrip("/")
        tgt_stripped = target_clean.lstrip("/")
        if tgt_stripped == pf_clean:
            return {"decision": "allow"}
        if tgt_stripped.endswith("/" + pf_clean):
            return {"decision": "allow"}
        if pf_clean.endswith("/" + tgt_stripped):
            return {"decision": "allow"}

    # Undeclared file detected
    is_strict = strict or (os.environ.get("PSL_STRICT_ANTI_DRIFT", "").strip().lower() in ("1", "true", "yes"))

    if is_strict:
        return {
            "decision": "ask",
            "reason": (
                f"PSL Anti-Drift Gate: Target file '{target_file}' is not listed in implementation_plan.md. "
                "Please confirm intentional edit."
            ),
        }
    else:
        return {
            "decision": "allow",
            "reason": (
                f"PSL Anti-Drift Notice: Target file '{target_file}' was not declared in implementation_plan.md; "
                "permitted under non-strict mode."
            ),
        }


def check_auditor_write_block(payload: dict) -> Optional[dict]:
    """
    PSL PreToolUse Write-Block Guard (ADR-024 / ADR-025).

    Blocks file modification tools (write_to_file, replace_file_content, edit_file)
    when the calling subagent role is an auditor, planner, coordinator, reviewer,
    or any agent declaring write: false.
    """
    if not isinstance(payload, dict):
        return None

    role = (
        payload.get("agent_role")
        or payload.get("agentRole")
        or payload.get("role")
        or payload.get("agent_name")
        or payload.get("agentName")
        or payload.get("agent")
        or os.environ.get("PSL_SUBAGENT_ROLE")
        or os.environ.get("PSL_AGENT_ROLE")
        or ""
    )
    r_lower = role.strip().lower().replace("-", "_")
    is_auditor = (
        r_lower in ("auditor", "harness_auditor", "qa_verifier", "qa")
        or "auditor" in r_lower
    )
    is_planner = (
        r_lower in ("planner", "architect", "designer", "researcher")
        or "planner" in r_lower
    )
    is_coordinator = (
        r_lower in ("coordinator", "orchestrator", "swarm_lead")
        or "coordinator" in r_lower
    )
    is_reviewer = (
        r_lower in ("hammer", "reviewer", "inspector", "harness_reviewer")
        or "reviewer" in r_lower
    )
    is_main = (
        r_lower in ("main", "psl_main", "lead")
        or "master" in r_lower
    )

    perms = payload.get("permissions")
    explicit_write_false = (
        payload.get("write") is False
        or payload.get("can_write") is False
        or (isinstance(perms, dict) and perms.get("write") is False)
    )

    is_builder = (
        r_lower in ("builder", "worker", "implementer", "harness_builder", "executioner")
        or "builder" in r_lower
    )
    if (is_builder or is_main) and not explicit_write_false:
        return None

    should_block = is_auditor or is_planner or is_coordinator or is_reviewer or explicit_write_false
    if not should_block:
        return None

    tool_call = payload.get("toolCall", {})
    if isinstance(tool_call, dict):
        tool_name = tool_call.get("name") or ""
    else:
        tool_name = ""
    if not tool_name:
        tool_name = payload.get("tool_name") or payload.get("action") or ""

    tool_lower = tool_name.strip().lower()
    if tool_lower in ("write_to_file", "replace_file_content", "edit_file"):
        if is_auditor:
            reason = "PSL Auditor Invariant: harness_auditor is strictly verification-only and cannot mutate files."
        elif is_planner:
            reason = f"PSL Write-Block Guard: {role or 'planner'} is artifact-only and cannot mutate files directly."
        elif is_coordinator:
            reason = f"PSL Write-Block Guard: {role or 'coordinator'} is orchestration-only and cannot mutate files."
        else:
            reason = f"PSL Write-Block Guard: agent '{role or 'agent'}' has write: false and cannot mutate files."

        return {
            "decision": "deny",
            "reason": reason,
        }

    return None


def find_active_plan(
    conv_id: Optional[str] = None,
    workspace_root: Optional[Path | str] = None,
    brain_dir: Optional[Path | str] = None,
) -> Optional[Path]:
    """
    Locates the active implementation plan markdown file.
    Searches in priority order:
    1. PSL_PLAN_PATH override
    2. Workspace root (.agents/artifacts/implementation_plan.md, plan.md, etc.)
    3. Current working directory (when workspace_root is None)
    4. Antigravity parent worktree discovery (when workspace_root is None)
    5. Explicit brain_dir or ANTIGRAVITY_BRAIN_DIR
    6. Conversation brain directory (~/.gemini/antigravity/brain/<conv_id>/)
    7. Glob match for *plan*.md in workspace_root (or cwd), artifacts, or brain directory
    """
    env_plan = os.environ.get("PSL_PLAN_PATH")
    if env_plan:
        p = Path(env_plan)
        if p.is_file():
            return p

    candidates: list[Path] = []

    # 2. Workspace root or CWD
    if workspace_root:
        ws = Path(workspace_root)
        candidates.append(ws / ".agents" / "artifacts" / "implementation_plan.md")
        candidates.append(ws / ".agents" / "artifacts" / "plan.md")
        candidates.append(ws / "implementation_plan.md")
        candidates.append(ws / "plan.md")
    else:
        # 3. Only fall back to Current working directory and parent walking when workspace_root is None
        cwd = Path.cwd()
        candidates.append(cwd / ".agents" / "artifacts" / "implementation_plan.md")
        candidates.append(cwd / ".agents" / "artifacts" / "plan.md")
        candidates.append(cwd / "implementation_plan.md")
        candidates.append(cwd / "plan.md")

        # 4. Walk up parent directories if inside an Antigravity worktree
        for parent in cwd.parents:
            candidates.append(parent / ".agents" / "artifacts" / "implementation_plan.md")
            candidates.append(parent / ".agents" / "artifacts" / "plan.md")
            candidates.append(parent / "implementation_plan.md")
            candidates.append(parent / "plan.md")

    # 5. Explicit brain_dir or env
    target_brain = brain_dir or os.environ.get("ANTIGRAVITY_BRAIN_DIR") or os.environ.get("GEMINI_BRAIN_DIR")
    if target_brain:
        b_path = Path(target_brain)
        candidates.append(b_path / "implementation_plan.md")
        candidates.append(b_path / "plan.md")

    # 6. Conversation brain directory
    if conv_id and conv_id != "default":
        conv_brain = Path.home() / ".gemini" / "antigravity" / "brain" / conv_id
        candidates.append(conv_brain / "implementation_plan.md")
        candidates.append(conv_brain / "plan.md")

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    # 7. Glob fallbacks
    search_dirs: list[Path] = []
    if workspace_root:
        ws = Path(workspace_root)
        search_dirs.append(ws / ".agents" / "artifacts")
        search_dirs.append(ws)
    else:
        cwd = Path.cwd()
        search_dirs.append(cwd / ".agents" / "artifacts")
        search_dirs.append(cwd)

    if target_brain:
        search_dirs.append(Path(target_brain))
    if conv_id and conv_id != "default":
        search_dirs.append(Path.home() / ".gemini" / "antigravity" / "brain" / conv_id)

    for s_dir in search_dirs:
        if s_dir.is_dir():
            for f in sorted(s_dir.glob("*plan*.md")):
                if f.is_file():
                    return f

    return None


def main() -> None:
    """PreToolUse anti-drift entry point consuming protojson from stdin."""
    try:
        raw_stdin = sys.stdin.read()
        if not raw_stdin.strip():
            print(json.dumps({"decision": "allow"}))
            return
        payload = json.loads(raw_stdin)
        if not isinstance(payload, dict):
            print(json.dumps({"decision": "allow"}))
            return
    except (json.JSONDecodeError, OSError):
        print(json.dumps({"decision": "allow"}))
        return

    # Action override for direct testing/IPC
    action = payload.get("action")
    if action == "check_auditor_write_block":
        result = check_auditor_write_block(payload)
        print(json.dumps(result or {"decision": "allow"}))
        return
    if action == "check_drift":
        target = payload.get("target_file", "")
        plan_files = set(payload.get("plan_files", []))
        strict = bool(payload.get("strict", False))
        result = check_drift(target, plan_files, strict=strict)
        print(json.dumps(result))
        return

    # Intercept auditor file mutations before plan check
    auditor_block = check_auditor_write_block(payload)
    if auditor_block:
        print(json.dumps(auditor_block))
        return

    conv_id = payload.get("conversationId") or payload.get("conversation_id")
    workspace_paths = payload.get("workspacePaths") or []
    workspace_root = workspace_paths[0] if workspace_paths else None
    artifact_dir = payload.get("artifactDirectoryPath")

    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    tool_args = tool_call.get("args", {})

    target_file = (
        tool_args.get("TargetFile")
        or tool_args.get("target_file")
        or tool_args.get("FilePath")
        or tool_args.get("file_path")
        or tool_args.get("AbsolutePath")
        or tool_args.get("path")
        or ""
    )

    if not target_file:
        print(json.dumps({"decision": "allow"}))
        return

    plan_path = find_active_plan(conv_id=conv_id, workspace_root=workspace_root, brain_dir=artifact_dir)
    if not plan_path or not plan_path.is_file():
        print(json.dumps({"decision": "allow"}))
        return

    try:
        plan_content = plan_path.read_text(encoding="utf-8")
    except OSError:
        print(json.dumps({"decision": "allow"}))
        return

    try:
        plan_files = parse_plan_files(plan_content)
    except Exception as exc:
        print(f"PSL Anti-Drift: Error parsing plan files: {exc}", file=sys.stderr)
        print(json.dumps({"decision": "allow"}))
        return

    strict = os.environ.get("PSL_STRICT_ANTI_DRIFT", "").strip().lower() in ("1", "true", "yes")
    result = check_drift(target_file, plan_files, strict=strict)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
