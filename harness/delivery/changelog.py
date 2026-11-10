# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Native Keep-a-Changelog rendering, idempotent upsert, and tag backfill engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.delivery.release_notes import (
    CATEGORY_BREAKING,
    CATEGORY_DOCS,
    CATEGORY_FEATURES,
    CATEGORY_FIXES,
    CATEGORY_MAINTENANCE,
    SECTION_ORDER,
    collect_breaking_commits,
    collect_release_notes,
    find_previous_tag,
    format_section_bullets,
    get_repo_remote_url,
    get_tag_date,
    list_release_tags,
    parse_semver_tag,
    resolve_git_ref,
)

DEFAULT_CHANGELOG_PREAMBLE = (
    "# Changelog\n\n"
    "All notable changes to this project are documented in this file.\n\n"
    "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),\n"
    "and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).\n\n"
    "---"
)

KEEPACHANGELOG_MAP: Dict[str, str] = {
    CATEGORY_FEATURES: "Added",
    CATEGORY_FIXES: "Fixed",
    CATEGORY_DOCS: "Changed",
    CATEGORY_MAINTENANCE: "Changed",
}

KEEPACHANGELOG_ORDER: List[str] = ["Added", "Changed", "Fixed"]
_SECTION_HEADING_RE = re.compile(r"^##\s+\[(?P<label>[^\]]+)\](?:\s*-\s*.*)?$")
_REF_LINK_RE = re.compile(r"^\[(?P<label>[^\]]+)\]:\s*(?P<url>\S+)\s*$")


