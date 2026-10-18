# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Conventional Release Notes Generation Engine & Workflow Integration.

Parses git log history using ASCII record/unit delimiters, categorizes
commits into canonical PSL release sections, extracts issue/PR references,
preserves body sub-bullets, and renders clean Markdown changelogs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union

# 4 Canonical Category Titles
CATEGORY_FEATURES = "Features & Architecture"
CATEGORY_FIXES = "Bug Fixes & Hardening"
CATEGORY_DOCS = "Documentation & Usability"
CATEGORY_MAINTENANCE = "Maintenance & Release"

SECTION_ORDER: List[str] = [
    CATEGORY_FEATURES,
    CATEGORY_FIXES,
    CATEGORY_DOCS,
    CATEGORY_MAINTENANCE,
]

TYPE_TO_CATEGORY: Dict[str, str] = {
    "feat": CATEGORY_FEATURES,
    "feature": CATEGORY_FEATURES,
    "architecture": CATEGORY_FEATURES,
    "fix": CATEGORY_FIXES,
    "bugfix": CATEGORY_FIXES,
    "patch": CATEGORY_FIXES,
    "perf": CATEGORY_FIXES,
    "docs": CATEGORY_DOCS,
    "doc": CATEGORY_DOCS,
    "chore": CATEGORY_MAINTENANCE,
    "refactor": CATEGORY_MAINTENANCE,
    "test": CATEGORY_MAINTENANCE,
    "ci": CATEGORY_MAINTENANCE,
    "build": CATEGORY_MAINTENANCE,
    "release": CATEGORY_MAINTENANCE,
    "style": CATEGORY_MAINTENANCE,
    "revert": CATEGORY_MAINTENANCE,
    "legal": CATEGORY_MAINTENANCE,
}

CONVENTIONAL_COMMIT_REGEX = re.compile(
    r"^(?P<type>[a-zA-Z0-9_-]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<description>.+)$"
)

ISSUE_EXTRACTION_REGEX = re.compile(r"(?<![\w/])#(\d+)\b")

MERGE_COMMIT_REGEX = re.compile(
    r"^Merge (pull request|branch|remote-tracking branch)", re.IGNORECASE
)

DEFAULT_REPO_URL = "https://github.com/kuasha420/agyis-harness"


@dataclass
class CommitInfo:
    """Structured representation of a parsed git commit."""

    hash: str
    short_hash: str
    subject: str
    body: str
    commit_type: Optional[str] = None
    scope: Optional[str] = None
    description: str = ""
    breaking: bool = False
    issues: List[str] = field(default_factory=list)
    sub_bullets: List[str] = field(default_factory=list)
    category: str = CATEGORY_MAINTENANCE
    is_merge: bool = False
    author_name: str = ""
    author_email: str = ""
    author_date: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert CommitInfo to dictionary."""
        d = asdict(self)
        d["type"] = self.commit_type
        return d


@dataclass
class ReleaseNotesResult:
    """Structured result of release notes generation."""

    target_tag: str
    base_tag: Optional[str]
    repo_url: str
    markdown: str
    categories: Dict[str, List[Dict[str, Any]]]
    commits_count: int
    compare_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert ReleaseNotesResult to JSON-serializable dictionary."""
        return asdict(self)


