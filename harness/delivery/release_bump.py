# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Unified single-command release bump & parity verification engine (`agyis release`)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from harness.delivery.changelog import (
    build_compare_url,
    format_changelog_section,
    generate_changelog,
    normalize_changelog_version,
    parse_changelog_document,
    upsert_changelog_document,
)
from harness.delivery.release_notes import (
    DEFAULT_REPO_URL,
    find_previous_tag,
    get_repo_remote_url,
    list_release_tags,
    parse_semver_tag,
    resolve_git_ref,
)
from harness.utils import theme

_SV = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
_SV_BADGE = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+?)?(?:\+[0-9A-Za-z.-]+)?"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

EXCLUDED_RELEASE_PATHS: Tuple[str, ...] = (
    "server/__init__.py",
    "website/data/manifest.json",
    "website/telemetry/telemetry.js",
    "harness/runtime/matrix.json",
    ".agyis/test_manifest.json",
    "docs/archive/",
)

_HTML_RULE_SPECS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(rf"(\bAgyis(?:\s+Harness)?\s+){_SV}\b"), r"\g<1>{ver}"),
    (re.compile(rf"(\bInstall\s+v){_SV}\b"), r"\g<1>{ver}"),
    (re.compile(rf"(\bVersion\s+){_SV}(\s+verification ledger\b)"), r"\g<1>{ver}\g<2>"),
    (re.compile(rf"(\bfrozen\s+v){_SV}(\s+wheel\b)"), r"\g<1>{ver}\g<2>"),
    (re.compile(rf"(\bView\s+v){_SV}(\s+release\b)"), r"\g<1>{ver}\g<2>"),
    (re.compile(rf"(\bfor\s+v){_SV}(\s+release\s+links\b)"), r"\g<1>{ver}\g<2>"),
    (re.compile(rf"(/releases/tag/v){_SV}\b"), r"\g<1>{ver}"),
)

_OG_SVG_RULE = (
    re.compile(rf"(\bVersion\s+){_SV}(\s*(?:·|&#183;|&middot;)\s*agyis-harness\.io)"),
    r"\g<1>{ver}\g<2>",
)

_DOC_RULE_SPECS: Tuple[Tuple[str, str, Tuple[Tuple[re.Pattern[str], str], ...]], ...] = (
    ("README.md", "docs", (
        (re.compile(rf"(badge/Version-v){_SV_BADGE}(-[A-Za-z0-9_]+\.svg)"), r"\g<1>{ver}\g<2>"),
        (re.compile(rf"(/releases/tag/v){_SV}\b"), r"\g<1>{ver}"),
        (re.compile(rf"(GA\s*->\s*`v){_SV}(`)"), r"\g<1>{ver}\g<2>"),
        (re.compile(rf"(Post-`v){_SV}(`)"), r"\g<1>{ver}\g<2>"),
    )),
    ("roadmap.md", "docs", (
        (re.compile(rf"(\*\*Last Updated\*\*:\s*)\d{{4}}-\d{{2}}-\d{{2}}(\s*\(`v){_SV}(`\))"), r"\g<1>{date}\g<2>{ver}\g<3>"),
        (re.compile(rf"(^##\s+3\.\s+Completed Baseline\s*\(`v){_SV}(`)", re.M), r"\g<1>{ver}\g<2>"),
        (re.compile(rf"(^##\s+4\.\s+Post-`v){_SV}(`)", re.M), r"\g<1>{ver}\g<2>"),
    )),
    ("docs/taxonomy/project-ledger.md", "docs", (
        (re.compile(rf"(^#\s+Agyis Harness Project Ledger\s*\(`v){_SV}(`)", re.M), r"\g<1>{ver}\g<2>"),
        (re.compile(rf"(^##\s+1\.\s+Current Release Baseline\s*\(`v){_SV}(`\s*[—-]\s*)\d{{4}}-\d{{2}}-\d{{2}}(\))", re.M), r"\g<1>{ver}\g<2>{date}\g<3>"),
    )),
    ("docs/user_guide.md", "docs", (
        (re.compile(rf"(\*\*Version\*\*:\s*`){_SV}(`\s*\(`?)\d{{4}}-\d{{2}}-\d{{2}}(`?\))"), r"\g<1>{ver}\g<2>{date}\g<3>"),
    )),
    ("docs/developer_guide.md", "docs", (
        (re.compile(rf"(\*\*Version\*\*:\s*`){_SV}(`\s*\(`?)\d{{4}}-\d{{2}}-\d{{2}}(`?\))"), r"\g<1>{ver}\g<2>{date}\g<3>"),
    )),
    ("docs/official-specs/cli-palette.md", "docs", (
        (re.compile(rf"(\*\*Last Updated\*\*:\s*)\d{{4}}-\d{{2}}-\d{{2}}(\s*\(`v){_SV}(`\))"), r"\g<1>{date}\g<2>{ver}\g<3>"),
    )),
    ("docs/official-specs/cockpit-director.md", "docs", (
        (re.compile(rf"(\bagyis-harness\s+v){_SV}\b"), r"\g<1>{ver}"),
    )),
    ("docs/official-specs/testing-contracts.md", "docs", (
        (re.compile(rf"(\*\*Last Updated\*\*:\s*)\d{{4}}-\d{{2}}-\d{{2}}(\s*\(`v){_SV}(`\))"), r"\g<1>{date}\g<2>{ver}\g<3>"),
    )),
    ("docs/official-specs/platform-surface-mapping.md", "docs", (
        (re.compile(rf'("name"\s*:\s*"agyis-harness"[\s\S]{{0,240}}?"version"\s*:\s*"){_SV}(")'), r"\g<1>{ver}\g<2>"),
    )),
    ("docs/runbooks/repo-onboarding.md", "docs", (
        (re.compile(r"(^last_updated:\s*)\d{4}-\d{2}-\d{2}", re.M), r"\g<1>{date}"),
        (re.compile(rf"(\|\s*\*\*Agyis Harness\*\*\s*\|\s*`){_SV}(`\s*\|)"), r"\g<1>{ver}\g<2>"),
    )),
    ("docs/adr/README.md", "docs", (
        (re.compile(r"(^\*\*Last Updated\*\*:\s*)\d{4}-\d{2}-\d{2}", re.M), r"\g<1>{date}"),
    )),
    (".github/ISSUE_TEMPLATE/bug_report.yml", "issue_template", (
        (re.compile(rf'(placeholder:\s*"e\.g\.,\s*){_SV}(\s+or\s+)'), r"\g<1>{ver}\g<2>"),
    )),
    (".github/ISSUE_TEMPLATE/feature_request.yml", "issue_template", (
        (re.compile(rf'(placeholder:\s*"e\.g\.,\s*){_SV}(\s+or\s+)'), r"\g<1>{ver}\g<2>"),
    )),
)

