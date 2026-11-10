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
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union

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

SEMVER_TAG_REGEX = re.compile(
    r"^[vV]?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
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


def resolve_git_ref(
    repo_dir: Union[Path, str],
    ref: str,
) -> Optional[str]:
    """
    Verify and resolve a git revision reference to a commit SHA.

    Handles lightweight tags, annotated tags, branches, SHAs, and HEAD.
    Returns None if the reference is invalid or cannot be peeled to a commit.
    """
    if not isinstance(ref, str):
        return None
    ref_s = ref.strip()
    if not ref_s or ref_s.startswith("-"):
        return None

    repo_path = Path(repo_dir).resolve()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref_s}^{{commit}}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if proc.returncode == 0:
            sha = proc.stdout.strip()
            return sha if sha else None
        return None
    except (OSError, subprocess.SubprocessError):
        return None


def parse_semver_tag(
    tag: str,
) -> Optional[Tuple[int, int, int, int, Tuple[Tuple[int, Union[int, str]], ...]]]:
    """
    Parse a SemVer tag (`v?MAJOR.MINOR.PATCH(-pre)?(+build)?`) into a sortable tuple.

    Returns `(major, minor, patch, is_final, prerelease_parts)` where `is_final=1`
    for stable releases and `is_final=0` for prereleases. Prerelease identifiers
    split numeric and alpha segments so `rc0 < rc1 < ... < rc9 < rc10 < 1.0.0`.
    """
    if not isinstance(tag, str):
        return None
    m = SEMVER_TAG_REGEX.match(tag.strip())
    if not m:
        return None

    major = int(m.group("major"))
    minor = int(m.group("minor"))
    patch = int(m.group("patch"))
    pre = m.group("pre")
    if not pre:
        return (major, minor, patch, 1, ())

    pre_parts: List[Tuple[int, Union[int, str]]] = []
    for ident in re.split(r"[.-]+", pre):
        if not ident:
            continue
        for chunk in re.findall(r"\d+|[^\d]+", ident):
            if chunk.isdigit():
                pre_parts.append((0, int(chunk)))
            else:
                pre_parts.append((1, chunk.lower()))

    return (major, minor, patch, 0, tuple(pre_parts))


