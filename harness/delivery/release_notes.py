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
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.delivery.release_git import (  # noqa: F401
    DEFAULT_REPO_URL,
    SEMVER_TAG_REGEX,
    _git_tags_query,
    _is_git_repository,
    _read_tag_records,
    _run_gh_edit,
    _run_gh_upload,
    find_previous_tag,
    get_repo_remote_url,
    get_tag_date,
    list_release_tags,
    parse_semver_tag,
    resolve_git_ref,
    sync_github_release,
)

# 4 Canonical Category Titles + Breaking Changes Section Title
CATEGORY_BREAKING = "Breaking Changes"
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

    has_breaking_footer = ("BREAKING CHANGE:" in body) or ("BREAKING-CHANGE:" in body)
    m = CONVENTIONAL_COMMIT_REGEX.match(subject)
    if m:
        c_type = m.group("type").lower()
        scope = m.group("scope")
        desc = m.group("description")
        breaking = bool(m.group("breaking")) or has_breaking_footer
    else:
        c_type = "chore" if not is_merge else None
        scope = None
        desc = subject
        breaking = has_breaking_footer

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


def collect_breaking_commits(
    categories: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    Collect breaking commits from `CATEGORY_BREAKING` and `SECTION_ORDER` without duplicates.
    """
    breaking: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()

    def _add(item: Dict[str, Any]) -> None:
        key = (str(item.get("hash") or ""), str(item.get("subject") or ""))
        if key not in seen:
            seen.add(key)
            breaking.append(item)

    for item in categories.get(CATEGORY_BREAKING, []):
        _add(item)

    for section in SECTION_ORDER:
        for item in categories.get(section, []):
            if item.get("breaking"):
                _add(item)

    return breaking


def format_section_bullets(items: List[Dict[str, Any]]) -> List[str]:
    """Render commit items and nested sub-bullets as Markdown list lines."""
    lines: List[str] = []
    for item in items:
        subject = item.get("subject", "")
        lines.append(f"- {subject}")
        for bullet in item.get("sub_bullets", []):
            lines.append(f"  - {bullet}")
    return lines


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
    breaking_items = collect_breaking_commits(categories)
    if breaking_items:
        has_content = True
        lines.append(f"### {CATEGORY_BREAKING}")
        lines.extend(format_section_bullets(breaking_items))
        lines.append("")

    for section in SECTION_ORDER:
        items = categories.get(section, [])
        if not items:
            continue

        has_content = True
        lines.append(f"### {section}")
        lines.extend(format_section_bullets(items))
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


def collect_release_notes(
    repo_dir: Union[Path, str] = ".",
    base_tag: Optional[str] = None,
    target_ref: str = "HEAD",
    repo_url: Optional[str] = None,
    target_rev: Optional[str] = None,
) -> ReleaseNotesResult:
    """
    Collect commits via a single `git log` pass and return structured ReleaseNotesResult.

    Validates explicit `target_rev` and `base_tag` via `resolve_git_ref`, raising
    `ValueError` on invalid refs and `RuntimeError` on git execution failures.
    """
    repo_path = Path(repo_dir).resolve()
    resolved_repo_url = repo_url or get_repo_remote_url(repo_path)

    if target_rev is not None:
        if resolve_git_ref(repo_path, target_rev) is None:
            raise ValueError(f"Invalid target revision ref: {target_rev!r}")
        effective_rev = target_rev
    else:
        if resolve_git_ref(repo_path, target_ref) is not None:
            effective_rev = target_ref
        else:
            effective_rev = "HEAD"

    if base_tag is not None:
        if resolve_git_ref(repo_path, base_tag) is None:
            raise ValueError(f"Invalid base ref: {base_tag!r}")
        resolved_base_tag: Optional[str] = base_tag
    else:
        resolved_base_tag = find_previous_tag(repo_path, effective_rev)

    if (
        target_rev is None
        and base_tag is None
        and resolve_git_ref(repo_path, effective_rev) is None
        and _is_git_repository(repo_path)
    ):
        empty_categories = categorize_commits([])
        norm_repo = resolved_repo_url.rstrip("/")
        return ReleaseNotesResult(
            target_tag=target_ref,
            base_tag=None,
            repo_url=resolved_repo_url,
            markdown=format_markdown(
                categories=empty_categories,
                base_tag=None,
                target_tag=target_ref,
                repo_url=resolved_repo_url,
            ),
            categories=empty_categories,
            commits_count=0,
            compare_url=f"{norm_repo}/commits/{target_ref}",
        )

    rev_range = (
        f"{resolved_base_tag}..{effective_rev}" if resolved_base_tag else effective_rev
    )
    cmd = [
        "git",
        "log",
        rev_range,
        "--format=%x1e%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b",
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
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Failed to execute git log in {repo_path}: {exc}") from exc

    if proc.returncode != 0:
        err = proc.stderr.strip() or f"exit code {proc.returncode}"
        raise RuntimeError(f"git log failed for range {rev_range!r}: {err}")

    commits = parse_commits(proc.stdout)
    categories = categorize_commits(commits)
    markdown = format_markdown(
        categories=categories,
        base_tag=resolved_base_tag,
        target_tag=target_ref,
        repo_url=resolved_repo_url,
    )
    norm_repo = resolved_repo_url.rstrip("/")
    compare_url = (
        f"{norm_repo}/compare/{resolved_base_tag}...{target_ref}"
        if resolved_base_tag
        else f"{norm_repo}/commits/{target_ref}"
    )

    return ReleaseNotesResult(
        target_tag=target_ref,
        base_tag=resolved_base_tag,
        repo_url=resolved_repo_url,
        markdown=markdown,
        categories=categories,
        commits_count=len(commits),
        compare_url=compare_url,
    )


def generate_release_notes(
    repo_dir: Union[Path, str] = ".",
    base_tag: Optional[str] = None,
    target_ref: str = "HEAD",
    repo_url: Optional[str] = None,
    target_rev: Optional[str] = None,
) -> str:
    """
    High-level entrypoint to generate release notes Markdown between base_tag and target_ref.
    """
    return collect_release_notes(
        repo_dir=repo_dir,
        base_tag=base_tag,
        target_ref=target_ref,
        repo_url=repo_url,
        target_rev=target_rev,
    ).markdown


__all__ = [
    "CATEGORY_BREAKING",
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
    "collect_breaking_commits",
    "collect_release_notes",
    "extract_issue_references",
    "find_previous_tag",
    "format_markdown",
    "format_section_bullets",
    "generate_release_notes",
    "get_repo_remote_url",
    "get_tag_date",
    "list_release_tags",
    "parse_commit_record",
    "parse_commits",
    "parse_semver_tag",
    "resolve_git_ref",
    "sync_github_release",
]