_DOC_VERSION_EXTRACTORS: Tuple[Tuple[str, Tuple[re.Pattern[str], ...]], ...] = (
    ("README.md", (re.compile(rf"badge/Version-v(?P<ver>{_SV_BADGE})(?=-[A-Za-z0-9_]+\.svg)"), re.compile(rf"/releases/tag/v(?P<ver>{_SV})\b"))),
    ("roadmap.md", (re.compile(rf"\*\*Last Updated\*\*:\s*\d{{4}}-\d{{2}}-\d{{2}}\s*\(`v(?P<ver>{_SV})`\)"), re.compile(rf"^##\s+3\.\s+Completed Baseline\s*\(`v(?P<ver>{_SV})`", re.M))),
    ("docs/taxonomy/project-ledger.md", (re.compile(rf"^#\s+Agyis Harness Project Ledger\s*\(`v(?P<ver>{_SV})`", re.M), re.compile(rf"^##\s+1\.\s+Current Release Baseline\s*\(`v(?P<ver>{_SV})`", re.M))),
    ("docs/user_guide.md", (re.compile(rf"\*\*Version\*\*:\s*`(?P<ver>{_SV})`"),)),
    ("docs/developer_guide.md", (re.compile(rf"\*\*Version\*\*:\s*`(?P<ver>{_SV})`"),)),
    ("docs/official-specs/cli-palette.md", (re.compile(rf"\*\*Last Updated\*\*:\s*\d{{4}}-\d{{2}}-\d{{2}}\s*\(`v(?P<ver>{_SV})`\)"),)),
    ("docs/official-specs/cockpit-director.md", (re.compile(rf"\bagyis-harness\s+v(?P<ver>{_SV})\b"),)),
    ("docs/official-specs/testing-contracts.md", (re.compile(rf"\*\*Last Updated\*\*:\s*\d{{4}}-\d{{2}}-\d{{2}}\s*\(`v(?P<ver>{_SV})`\)"),)),
    ("docs/official-specs/platform-surface-mapping.md", (re.compile(rf'"name"\s*:\s*"agyis-harness"[\s\S]{{0,240}}?"version"\s*:\s*"(?P<ver>{_SV})"'),)),
    ("docs/runbooks/repo-onboarding.md", (re.compile(rf"\|\s*\*\*Agyis Harness\*\*\s*\|\s*`(?P<ver>{_SV})`\s*\|"),)),
    (".github/ISSUE_TEMPLATE/bug_report.yml", (re.compile(rf'placeholder:\s*"e\.g\.,\s*(?P<ver>{_SV})\s+or\s+'),)),
    (".github/ISSUE_TEMPLATE/feature_request.yml", (re.compile(rf'placeholder:\s*"e\.g\.,\s*(?P<ver>{_SV})\s+or\s+'),)),
)