def _read_tag_records(repo_path: Path) -> List[Tuple[str, int]]:
    """Read `(tag_name, creatordate_unix)` pairs across all local git tags."""
    try:
        proc = subprocess.run(
            [
                "git",
                "for-each-ref",
                "--format=%(refname:short)\t%(creatordate:unix)",
                "refs/tags",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if proc.returncode != 0:
            return []
    except (OSError, subprocess.SubprocessError):
        return []

    records: List[Tuple[str, int]] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        name, _, ts_raw = line.partition("\t")
        name = name.strip()
        if not name:
            continue
        try:
            ts = int(ts_raw.strip()) if ts_raw.strip() else 0
        except ValueError:
            ts = 0
        records.append((name, ts))
    return records


def list_release_tags(
    repo_dir: Union[Path, str],
    semver_only: bool = False,
) -> List[str]:
    """
    List repository release tags sorted ascending by SemVer key (`creatordate` tie-breaker).

    Uses `git for-each-ref` so both lightweight commit tags and annotated tag objects
    are captured with consistent creator timestamps.
    """
    repo_path = Path(repo_dir).resolve()
    keyed: List[Tuple[Tuple[Any, ...], str]] = []
    for name, creator_ts in _read_tag_records(repo_path):
        sv = parse_semver_tag(name)
        if semver_only and sv is None:
            continue
        if sv is not None:
            sort_key: Tuple[Any, ...] = (1, sv, creator_ts, name)
        else:
            sort_key = (0, creator_ts, name)
        keyed.append((sort_key, name))

    keyed.sort(key=lambda item: item[0])
    return [name for _, name in keyed]


def get_tag_date(
    repo_dir: Union[Path, str],
    ref: str,
) -> Optional[str]:
    """
    Return the YYYY-MM-DD date of a tag via `for-each-ref` creatordate,
    falling back to commit author/committer date (`%cs`) via `git log -1`.
    """
    if not isinstance(ref, str):
        return None
    ref_s = ref.strip()
    if not ref_s or ref_s.startswith("-"):
        return None

    repo_path = Path(repo_dir).resolve()
    tag_short = ref_s[len("refs/tags/"):] if ref_s.startswith("refs/tags/") else ref_s
    try:
        proc = subprocess.run(
            [
                "git",
                "for-each-ref",
                "--format=%(refname:short)\t%(creatordate:short)",
                f"refs/tags/{tag_short}",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                name, _, date_str = line.partition("\t")
                if name.strip() == tag_short and date_str.strip():
                    return date_str.strip()
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%cs", f"{ref_s}^{{commit}}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if proc.returncode == 0:
            date_str = proc.stdout.strip()
            return date_str if date_str else None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _git_tags_query(repo_path: Path, args: List[str]) -> List[str]:
    """Execute a bounded `git tag` query returning stripped non-empty tag names."""
    try:
        proc = subprocess.run(
            ["git", "tag", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if proc.returncode != 0:
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        return []


def find_previous_tag(
    repo_dir: Union[Path, str],
    target_ref: str = "HEAD",
) -> Optional[str]:
    """
    Find the highest-precedence ancestor release tag prior to target_ref.

    Resolves `<target_ref>^{commit}`, inspects `git tag --merged` and
    `git tag --points-at`, excludes `target_ref` (and co-located tags with
    semver >= target_ref, or all co-located tags when target_ref is a non-tag
    such as HEAD sitting on a tag), and selects the highest SemVer remaining tag
    (falling back to `git describe --tags --abbrev=0` only when needed).
    """
    repo_path = Path(repo_dir).resolve()
    commit_sha = resolve_git_ref(repo_path, target_ref)
    if commit_sha is None:
        return None

    merged_tags = _git_tags_query(repo_path, ["--merged", commit_sha])
    co_located = set(_git_tags_query(repo_path, ["--points-at", commit_sha]))

    target_name = (
        target_ref[len("refs/tags/"):]
        if target_ref.startswith("refs/tags/")
        else target_ref
    ).strip()

    excluded = {target_name}
    if target_name in co_located:
        target_sv = parse_semver_tag(target_name)
        for tag in co_located:
            if tag == target_name:
                continue
            if target_sv is None:
                excluded.add(tag)
            else:
                tag_sv = parse_semver_tag(tag)
                if tag_sv is None or tag_sv >= target_sv:
                    excluded.add(tag)
    else:
        excluded.update(co_located)

    remaining = {tag for tag in merged_tags if tag not in excluded}
    if remaining:
        ordered = [
            tag for tag in list_release_tags(repo_path, semver_only=False)
            if tag in remaining
        ]
        semver_ordered = [tag for tag in ordered if parse_semver_tag(tag) is not None]
        if semver_ordered:
            return semver_ordered[-1]

        spec = f"{commit_sha}^" if co_located else commit_sha
        try:
            tag = subprocess.check_output(
                ["git", "describe", "--tags", "--abbrev=0", spec],
                cwd=repo_path,
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).strip()
            if tag and tag in remaining:
                return tag
        except (OSError, subprocess.SubprocessError):
            pass
        return ordered[-1] if ordered else None

    spec = f"{commit_sha}^" if co_located else commit_sha
    try:
        tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0", spec],
            cwd=repo_path,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        if tag and tag not in excluded:
            return tag
    except (OSError, subprocess.SubprocessError):
        pass
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


def _is_git_repository(repo_path: Path) -> bool:
    """Return True when `repo_path` resides inside a valid git repository."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


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


def _run_gh_upload(
    tag: str,
    asset_args: List[str],
    repo_path: Path,
) -> Optional[str]:
    """Upload release assets with `--clobber`; return error message on failure."""
    if not asset_args:
        return None
    upload_cmd = ["gh", "release", "upload", tag, *asset_args, "--clobber"]
    upload_res = subprocess.run(
        upload_cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if upload_res.returncode != 0:
        return f"Failed to upload assets for GitHub release {tag}: {upload_res.stderr.strip()}"
    return None


def _run_gh_edit(
    tag: str,
    tmp_path: Path,
    repo_path: Path,
    title: Optional[str],
    prerelease: Optional[bool],
) -> Tuple[bool, str]:
    """Update an existing GitHub release via `gh release edit`."""
    edit_cmd = ["gh", "release", "edit", tag, "--notes-file", str(tmp_path)]
    if title is not None:
        edit_cmd.extend(["--title", title])
    if prerelease is True:
        edit_cmd.append("--prerelease")
    elif prerelease is False:
        edit_cmd.append("--prerelease=false")

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


def sync_github_release(
    tag: str,
    notes_markdown: str,
    repo_dir: Union[Path, str] = ".",
    prerelease: Optional[bool] = None,
    title: Optional[str] = None,
    assets: Optional[List[Union[Path, str]]] = None,
) -> Tuple[bool, str]:
    """
    Create or edit a GitHub release using the GitHub CLI (`gh`).

    Writes notes to a temporary file and synchronizes with `gh release edit`
    or `gh release create`, handling asset uploads and race-safe collision fallback.
    """
    repo_path = Path(repo_dir).resolve()
    asset_args = [str(a) for a in assets] if assets else []

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".md") as tmp:
        tmp.write(notes_markdown)
        tmp_path = Path(tmp.name)

    try:
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
            upload_err = _run_gh_upload(tag, asset_args, repo_path)
            if upload_err:
                return False, upload_err
            return _run_gh_edit(tag, tmp_path, repo_path, title, prerelease)

        release_title = title or tag
        is_pre = prerelease
        if is_pre is None:
            tag_lower = tag.lower()
            is_pre = any(p in tag_lower for p in ("rc", "alpha", "beta", "dev"))

        create_cmd = [
            "gh",
            "release",
            "create",
            tag,
            *asset_args,
            "--title",
            release_title,
            "--notes-file",
            str(tmp_path),
        ]
        if is_pre:
            create_cmd.append("--prerelease")

        create_res = subprocess.run(
            create_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=30 if asset_args else 15,
        )
        if create_res.returncode == 0:
            return True, f"Successfully created GitHub release {tag}"

        err_combined = f"{create_res.stderr or ''}\n{create_res.stdout or ''}".lower()
        if any(tok in err_combined for tok in ("already exists", "release_already_exists", "422")):
            upload_err = _run_gh_upload(tag, asset_args, repo_path)
            if upload_err:
                return False, upload_err
            fallback_pre: Optional[bool] = (
                prerelease if prerelease is not None else (True if is_pre else None)
            )
            return _run_gh_edit(tag, tmp_path, repo_path, release_title, fallback_pre)

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
