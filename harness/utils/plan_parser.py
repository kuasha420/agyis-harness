# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Implementation plan target file parser and extraction utility (ADR-014).
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Set

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

    base_name = Path(tok_lower).name
    if base_name in SPECIAL_FILENAMES:
        return True

    has_slash = ("/" in token) or ("\\" in token)

    if "." in base_name:
        parts = base_name.rsplit(".", 1)
        ext = parts[1].lower()
        if ext in COMMON_FILE_EXTENSIONS:
            return True

    return has_slash


def _add_indexed_path(declared_files: Set[str], path_str: str) -> None:
    """Normalizes and indexes a path, its relative subpaths, and its basename into the set."""
    clean = path_str.strip().strip("'\"`")
    clean = re.sub(r"[:;,.]+$", "", clean)
    if not clean:
        return

    norm = clean.replace("\\", "/")
    declared_files.add(norm)

    stripped = norm.lstrip("/")
    if stripped:
        declared_files.add(stripped)

    p = Path(stripped)
    parts = p.parts
    for i in range(len(parts)):
        sub = "/".join(parts[i:])
        if sub:
            declared_files.add(sub)


def extract_plan_files(content: str) -> Set[str]:
    """
    Extracts declared file paths and basenames from implementation plan Markdown content.
    Extracts from:
    - Markdown file links: [basename](file:///path/to/file) or [basename](path/to/file)
    - Action headers: #### [MODIFY] [file](...) or #### [NEW] file.py
    - Backticked file paths: `path/to/file.py`
    """
    declared_files: Set[str] = set()
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


# Alias for backward compatibility
parse_plan_files = extract_plan_files


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
    import os

    env_plan = os.environ.get("PSL_PLAN_PATH")
    if env_plan:
        p = Path(env_plan)
        if p.is_file():
            return p

    search_roots: list[Path] = []
    if workspace_root:
        search_roots.append(Path(workspace_root))
    else:
        search_roots.append(Path.cwd())
        cwd = Path.cwd().resolve()
        for parent in cwd.parents:
            if (parent / ".git").exists() or (parent / ".agents").exists():
                search_roots.append(parent)

    candidate_rel_paths = [
        Path(".agents/artifacts/implementation_plan.md"),
        Path(".agents/artifacts/plan.md"),
        Path("implementation_plan.md"),
        Path("plan.md"),
        Path("docs/plan.md"),
        Path("docs/implementation_plan.md"),
        Path(".agents/plan.md"),
    ]

    for root in search_roots:
        for rel in candidate_rel_paths:
            cand = root / rel
            if cand.is_file():
                return cand

    # Check brain directories
    brain_roots: list[Path] = []
    if brain_dir:
        brain_roots.append(Path(brain_dir))
    env_brain = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
    if env_brain:
        brain_roots.append(Path(env_brain))
    if conv_id:
        brain_roots.append(Path.home() / ".gemini" / "antigravity" / "brain" / str(conv_id))

    for b_root in brain_roots:
        if b_root.is_dir():
            for rel_name in ("implementation_plan.md", "plan.md"):
                cand = b_root / rel_name
                if cand.is_file():
                    return cand

    # Glob match
    for root in search_roots:
        if root.is_dir():
            try:
                for match in sorted(root.glob("*plan*.md")):
                    if match.is_file() and not match.name.startswith("."):
                        return match
                artifacts_dir = root / ".agents" / "artifacts"
                if artifacts_dir.is_dir():
                    for match in sorted(artifacts_dir.glob("*plan*.md")):
                        if match.is_file():
                            return match
            except OSError:
                pass

    for b_root in brain_roots:
        if b_root.is_dir():
            try:
                for match in sorted(b_root.glob("*plan*.md")):
                    if match.is_file():
                        return match
            except OSError:
                pass

    return None
