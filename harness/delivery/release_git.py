# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Git reference, SemVer tag resolution, and GitHub release synchronization helpers."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, List, Optional, Tuple, Union

SEMVER_TAG_REGEX = re.compile(
    r"^[vV]?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

DEFAULT_REPO_URL = "https://github.com/kuasha420/agyis-harness"


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