@dataclass
class ReleaseFileEdit:
    """Single planned or applied text surface edit."""

    path: str
    category: str
    changed: bool
    replacements: int
    original_text: str = field(repr=False)
    updated_text: str = field(repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize edit metadata without raw file bodies."""
        return {"path": self.path, "category": self.category, "changed": self.changed, "replacements": self.replacements}


@dataclass
class ReleaseActionStatus:
    """Status of an external release command action (`uv_lock`, `og_raster`)."""

    name: str
    status: str
    reason: Optional[str] = None
    commands: List[List[str]] = field(default_factory=list)
    targets: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize external action metadata."""
        return asdict(self)


@dataclass
class ReleaseBumpPlan:
    """In-memory deterministic plan for a release version bump."""

    version: str
    tag: str
    release_date: str
    workspace: str
    repo_url: str
    dry_run: bool = True
    edits: List[ReleaseFileEdit] = field(default_factory=list)
    actions: List[ReleaseActionStatus] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    skipped_files: List[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return any(edit.changed for edit in self.edits)

    @property
    def changed_files(self) -> List[str]:
        return [edit.path for edit in self.edits if edit.changed]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "tag": self.tag,
            "release_date": self.release_date,
            "workspace": self.workspace,
            "repo_url": self.repo_url,
            "dry_run": self.dry_run,
            "changed": self.changed,
            "changed_count": len(self.changed_files),
            "changed_files": self.changed_files,
            "edits": [e.to_dict() for e in self.edits],
            "actions": [a.to_dict() for a in self.actions],
            "warnings": list(self.warnings),
            "skipped_files": list(self.skipped_files),
        }


@dataclass
class ReleaseBumpResult:
    """Structured result returned by `apply_release_bump` (dry-run or applied)."""

    version: str
    tag: str
    release_date: str
    workspace: str
    repo_url: str
    dry_run: bool
    applied: bool
    changed: bool
    changed_files: List[str]
    written_files: List[str]
    edits: List[ReleaseFileEdit]
    actions: List[ReleaseActionStatus]
    warnings: List[str]
    skipped_files: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "tag": self.tag,
            "release_date": self.release_date,
            "workspace": self.workspace,
            "repo_url": self.repo_url,
            "dry_run": self.dry_run,
            "applied": self.applied,
            "changed": self.changed,
            "changed_count": len(self.changed_files),
            "changed_files": list(self.changed_files),
            "written_files": list(self.written_files),
            "edits": [e.to_dict() for e in self.edits],
            "actions": [a.to_dict() for a in self.actions],
            "warnings": list(self.warnings),
            "skipped_files": list(self.skipped_files),
        }


def normalize_release_version(raw_version: str) -> str:
    """Validate and normalize a SemVer release string (stripping optional leading `v`)."""
    if not isinstance(raw_version, str):
        raise ValueError(f"Release version must be a string, got {type(raw_version).__name__}")
    cleaned = raw_version.strip()
    if not cleaned or parse_semver_tag(cleaned) is None:
        raise ValueError(f"Invalid SemVer release version: {raw_version!r} (expected MAJOR.MINOR.PATCH[-pre][+build])")
    return cleaned[1:] if cleaned[0] in ("v", "V") else cleaned


