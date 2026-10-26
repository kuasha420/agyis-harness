# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Implementation plan target file parser and extraction utility (ADR-014).
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Optional, Set

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


def is_plan_completed(content: str) -> bool:
    r"""
    Determines if an implementation plan is 100% completed.
    Scans for task checkboxes with regex r"[-*+]\s*\[([ xX])\]".
    Returns True if total checkboxes > 0 and pending checkboxes (`[ ]`) == 0.
    Returns False otherwise.
    """
    if not content or not isinstance(content, str):
        return False
    matches = re.findall(r"[-*+]\s*\[([ xX])\]", content)
    if not matches:
        return False
    pending = sum(1 for m in matches if m == " ")
    return len(matches) > 0 and pending == 0


def find_active_plan(
    conv_id: Optional[str] = None,
    workspace_root: Optional[Path | str] = None,
    brain_dir: Optional[Path | str] = None,
    ignore_completed: bool = True,
) -> Optional[Path]:
    """
    Locates the active implementation plan markdown file.
    Searches in priority order:
    1. PSL_PLAN_PATH override
    2. Active Brain Directory (*plan*.md, *plan*.json, newest mtime first)
    3. Workspace Artifacts (.agents/artifacts/, .agents/, docs/, workspace_root)
    4. Fallback to newest completed plan overall if all candidates completed.
    """
    import os

    # Tier 1 (Override): Respect PSL_PLAN_PATH if file exists
    env_plan = os.environ.get("PSL_PLAN_PATH")
    if env_plan:
        p = Path(env_plan)
        if p.is_file():
            return p

    def _safe_mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    def _safe_read(p: Path) -> str:
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    # Tier 2 (Active Brain Directory)
    tier2_candidates: list[Path] = []
    tier2_seen: set[Path] = set()

    brain_roots: list[Path] = []
    if brain_dir:
        brain_roots.append(Path(brain_dir))
    env_brain = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
    if env_brain:
        brain_roots.append(Path(env_brain))

    cids: list[str] = []
    if conv_id:
        cids.append(str(conv_id))
    for env_k in ("AGYIS_CONVERSATION_ID", "GEMINI_CONVERSATION_ID"):
        val = os.environ.get(env_k)
        if val and val not in cids:
            cids.append(val)

    for cid in cids:
        brain_roots.append(Path.home() / ".gemini" / "antigravity" / "brain" / cid)

    for b_root in brain_roots:
        if not b_root.is_dir():
            continue
        try:
            for match in b_root.iterdir():
                if match.is_file() and not match.name.startswith("."):
                    mname = match.name.lower()
                    if "plan" in mname and (mname.endswith(".md") or mname.endswith(".json")):
                        res = match.resolve()
                        if res not in tier2_seen:
                            tier2_seen.add(res)
                            tier2_candidates.append(match)
        except OSError:
            pass

    tier2_candidates.sort(key=_safe_mtime, reverse=True)

    if not ignore_completed:
        if tier2_candidates:
            return tier2_candidates[0]
    else:
        for cand in tier2_candidates:
            content = _safe_read(cand)
            if not is_plan_completed(content):
                return cand

    # Tier 3 (Workspace Artifacts)
    tier3_candidates: list[Path] = []
    tier3_seen: set[Path] = set()

    ws_roots: list[Path] = []
    if workspace_root:
        ws_roots.append(Path(workspace_root))
    else:
        ws_roots.append(Path.cwd())
        cwd = Path.cwd().resolve()
        for parent in cwd.parents:
            if (parent / ".git").exists() or (parent / ".agents").exists():
                ws_roots.append(parent)

    for ws_root in ws_roots:
        if not ws_root.is_dir():
            continue
        scan_subdirs = [
            ws_root / ".agents" / "artifacts",
            ws_root / ".agents",
            ws_root / "docs",
            ws_root,
        ]
        for s_dir in scan_subdirs:
            if not s_dir.is_dir():
                continue
            try:
                for match in s_dir.iterdir():
                    if match.is_file() and not match.name.startswith("."):
                        mname = match.name.lower()
                        if "plan" in mname and (mname.endswith(".md") or mname.endswith(".json")):
                            res = match.resolve()
                            if res not in tier3_seen and res not in tier2_seen:
                                tier3_seen.add(res)
                                tier3_candidates.append(match)
            except OSError:
                pass

    tier3_candidates.sort(key=_safe_mtime, reverse=True)

    if not ignore_completed:
        if tier3_candidates:
            return tier3_candidates[0]
    else:
        for cand in tier3_candidates:
            content = _safe_read(cand)
            if not is_plan_completed(content):
                return cand

    # Fallback: newest completed candidate overall across Tier 2 and Tier 3
    all_candidates = tier2_candidates + tier3_candidates
    if all_candidates:
        all_candidates.sort(key=_safe_mtime, reverse=True)
        return all_candidates[0]

    return None