def find_previous_tag(
    repo_dir: Union[Path, str],
    target_ref: str = "HEAD",
) -> Optional[str]:
    """
    Find the ancestor release tag prior to target_ref.

    If target_ref itself resolves to an existing tag, inspects its parent
    `target_ref^`. If not a tag (or HEAD ahead of tag), inspects `target_ref`.
    Returns None if no previous tag exists in the git graph.
    """
    repo_path = Path(repo_dir).resolve()

    try:
        pts = subprocess.check_output(
            ["git", "tag", "--points-at", target_ref],
            cwd=repo_path,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip().splitlines()
        is_tag = len(pts) > 0
    except (OSError, subprocess.SubprocessError):
        is_tag = False

    spec = f"{target_ref}^" if is_tag else target_ref
    try:
        tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0", spec],
            cwd=repo_path,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        return tag if tag else None
    except (OSError, subprocess.SubprocessError):
        return None


def get_repo_remote_url(
    repo_dir: Union[Path, str],
    remote_name: str = "origin",
) -> str:
    """
    Resolve the GitHub HTTPS repository URL from git remote.

    Normalizes git@github.com:owner/repo.git and https://... to clean HTTPS URLs.
    Falls back to DEFAULT_REPO_URL on lookup failure.
    """
    repo_path = Path(repo_dir).resolve()
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", remote_name],
            cwd=repo_path,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        if not url:
            return DEFAULT_REPO_URL

        if url.endswith(".git"):
            url = url[:-4]

        if url.startswith("git@github.com:"):
            path_part = url[len("git@github.com:"):]
            return f"https://github.com/{path_part}"
        elif url.startswith("https://") or url.startswith("http://"):
            return url
        return DEFAULT_REPO_URL
    except (OSError, subprocess.SubprocessError):
        return DEFAULT_REPO_URL


def extract_issue_references(text: str) -> List[str]:
    """
    Extract unique issue/PR numeric references from text while preserving order.

    Filters out hex colors (#ffffff) and language directives (C# #define).
    """
    matches = ISSUE_EXTRACTION_REGEX.findall(text)
    return list(dict.fromkeys(matches))


def parse_commit_record(raw_record: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single %x1f-delimited commit record into a structured dictionary.
    """
    if not raw_record.strip():
        return None

    parts = raw_record.split("\x1f")
    full_hash = ""
    short_hash = ""
    author_name = ""
    author_email = ""
    author_date = ""
    subject = ""
    body = ""

    if len(parts) >= 7:
        full_hash = parts[0].strip()
        short_hash = parts[1].strip()
        author_name = parts[2].strip()
        author_email = parts[3].strip()
        author_date = parts[4].strip()
        subject = parts[5].strip()
        body = parts[6].strip()
    elif len(parts) == 3:
        full_hash = parts[0].strip()
        short_hash = full_hash[:7] if len(full_hash) >= 7 else full_hash
        subject = parts[1].strip()
        body = parts[2].strip()
    elif len(parts) == 2:
        full_hash = parts[0].strip()
        short_hash = full_hash[:7] if len(full_hash) >= 7 else full_hash
        subject = parts[1].strip()
    elif len(parts) == 1:
        subject = parts[0].strip()

    if not subject and not full_hash:
        return None

    is_merge = bool(MERGE_COMMIT_REGEX.match(subject))

    full_text = f"{subject}\n{body}" if body else subject
    issues = extract_issue_references(full_text)

    sub_bullets: List[str] = []
    if body:
        for line in body.splitlines():
            s = line.strip()
            if s.startswith(("- ", "* ")):
                bullet = s[2:].strip()
                b_lower = bullet.lower()
                if any(
                    b_lower.startswith(prefix)
                    for prefix in (
                        "closes ",
                        "fixes ",
                        "resolves ",
                        "signed-off-by:",
                        "co-authored-by:",
                    )
                ):
                    continue
                if bullet:
                    sub_bullets.append(bullet)

    m = CONVENTIONAL_COMMIT_REGEX.match(subject)
    if m:
        c_type = m.group("type").lower()
        scope = m.group("scope")
        desc = m.group("description")
        breaking = (
            bool(m.group("breaking"))
            or ("BREAKING CHANGE:" in body)
            or ("BREAKING-CHANGE:" in body)
        )
    else:
        c_type = "chore" if not is_merge else None
        scope = None
        desc = subject
        breaking = False

    category = TYPE_TO_CATEGORY.get(c_type or "", CATEGORY_MAINTENANCE)

    return {
        "hash": full_hash,
        "short_hash": short_hash,
        "author_name": author_name,
        "author_email": author_email,
        "author_date": author_date,
        "subject": subject,
        "body": body,
        "type": c_type,
        "commit_type": c_type,
        "scope": scope,
        "description": desc,
        "breaking": breaking,
        "issues": issues,
        "sub_bullets": sub_bullets,
        "category": category,
        "is_merge": is_merge,
    }


def parse_commits(git_log_output: str) -> List[Dict[str, Any]]:
    """
    Parse git log output separated by ASCII Record Separator (%x1e).
    """
    if not git_log_output or not git_log_output.strip():
        return []

    commits: List[Dict[str, Any]] = []
    raw_records = git_log_output.split("\x1e")
    for raw in raw_records:
        parsed = parse_commit_record(raw)
        if parsed is not None:
            commits.append(parsed)

    return commits


def categorize_commits(
    commits: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group parsed commits into canonical sections, filtering merge commits.
    """
    categorized: Dict[str, List[Dict[str, Any]]] = {
        CATEGORY_FEATURES: [],
        CATEGORY_FIXES: [],
        CATEGORY_DOCS: [],
        CATEGORY_MAINTENANCE: [],
    }

    for c in commits:
        if c.get("is_merge"):
            continue

        c_type = (c.get("type") or c.get("commit_type") or "").lower()
        cat = TYPE_TO_CATEGORY.get(c_type, CATEGORY_MAINTENANCE)
        categorized[cat].append(c)

    return categorized


def format_markdown(
    categories: Dict[str, List[Dict[str, Any]]],
    base_tag: Optional[str],
    target_tag: str,
    repo_url: str = DEFAULT_REPO_URL,
) -> str:
    """
    Format categorized commits into standard GitHub release notes Markdown.
    """
    lines: List[str] = [
        f"# Release {target_tag}",
        "",
        "## What's Changed",
        "",
    ]

    has_content = False
    for section in SECTION_ORDER:
        items = categories.get(section, [])
        if not items:
            continue

        has_content = True
        lines.append(f"### {section}")
        for item in items:
            subject = item.get("subject", "")
            lines.append(f"- {subject}")
            for bullet in item.get("sub_bullets", []):
                lines.append(f"  - {bullet}")
        lines.append("")

    if not has_content:
        lines.append("*No changes.*")
        lines.append("")

    norm_repo = repo_url.rstrip("/")
    if base_tag:
        lines.append(
            f"**Full Changelog**: {norm_repo}/compare/{base_tag}...{target_tag}"
        )
    else:
        lines.append(f"**Full Changelog**: {norm_repo}/commits/{target_tag}")

    lines.append("")
    return "\n".join(lines)


def generate_release_notes(
    repo_dir: Union[Path, str] = ".",
    base_tag: Optional[str] = None,
    target_ref: str = "HEAD",
    repo_url: Optional[str] = None,
) -> str:
    """
    High-level entrypoint to generate release notes Markdown between base_tag and target_ref.
    """
    repo_path = Path(repo_dir).resolve()
    resolved_repo_url = repo_url or get_repo_remote_url(repo_path)
    resolved_base_tag = base_tag if base_tag is not None else find_previous_tag(repo_path, target_ref)

    if resolved_base_tag:
        rev_range = f"{resolved_base_tag}..{target_ref}"
    else:
        rev_range = target_ref

    cmd = [
        "git",
        "log",
        rev_range,
        '--format=%x1e%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b',
        "--no-merges",
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        git_log_output = proc.stdout if proc.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        git_log_output = ""

    commits = parse_commits(git_log_output)
    categories = categorize_commits(commits)
    return format_markdown(
        categories=categories,
        base_tag=resolved_base_tag,
        target_tag=target_ref,
        repo_url=resolved_repo_url,
    )


def sync_github_release(
    tag: str,
    notes_markdown: str,
    repo_dir: Union[Path, str] = ".",
    prerelease: Optional[bool] = None,
) -> Tuple[bool, str]:
    """
    Create or edit a GitHub release using the GitHub CLI (`gh`).

    Writes notes to a temporary file and synchronizes with `gh release edit`
    or `gh release create`.
    """
    repo_path = Path(repo_dir).resolve()

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".md") as tmp:
        tmp.write(notes_markdown)
        tmp_path = Path(tmp.name)

    try:
        # Check if release exists
        view_cmd = ["gh", "release", "view", tag]
        view_res = subprocess.run(
            view_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )

        if view_res.returncode == 0:
            edit_cmd = ["gh", "release", "edit", tag, "--notes-file", str(tmp_path)]
            edit_res = subprocess.run(
                edit_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if edit_res.returncode == 0:
                return True, f"Successfully updated GitHub release {tag}"
            return False, f"Failed to edit GitHub release {tag}: {edit_res.stderr.strip()}"
        else:
            create_cmd = [
                "gh",
                "release",
                "create",
                tag,
                "--title",
                tag,
                "--notes-file",
                str(tmp_path),
            ]
            is_pre = prerelease
            if is_pre is None:
                tag_lower = tag.lower()
                is_pre = any(p in tag_lower for p in ("rc", "alpha", "beta", "dev"))
            if is_pre:
                create_cmd.append("--prerelease")

            create_res = subprocess.run(
                create_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if create_res.returncode == 0:
                return True, f"Successfully created GitHub release {tag}"
            return False, f"Failed to create GitHub release {tag}: {create_res.stderr.strip()}"
    except FileNotFoundError:
        return False, "GitHub CLI ('gh') not found in PATH"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Subprocess error executing GitHub CLI: {exc}"
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


__all__ = [
    "CATEGORY_DOCS",
    "CATEGORY_FEATURES",
    "CATEGORY_FIXES",
    "CATEGORY_MAINTENANCE",
    "CONVENTIONAL_COMMIT_REGEX",
    "CommitInfo",
    "DEFAULT_REPO_URL",
    "ISSUE_EXTRACTION_REGEX",
    "ReleaseNotesResult",
    "SECTION_ORDER",
    "TYPE_TO_CATEGORY",
    "categorize_commits",
    "extract_issue_references",
    "find_previous_tag",
    "format_markdown",
    "generate_release_notes",
    "get_repo_remote_url",
    "parse_commit_record",
    "parse_commits",
    "sync_github_release",
]