@dataclass
class ChangelogResult:
    """Structured result of changelog generation, upsert, or backfill."""

    version: str
    tag: str
    base_tag: Optional[str]
    release_date: Optional[str]
    repo_url: str
    compare_url: Optional[str]
    section_markdown: str
    document_markdown: str
    commits_count: int
    categories: Dict[str, List[Dict[str, Any]]]
    written: bool = False
    file_path: Optional[str] = None
    updated_versions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert ChangelogResult to JSON-serializable dictionary."""
        return asdict(self)


def normalize_changelog_version(tag: Optional[str]) -> str:
    """Normalize a tag/label (`Unreleased` preserved; `v1.0.0-rc5` -> `1.0.0-rc5`)."""
    if not tag or not tag.strip():
        return "Unreleased"
    cleaned = tag.strip()
    if cleaned.lower() == "unreleased" or cleaned == "HEAD":
        return "Unreleased"
    return re.sub(r"^[vV](?=\d)", "", cleaned)


def build_compare_url(repo_url: str, base_tag: Optional[str], target_ref: str) -> str:
    """Build a GitHub compare URL or commits fallback URL when base_tag is None."""
    norm = repo_url.rstrip("/")
    return f"{norm}/compare/{base_tag}...{target_ref}" if base_tag else f"{norm}/commits/{target_ref}"


def format_changelog_section(
    categories: Dict[str, List[Dict[str, Any]]],
    version: Optional[str],
    release_date: Optional[str] = None,
    style: str = "canonical",
) -> str:
    """Render categorized commits as a Keep-a-Changelog section (`canonical` or `keepachangelog`)."""
    style_norm = (style or "canonical").strip().lower()
    if style_norm not in ("canonical", "psl", "keepachangelog"):
        raise ValueError(f"Unsupported changelog style {style!r}; expected 'canonical' or 'keepachangelog'")

    norm_ver = normalize_changelog_version(version)
    if norm_ver == "Unreleased":
        heading = "## [Unreleased]"
    else:
        date_str = (
            release_date.strip()
            if release_date and release_date.strip()
            else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        heading = f"## [{norm_ver}] - {date_str}"

    sections_to_render: List[Tuple[str, List[Dict[str, Any]]]] = []
    breaking_items = collect_breaking_commits(categories)
    if breaking_items:
        sections_to_render.append((CATEGORY_BREAKING, breaking_items))

    if style_norm == "keepachangelog":
        grouped: Dict[str, List[Dict[str, Any]]] = {k: [] for k in KEEPACHANGELOG_ORDER}
        for sec in SECTION_ORDER:
            grouped[KEEPACHANGELOG_MAP.get(sec, "Changed")].extend(categories.get(sec, []))
        for k_title in KEEPACHANGELOG_ORDER:
            if grouped[k_title]:
                sections_to_render.append((k_title, grouped[k_title]))
    else:
        for sec in SECTION_ORDER:
            items = categories.get(sec, [])
            if items:
                sections_to_render.append((sec, items))

    lines: List[str] = [heading, ""]
    if not sections_to_render:
        lines.append("*No changes.*")
    else:
        for idx, (sec_title, sec_items) in enumerate(sections_to_render):
            if idx > 0:
                lines.append("")
            lines.append(f"### {sec_title}")
            lines.extend(format_section_bullets(sec_items))
    return "\n".join(lines).rstrip()


def _strip_trailing_section_separators(lines: List[str]) -> str:
    """Remove trailing blank lines and `---` thematic breaks from a parsed section."""
    trimmed = list(lines)
    while trimmed and (not trimmed[-1].strip() or trimmed[-1].strip() == "---"):
        trimmed.pop()
    return "\n".join(trimmed).rstrip()


def parse_changelog_document(content: str) -> Tuple[str, Dict[str, str], Dict[str, str]]:
    """Parse CHANGELOG.md into `(preamble, sections_by_version, links_by_version)`."""
    if not content:
        return "", {}, {}

    preamble_lines: List[str] = []
    sections: Dict[str, str] = {}
    links: Dict[str, str] = {}
    current_ver: Optional[str] = None
    current_lines: List[str] = []
    in_fence = False

    for line in content.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence

        if not in_fence:
            sec_m = _SECTION_HEADING_RE.match(line)
            if sec_m:
                if current_ver is not None:
                    sections[current_ver] = _strip_trailing_section_separators(current_lines)
                current_ver = normalize_changelog_version(sec_m.group("label"))
                current_lines = [line]
                continue

            link_m = _REF_LINK_RE.match(line)
            if link_m and current_ver is not None:
                links[normalize_changelog_version(link_m.group("label"))] = link_m.group("url").strip()
                continue

        if current_ver is None:
            preamble_lines.append(line)
        else:
            current_lines.append(line)

    if current_ver is not None:
        sections[current_ver] = _strip_trailing_section_separators(current_lines)
    return "\n".join(preamble_lines).rstrip(), sections, links


def _sort_changelog_keys(keys: List[str]) -> List[str]:
    """Sort changelog keys: `Unreleased` first, SemVer descending, then legacy keys."""
    deduped = list(dict.fromkeys(keys))
    ordered: List[str] = ["Unreleased"] if "Unreleased" in deduped else []
    semver_keys = [k for k in deduped if k != "Unreleased" and parse_semver_tag(k) is not None]
    semver_keys.sort(key=lambda k: parse_semver_tag(k) or (0, 0, 0, 0, ()), reverse=True)
    ordered.extend(semver_keys)
    ordered.extend(k for k in deduped if k != "Unreleased" and parse_semver_tag(k) is None)
    return ordered


def upsert_changelog_document(
    existing_content: Optional[str],
    updates: Dict[str, str],
    link_updates: Optional[Dict[str, str]] = None,
) -> str:
    """Idempotently merge section updates and reference links preserving preamble and historical sections."""
    if existing_content and existing_content.strip():
        preamble, sections, links = parse_changelog_document(existing_content)
        if not preamble:
            preamble = DEFAULT_CHANGELOG_PREAMBLE
    else:
        preamble, sections, links = DEFAULT_CHANGELOG_PREAMBLE, {}, {}

    for ver, body in updates.items():
        sections[normalize_changelog_version(ver)] = body.strip()

    if link_updates:
        for ver, url in link_updates.items():
            if url and url.strip():
                links[normalize_changelog_version(ver)] = url.strip()

    ordered_versions = _sort_changelog_keys(list(sections.keys()))
    section_blocks = [sections[v].strip() for v in ordered_versions if sections[v].strip()]
    parts = [preamble.rstrip()]
    if section_blocks:
        parts.append("\n\n---\n\n".join(section_blocks))
    doc = "\n\n".join(part for part in parts if part)

    if links:
        ordered_links = _sort_changelog_keys(list(links.keys()))
        link_lines = [f"[{k}]: {links[k]}" for k in ordered_links if links.get(k)]
        if link_lines:
            doc = f"{doc}\n\n" + "\n".join(link_lines)
    return doc.rstrip() + "\n"


def _find_latest_merged_tag(repo_path: Path, rev_ref: str) -> Optional[str]:
    """Find highest-precedence tag reachable from `rev_ref` (inclusive)."""
    rev_sha = resolve_git_ref(repo_path, rev_ref)
    if rev_sha is None:
        return None
    try:
        proc = subprocess.run(
            ["git", "tag", "--merged", rev_sha],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if proc.returncode != 0:
            return None
        merged = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    except (OSError, subprocess.SubprocessError):
        return None

    if not merged:
        return None
    ordered = [t for t in list_release_tags(repo_path, semver_only=False) if t in merged]
    semver_ordered = [t for t in ordered if parse_semver_tag(t) is not None]
    return semver_ordered[-1] if semver_ordered else (ordered[-1] if ordered else None)


def _resolve_changelog_file(repo_path: Path, changelog_path: Optional[Union[Path, str]]) -> Path:
    """Resolve target CHANGELOG.md path relative to `repo_path` when non-absolute."""
    if changelog_path is None:
        return (repo_path / "CHANGELOG.md").resolve()
    p = Path(changelog_path)
    return p.resolve() if p.is_absolute() else (repo_path / p).resolve()


def _write_if_changed(target_file: Path, new_content: str) -> None:
    """Write `new_content` only when file is missing or differs."""
    existing = target_file.read_text(encoding="utf-8") if target_file.exists() else None
    if existing == new_content:
        return
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(new_content, encoding="utf-8")


def generate_changelog(
    repo_dir: Union[Path, str] = ".",
    tag: Optional[str] = None,
    base_tag: Optional[str] = None,
    target_rev: Optional[str] = None,
    release_date: Optional[str] = None,
    repo_url: Optional[str] = None,
    style: str = "canonical",
    changelog_path: Optional[Union[Path, str]] = None,
    write: bool = False,
) -> ChangelogResult:
    """Generate a Keep-a-Changelog section and upserted document for `[Unreleased]` or a release tag."""
    repo_path = Path(repo_dir).resolve()
    target_file = _resolve_changelog_file(repo_path, changelog_path)
    norm_ver = normalize_changelog_version(tag)

    if norm_ver == "Unreleased":
        if target_rev is not None and resolve_git_ref(repo_path, target_rev) is None:
            raise ValueError(f"Invalid target revision ref: {target_rev!r}")
        effective_rev = target_rev if target_rev is not None else "HEAD"
        resolved_base = (
            base_tag if base_tag is not None else _find_latest_merged_tag(repo_path, effective_rev)
        )
        notes = collect_release_notes(
            repo_dir=repo_path,
            base_tag=resolved_base,
            target_ref="HEAD",
            repo_url=repo_url,
            target_rev=target_rev,
        )
        link_target = target_rev if target_rev is not None else "HEAD"
        resolved_date: Optional[str] = None
        display_tag = "Unreleased"
    else:
        assert tag is not None
        git_target_ref = tag.strip()
        if (
            target_rev is None
            and resolve_git_ref(repo_path, git_target_ref) is None
            and not git_target_ref.startswith(("v", "V"))
            and resolve_git_ref(repo_path, f"v{git_target_ref}") is not None
        ):
            git_target_ref = f"v{git_target_ref}"

        notes = collect_release_notes(
            repo_dir=repo_path,
            base_tag=base_tag,
            target_ref=git_target_ref,
            repo_url=repo_url,
            target_rev=target_rev,
        )
        resolved_date = (
            release_date.strip()
            if release_date and release_date.strip()
            else (get_tag_date(repo_path, git_target_ref) or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        )
        link_target = git_target_ref
        display_tag = git_target_ref

    compare_url = build_compare_url(notes.repo_url, notes.base_tag, link_target)
    section_md = format_changelog_section(
        categories=notes.categories,
        version=norm_ver,
        release_date=resolved_date,
        style=style,
    )
    existing_content = target_file.read_text(encoding="utf-8") if target_file.exists() else None
    document_md = upsert_changelog_document(
        existing_content=existing_content,
        updates={norm_ver: section_md},
        link_updates={norm_ver: compare_url},
    )

    written = False
    if write:
        _write_if_changed(target_file, document_md)
        written = True

    return ChangelogResult(
        version=norm_ver,
        tag=display_tag,
        base_tag=notes.base_tag,
        release_date=resolved_date,
        repo_url=notes.repo_url,
        compare_url=compare_url,
        section_markdown=section_md,
        document_markdown=document_md,
        commits_count=notes.commits_count,
        categories=notes.categories,
        written=written,
        file_path=str(target_file),
        updated_versions=[norm_ver],
    )


def backfill_changelog(
    repo_dir: Union[Path, str] = ".",
    changelog_path: Optional[Union[Path, str]] = None,
    repo_url: Optional[str] = None,
    style: str = "canonical",
    include_unreleased: bool = True,
    target_rev: Optional[str] = None,
    base_tag: Optional[str] = None,
    write: bool = False,
    overwrite_existing: bool = False,
) -> ChangelogResult:
    """Backfill missing SemVer release sections from git tags plus `[Unreleased]` idempotently."""
    repo_path = Path(repo_dir).resolve()
    if target_rev is not None and resolve_git_ref(repo_path, target_rev) is None:
        raise ValueError(f"Invalid target revision ref: {target_rev!r}")
    if base_tag is not None and resolve_git_ref(repo_path, base_tag) is None:
        raise ValueError(f"Invalid base ref: {base_tag!r}")

    target_file = _resolve_changelog_file(repo_path, changelog_path)
    resolved_repo_url = repo_url or get_repo_remote_url(repo_path)
    existing_content = target_file.read_text(encoding="utf-8") if target_file.exists() else None
    _, existing_sections, existing_links = (
        parse_changelog_document(existing_content) if existing_content else ("", {}, {})
    )

    tags = list_release_tags(repo_path, semver_only=True) or list_release_tags(repo_path, semver_only=False)
    section_updates: Dict[str, str] = {}
    link_updates: Dict[str, str] = {}
    updated_versions: List[str] = []

    for tag in tags:
        ver = normalize_changelog_version(tag)
        prev_tag = find_previous_tag(repo_path, tag)
        compare_url = build_compare_url(resolved_repo_url, prev_tag, tag)
        if ver not in existing_links or repo_url is not None or overwrite_existing:
            link_updates[ver] = compare_url
        if ver in existing_sections and not overwrite_existing:
            continue

        notes = collect_release_notes(
            repo_dir=repo_path,
            base_tag=prev_tag,
            target_ref=tag,
            repo_url=resolved_repo_url,
        )
        tag_date = get_tag_date(repo_path, tag) or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        section_updates[ver] = format_changelog_section(
            categories=notes.categories,
            version=ver,
            release_date=tag_date,
            style=style,
        )
        updated_versions.append(ver)

    unreleased_res: Optional[ChangelogResult] = None
    if include_unreleased:
        unreleased_res = generate_changelog(
            repo_dir=repo_path,
            tag=None,
            base_tag=base_tag,
            target_rev=target_rev,
            repo_url=resolved_repo_url,
            style=style,
            changelog_path=target_file,
            write=False,
        )
        section_updates["Unreleased"] = unreleased_res.section_markdown
        if unreleased_res.compare_url:
            link_updates["Unreleased"] = unreleased_res.compare_url
        updated_versions.insert(0, "Unreleased")

    document_md = upsert_changelog_document(
        existing_content=existing_content,
        updates=section_updates,
        link_updates=link_updates,
    )

    written = False
    if write:
        _write_if_changed(target_file, document_md)
        written = True

    return ChangelogResult(
        version="Unreleased" if include_unreleased else (updated_versions[-1] if updated_versions else ""),
        tag=unreleased_res.tag if unreleased_res else (tags[-1] if tags else "HEAD"),
        base_tag=unreleased_res.base_tag if unreleased_res else None,
        release_date=None,
        repo_url=resolved_repo_url,
        compare_url=unreleased_res.compare_url if unreleased_res else None,
        section_markdown=unreleased_res.section_markdown if unreleased_res else "",
        document_markdown=document_md,
        commits_count=unreleased_res.commits_count if unreleased_res else 0,
        categories=unreleased_res.categories if unreleased_res else {},
        written=written,
        file_path=str(target_file),
        updated_versions=updated_versions,
    )


__all__ = [
    "ChangelogResult",
    "DEFAULT_CHANGELOG_PREAMBLE",
    "KEEPACHANGELOG_MAP",
    "KEEPACHANGELOG_ORDER",
    "backfill_changelog",
    "build_compare_url",
    "format_changelog_section",
    "generate_changelog",
    "normalize_changelog_version",
    "parse_changelog_document",
    "upsert_changelog_document",
]