def _resolve_release_date(release_date: Optional[str]) -> Tuple[str, bool]:
    """Validate optional YYYY-MM-DD release date or return today's UTC date."""
    if release_date is None or not str(release_date).strip():
        return datetime.now(timezone.utc).strftime("%Y-%m-%d"), False
    cleaned = str(release_date).strip()
    if not _DATE_RE.match(cleaned):
        raise ValueError(f"Invalid --date format {release_date!r}; expected YYYY-MM-DD")
    try:
        datetime.strptime(cleaned, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid calendar date {release_date!r}: {exc}") from exc
    return cleaned, True


def _is_excluded_path(rel_posix: str) -> bool:
    """Check whether a workspace-relative POSIX path is strictly excluded from release mutations."""
    norm = rel_posix.lstrip("./")
    return any(norm.startswith(e) if e.endswith("/") else norm == e for e in EXCLUDED_RELEASE_PATHS)


def _apply_rules_counting_changes(text: str, rules: Sequence[Tuple[re.Pattern[str], str]]) -> Tuple[str, int]:
    """Apply regex substitutions sequentially and count only occurrences that actually mutate text."""
    updated = text
    changed_hits = 0
    for pattern, repl_tmpl in rules:
        def _sub_fn(match: re.Match[str], tmpl: str = repl_tmpl) -> str:
            nonlocal changed_hits
            replacement = match.expand(tmpl)
            if replacement != match.group(0):
                changed_hits += 1
            return replacement
        updated = pattern.sub(_sub_fn, updated)
    return updated, changed_hits


def _atomic_write_text(target: Path, content: str) -> None:
    """Atomically replace `target` with UTF-8 `content`, preserving existing file mode."""
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = target.stat().st_mode & 0o777 if target.exists() else None
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        if mode is not None:
            os.chmod(tmp_path, mode)
        os.replace(tmp_path, target)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _update_pyproject_version(raw: str, version: str) -> Tuple[str, int]:
    """Update `[project].version` inside `pyproject.toml`, failing if unreadable or missing."""
    try:
        parsed = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Malformed pyproject.toml: {exc}") from exc
    proj = parsed.get("project") if isinstance(parsed, dict) else None
    if not isinstance(proj, dict) or not isinstance(proj.get("version"), str):
        raise ValueError("pyproject.toml is missing [project].version")

    in_project = False
    replaced = 0
    ver_re = re.compile(r'^(\s*version\s*=\s*")([^"]+)(")')
    out: List[str] = []
    for line in raw.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and not stripped.startswith("[["):
            in_project = stripped == "[project]"
        elif in_project and replaced == 0:
            m = ver_re.match(line)
            if m:
                if m.group(2) != version:
                    line = ver_re.sub(rf"\g<1>{version}\g<3>", line, count=1)
                    replaced = 1
                else:
                    replaced = -1
        out.append(line)
    if replaced == 0:
        raise ValueError("Unable to locate [project] version line in pyproject.toml")
    return "".join(out), (1 if replaced == 1 else 0)


def _update_json_manifest_version(raw: str, version: str, rel_path: str) -> Tuple[str, int]:
    """Validate a JSON manifest and replace its top-level `"version"` preserving formatting."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Malformed JSON manifest {rel_path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("version"), str):
        raise ValueError(f"Manifest {rel_path} is missing string 'version' field")
    pat = re.compile(r'("version"\s*:\s*")([^"]+)(")')
    m = pat.search(raw)
    if not m:
        raise ValueError(f"Unable to locate '\"version\"' key in {rel_path}")
    if m.group(2) == version:
        return raw, 0
    return pat.sub(rf"\g<1>{version}\g<3>", raw, count=1), 1


def _plan_manifest_edits(root: Path, version: str, skipped: List[str]) -> List[ReleaseFileEdit]:
    """Plan version updates across core manifests (`pyproject.toml`, `harness/__init__.py`, `plugin.json`, `package.json`)."""
    edits: List[ReleaseFileEdit] = []
    py_path = root / "pyproject.toml"
    if py_path.is_file():
        orig = py_path.read_text(encoding="utf-8")
        upd, count = _update_pyproject_version(orig, version)
        edits.append(ReleaseFileEdit("pyproject.toml", "manifest", upd != orig, count, orig, upd))
    else:
        skipped.append("pyproject.toml")

    init_path = root / "harness" / "__init__.py"
    if init_path.is_file():
        orig = init_path.read_text(encoding="utf-8")
        init_re = re.compile(r'^(__version__\s*=\s*["\'])([^"\']+)(["\'])', re.M)
        if not init_re.search(orig):
            raise ValueError("harness/__init__.py is missing __version__ assignment")
        upd, count = _apply_rules_counting_changes(orig, ((init_re, rf"\g<1>{version}\g<3>"),))
        edits.append(ReleaseFileEdit("harness/__init__.py", "manifest", upd != orig, count, orig, upd))
    else:
        skipped.append("harness/__init__.py")

    for rel_json in ("plugin.json", "package.json"):
        jpath = root / rel_json
        if jpath.is_file():
            orig = jpath.read_text(encoding="utf-8")
            upd, count = _update_json_manifest_version(orig, version, rel_json)
            edits.append(ReleaseFileEdit(rel_json, "manifest", upd != orig, count, orig, upd))
        else:
            skipped.append(rel_json)
    return edits


def _find_prev_tag_before_version(root: Path, version: str, existing_sections: Dict[str, str]) -> Optional[str]:
    """Find highest SemVer predecessor tag `< version` via git tags or existing changelog sections."""
    target_sv = parse_semver_tag(version)
    tag_name = f"v{version}"
    if resolve_git_ref(root, tag_name) is not None:
        prev = find_previous_tag(root, tag_name)
        if prev:
            return prev
    if resolve_git_ref(root, "HEAD") is not None:
        candidates = [
            t for t in list_release_tags(root, semver_only=True)
            if (sv := parse_semver_tag(t)) is not None and (target_sv is None or sv < target_sv)
        ]
        if candidates:
            return candidates[-1]
    sec_versions = [
        k for k in existing_sections
        if k != "Unreleased" and (sv := parse_semver_tag(k)) is not None and (target_sv is None or sv < target_sv)
    ]
    if sec_versions:
        sec_versions.sort(key=lambda k: parse_semver_tag(k) or (0, 0, 0, 0, ()))
        return f"v{sec_versions[-1]}"
    return None


def _infer_repo_url(root: Path, repo_url: Optional[str], existing_links: Dict[str, str]) -> str:
    """Resolve GitHub repository URL from override, existing changelog links, git remote, or default."""
    if repo_url and repo_url.strip():
        return repo_url.strip().rstrip("/")
    for url in existing_links.values():
        m = re.match(r"^(https?://[^/\s]+/[^/\s]+/[^/\s]+?)/(?:compare|commits|releases)/", url)
        if m:
            return m.group(1)
    try:
        return get_repo_remote_url(root).rstrip("/")
    except (OSError, ValueError, RuntimeError):
        return DEFAULT_REPO_URL


def _plan_changelog_edit(
    root: Path, version: str, release_date: str, explicit_date: bool, repo_url: Optional[str], skipped: List[str]
) -> Tuple[Optional[ReleaseFileEdit], str]:
    """Plan Keep-a-Changelog upsert inserting `## [<version>]` and clean `## [Unreleased]`."""
    cl_path = root / "CHANGELOG.md"
    if not cl_path.is_file():
        skipped.append("CHANGELOG.md")
        return None, _infer_repo_url(root, repo_url, {})

    existing_text = cl_path.read_text(encoding="utf-8")
    _, existing_sections, existing_links = parse_changelog_document(existing_text)
    resolved_repo_url = _infer_repo_url(root, repo_url, existing_links)
    prev_tag = _find_prev_tag_before_version(root, version, existing_sections)
    tag_name = f"v{version}"

    if version in existing_sections:
        section_md = existing_sections[version]
        if explicit_date:
            heading_re = re.compile(rf"^(##\s+\[{re.escape(version)}\]\s*-\s*)\d{{4}}-\d{{2}}-\d{{2}}", re.M)
            section_md = heading_re.sub(rf"\g<1>{release_date}", section_md, count=1)
        ver_compare_url = existing_links.get(version) or build_compare_url(resolved_repo_url, prev_tag, tag_name)
    else:
        target_rev = "HEAD" if resolve_git_ref(root, tag_name) is None else None
        git_base = prev_tag if (prev_tag and resolve_git_ref(root, prev_tag) is not None) else None
        try:
            gen = generate_changelog(
                repo_dir=root, tag=tag_name, base_tag=git_base, target_rev=target_rev,
                release_date=release_date, repo_url=resolved_repo_url, write=False,
            )
            section_md = gen.section_markdown
            resolved_repo_url = gen.repo_url.rstrip("/")
            ver_compare_url = gen.compare_url or build_compare_url(resolved_repo_url, prev_tag, tag_name)
        except (ValueError, RuntimeError):
            unreleased_body = existing_sections.get("Unreleased", "")
            unreleased_lines = [ln for ln in unreleased_body.splitlines()[1:] if ln.strip() and ln.strip() != "*No changes.*"]
            if unreleased_lines:
                section_md = f"## [{version}] - {release_date}\n\n" + "\n".join(unreleased_lines).strip()
            else:
                section_md = format_changelog_section({}, version=version, release_date=release_date)
            ver_compare_url = build_compare_url(resolved_repo_url, prev_tag, tag_name)

    updated_text = upsert_changelog_document(
        existing_content=existing_text,
        updates={"Unreleased": "## [Unreleased]\n\n*No changes.*", version: section_md},
        link_updates={"Unreleased": build_compare_url(resolved_repo_url, tag_name, "HEAD"), version: ver_compare_url},
    )
    changed = updated_text != existing_text
    return ReleaseFileEdit("CHANGELOG.md", "changelog", changed, 1 if changed else 0, existing_text, updated_text), resolved_repo_url


def _plan_website_and_doc_edits(
    root: Path, version: str, release_date: str, skip_og: bool, skipped: List[str]
) -> List[ReleaseFileEdit]:
    """Plan release version/date updates across OG SVG, all website HTML routes, docs, and issue templates."""
    edits: List[ReleaseFileEdit] = []
    og_rel = "website/brand/svg/og-overlay.svg"
    og_path = root / og_rel
    if skip_og or not og_path.is_file():
        skipped.append(og_rel)
    else:
        orig = og_path.read_text(encoding="utf-8")
        pat, tmpl = _OG_SVG_RULE
        upd, count = _apply_rules_counting_changes(orig, ((pat, tmpl.format(ver=version)),))
        edits.append(ReleaseFileEdit(og_rel, "og_svg", upd != orig, count, orig, upd))

    website_dir = root / "website"
    if website_dir.is_dir():
        html_rules = tuple((pat, tmpl.format(ver=version)) for pat, tmpl in _HTML_RULE_SPECS)
        for html_file in sorted(website_dir.rglob("*.html")):
            rel_posix = html_file.relative_to(root).as_posix()
            if _is_excluded_path(rel_posix):
                continue
            orig = html_file.read_text(encoding="utf-8")
            upd, count = _apply_rules_counting_changes(orig, html_rules)
            edits.append(ReleaseFileEdit(rel_posix, "website", upd != orig, count, orig, upd))

    for rel_posix, category, spec_rules in _DOC_RULE_SPECS:
        if _is_excluded_path(rel_posix):
            continue
        target = root / rel_posix
        if not target.is_file():
            skipped.append(rel_posix)
            continue
        orig = target.read_text(encoding="utf-8")
        compiled_rules = tuple((pat, tmpl.format(ver=version, date=release_date)) for pat, tmpl in spec_rules)
        upd, count = _apply_rules_counting_changes(orig, compiled_rules)
        edits.append(ReleaseFileEdit(rel_posix, category, upd != orig, count, orig, upd))
    return edits


def _plan_external_actions(root: Path, *, skip_lock: bool, skip_og: bool, warnings: List[str]) -> List[ReleaseActionStatus]:
    """Plan external toolchain actions (`uv lock` and `rsvg-convert`/`magick` OG raster recomposition)."""
    actions: List[ReleaseActionStatus] = []
    if skip_lock:
        actions.append(ReleaseActionStatus("uv_lock", "skipped", reason="--skip-lock"))
    elif not (root / "pyproject.toml").is_file():
        actions.append(ReleaseActionStatus("uv_lock", "skipped", reason="pyproject.toml absent"))
    elif shutil.which("uv") is None:
        warnings.append("Skipping uv lock: 'uv' binary not found on PATH")
        actions.append(ReleaseActionStatus("uv_lock", "skipped", reason="uv binary not found"))
    else:
        actions.append(ReleaseActionStatus("uv_lock", "planned", commands=[["uv", "lock"]], targets=["uv.lock"]))

    backdrop = root / "website" / "assets" / "art" / "og-backdrop-1-0.png"
    overlay_svg = root / "website" / "brand" / "svg" / "og-overlay.svg"
    if skip_og:
        actions.append(ReleaseActionStatus("og_raster", "skipped", reason="--skip-og"))
    elif not (backdrop.is_file() and overlay_svg.is_file()):
        actions.append(ReleaseActionStatus("og_raster", "skipped", reason="OG backdrop or overlay SVG absent"))
    else:
        missing_bins = [b for b in ("rsvg-convert", "magick") if shutil.which(b) is None]
        if missing_bins:
            msg = f"Skipping OG raster recomposition: missing binary ({', '.join(missing_bins)})"
            warnings.append(msg)
            actions.append(ReleaseActionStatus("og_raster", "skipped", reason=msg))
        else:
            actions.append(ReleaseActionStatus(
                "og_raster", "planned",
                commands=[
                    ["rsvg-convert", "-w", "1200", "-h", "630", "website/brand/svg/og-overlay.svg", "-o", "<tmp>/overlay.png"],
                    ["magick", "website/assets/art/og-backdrop-1-0.png", "-resize", "1200x630^", "-gravity", "center", "-extent", "1200x630", "<tmp>/overlay.png", "-composite", "website/assets/og-image.png"],
                    ["magick", "website/assets/og-image.png", "-quality", "90", "website/assets/og-image.webp"],
                ],
                targets=["website/assets/og-image.png", "website/assets/og-image.webp"],
            ))
    return actions


def _execute_planned_actions(root: Path, actions: List[ReleaseActionStatus]) -> None:
    """Execute planned external commands (`uv lock`, OG raster recomposition) during `--apply`."""
    for action in actions:
        if action.status != "planned":
            continue
        if action.name == "uv_lock":
            proc = subprocess.run(["uv", "lock"], cwd=root, capture_output=True, text=True, check=False, timeout=120)
            if proc.returncode != 0:
                raise RuntimeError(f"'uv lock' failed with exit code {proc.returncode}: {(proc.stderr or proc.stdout or '').strip()}")
            action.status = "executed"
        elif action.name == "og_raster":
            backdrop = root / "website" / "assets" / "art" / "og-backdrop-1-0.png"
            overlay_svg = root / "website" / "brand" / "svg" / "og-overlay.svg"
            out_png = root / "website" / "assets" / "og-image.png"
            out_webp = root / "website" / "assets" / "og-image.webp"
            out_png.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_overlay = Path(tmp_dir) / "og-overlay.png"
                cmds = [
                    ["rsvg-convert", "-w", "1200", "-h", "630", str(overlay_svg), "-o", str(tmp_overlay)],
                    ["magick", str(backdrop), "-resize", "1200x630^", "-gravity", "center", "-extent", "1200x630", str(tmp_overlay), "-composite", str(out_png)],
                    ["magick", str(out_png), "-quality", "90", str(out_webp)],
                ]
                for cmd in cmds:
                    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False, timeout=60)
                    if proc.returncode != 0:
                        raise RuntimeError(f"OG raster command {cmd[0]!r} failed (rc={proc.returncode}): {(proc.stderr or proc.stdout or '').strip()}")
            action.status = "executed"


def plan_release_bump(
    workspace: Union[Path, str],
    version: str,
    *,
    release_date: Optional[str] = None,
    repo_url: Optional[str] = None,
    skip_og: bool = False,
    skip_lock: bool = False,
    skip_changelog: bool = False,
) -> ReleaseBumpPlan:
    """Compute a complete in-memory release bump plan with zero filesystem mutations."""
    root = Path(workspace).resolve()
    norm_ver = normalize_release_version(version)
    resolved_date, explicit_date = _resolve_release_date(release_date)
    skipped: List[str] = []
    warnings: List[str] = []

    edits: List[ReleaseFileEdit] = _plan_manifest_edits(root, norm_ver, skipped)
    if skip_changelog:
        skipped.append("CHANGELOG.md")
        resolved_repo_url = _infer_repo_url(root, repo_url, {})
    else:
        cl_edit, resolved_repo_url = _plan_changelog_edit(root, norm_ver, resolved_date, explicit_date, repo_url, skipped)
        if cl_edit is not None:
            edits.append(cl_edit)

    edits.extend(_plan_website_and_doc_edits(root, norm_ver, resolved_date, skip_og, skipped))
    actions = _plan_external_actions(root, skip_lock=skip_lock, skip_og=skip_og, warnings=warnings)
    return ReleaseBumpPlan(
        version=norm_ver, tag=f"v{norm_ver}", release_date=resolved_date, workspace=str(root),
        repo_url=resolved_repo_url, dry_run=True, edits=edits, actions=actions,
        warnings=warnings, skipped_files=skipped,
    )


def apply_release_bump(
    workspace: Union[Path, str],
    version: str,
    *,
    apply: bool = False,
    release_date: Optional[str] = None,
    repo_url: Optional[str] = None,
    skip_og: bool = False,
    skip_lock: bool = False,
    skip_changelog: bool = False,
) -> ReleaseBumpResult:
    """Plan and optionally atomically apply a release version bump across all target surfaces."""
    root = Path(workspace).resolve()
    plan = plan_release_bump(
        root, version, release_date=release_date, repo_url=repo_url,
        skip_og=skip_og, skip_lock=skip_lock, skip_changelog=skip_changelog,
    )
    written_files: List[str] = []
    if apply:
        for edit in plan.edits:
            if edit.changed:
                _atomic_write_text(root / edit.path, edit.updated_text)
                written_files.append(edit.path)
        _execute_planned_actions(root, plan.actions)

    return ReleaseBumpResult(
        version=plan.version, tag=plan.tag, release_date=plan.release_date, workspace=plan.workspace,
        repo_url=plan.repo_url, dry_run=not apply, applied=apply, changed=plan.changed,
        changed_files=plan.changed_files, written_files=written_files, edits=plan.edits,
        actions=plan.actions, warnings=plan.warnings, skipped_files=plan.skipped_files,
    )


def check_release_parity(
    workspace: Union[Path, str] = ".",
    *,
    version: Optional[str] = None,
    include_site: bool = True,
) -> Dict[str, Any]:
    """Validate release version parity across manifests, uv.lock, OG SVG, CHANGELOG, docs, and site."""
    root = Path(workspace).resolve()
    expected_ver = normalize_release_version(version) if version is not None else None
    sync_mod = importlib.import_module("harness.delivery.sync_check")
    sync_report = sync_mod.run_sync_check(workspace_root=root, include_site=include_site)

    mismatches: List[str] = list(sync_report.get("mismatches") or [])
    manifest = dict(sync_report.get("manifest") or {})
    py_ver = manifest.get("pyproject_version")
    if expected_ver is None:
        expected_ver = py_ver or manifest.get("harness_init_version") or manifest.get("plugin_version")
    elif py_ver and py_ver != expected_ver:
        mismatches.append(f"Expected version '{expected_ver}' != pyproject.toml '{py_ver}'")

    changelog_has_version: Optional[bool] = None
    cl_path = root / "CHANGELOG.md"
    if cl_path.is_file() and expected_ver:
        _, sections, _ = parse_changelog_document(cl_path.read_text(encoding="utf-8", errors="replace"))
        norm_expected = normalize_changelog_version(expected_ver)
        changelog_has_version = norm_expected in sections
        if not changelog_has_version:
            mismatches.append(f"CHANGELOG.md missing release section '## [{norm_expected}]'")

    if expected_ver:
        for rel_doc, patterns in _DOC_VERSION_EXTRACTORS:
            doc_path = root / rel_doc
            if not doc_path.is_file():
                continue
            text = doc_path.read_text(encoding="utf-8", errors="replace")
            for pat in patterns:
                for m in pat.finditer(text):
                    found = m.group("ver").strip()
                    if found != expected_ver:
                        mismatches.append(f"{rel_doc} claims version '{found}' != expected '{expected_ver}'")

    return {
        "status": "PASS" if not mismatches else "FAIL",
        "version": expected_ver,
        "workspace": str(root),
        "include_site": include_site,
        "manifest": manifest,
        "changelog_has_version": changelog_has_version,
        "sync_check": sync_report,
        "mismatches": mismatches,
    }


def format_release_bump_report(result: ReleaseBumpResult) -> str:
    """Format terminal report for `agyis release bump`."""
    mode_label = "DRY-RUN" if result.dry_run else "APPLIED"
    lines = [
        theme.banner(f"Agyis Release Bump ({result.tag})", badge_label=mode_label, status="INFO" if result.dry_run else "PASS"),
        f" Version:   {result.version} ({result.release_date})",
        f" Workspace: {result.workspace}",
        f" Changed:   {len(result.changed_files)} file(s) ({len(result.written_files)} written)",
        theme.rule(),
    ]
    if result.changed_files:
        verb = "WRITE" if result.applied else "PLAN "
        lines.extend(f"  [{verb}] {e.path} ({e.category}, {e.replacements} update(s))" for e in result.edits if e.changed)
    else:
        lines.append(" " + theme.badge("PASS", "No pending text changes (already synchronized)."))
    if result.actions:
        lines.append(theme.rule())
        lines.extend(f"  [ACTION:{a.status.upper()}] {a.name}{' — ' + a.reason if a.reason else ''}" for a in result.actions)
    lines.extend(" " + theme.badge("WARN", w) for w in result.warnings)
    lines.append(theme.rule("━"))
    return "\n".join(lines)


def format_release_check_report(report: Dict[str, Any]) -> str:
    """Format terminal report for `agyis release check`."""
    status_val = str(report.get("status", "FAIL"))
    manifest = report.get("manifest") or {}
    lines = [
        theme.banner("Agyis Release Parity Check", badge_label=status_val, status="PASS" if status_val == "PASS" else "FAIL"),
        f" Version:     {report.get('version')}",
        f" Manifests:   pyproject={manifest.get('pyproject_version')} init={manifest.get('harness_init_version')} plugin={manifest.get('plugin_version')} pkg={manifest.get('package_json_version')} lock={manifest.get('uv_lock_version')} og={manifest.get('og_overlay_version')}",
        f" Changelog:   section_present={report.get('changelog_has_version')}",
        f" IncludeSite: {report.get('include_site')}",
        theme.rule(),
    ]
    mismatches = report.get("mismatches") or []
    if not mismatches:
        lines.append(" " + theme.badge("PASS", "PASS: All release surfaces are synchronized."))
    else:
        lines.append(" " + theme.badge("FAIL", f"FAIL: {len(mismatches)} mismatch(es) detected:"))
        lines.extend(f"  - {item}" for item in mismatches)
    lines.append(theme.rule("━"))
    return "\n".join(lines)


__all__ = [
    "EXCLUDED_RELEASE_PATHS",
    "ReleaseActionStatus",
    "ReleaseBumpPlan",
    "ReleaseBumpResult",
    "ReleaseFileEdit",
    "apply_release_bump",
    "check_release_parity",
    "format_release_bump_report",
    "format_release_check_report",
    "normalize_release_version",
    "plan_release_bump",
]
