# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Fork-aware Git Remote Topology & Delivery Helpers (ADR-031).
Provides GitTopologyProbe and pull request delivery helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from harness.delivery.constants import REPO_ROOT


@dataclass
class RemoteInfo:
    name: str
    fetch_url: str
    push_url: str
    owner: Optional[str] = None
    repo: Optional[str] = None
    is_github: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "fetch_url": self.fetch_url,
            "push_url": self.push_url,
            "owner": self.owner,
            "repo": self.repo,
            "is_github": self.is_github,
        }


@dataclass
class GitTopology:
    workspace: Path
    remotes: Dict[str, RemoteInfo]
    current_branch: str
    active_base_branch: str
    is_dirty: bool
    untracked_files: List[str]
    modified_files: List[str]
    is_worktree: bool
    is_auxiliary_clone: bool
    is_harness_host: bool
    authenticated_user: Optional[str] = None
    canonical_upstream_remote: Optional[str] = None
    push_target_remote: Optional[str] = None
    pr_target_repo: Optional[str] = None
    pr_base_branch: Optional[str] = None
    pr_head_branch: Optional[str] = None
    requires_fork: bool = False
    viewer_permission: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace": str(self.workspace),
            "remotes": {k: v.to_dict() for k, v in self.remotes.items()},
            "current_branch": self.current_branch,
            "active_base_branch": self.active_base_branch,
            "is_dirty": self.is_dirty,
            "untracked_files": self.untracked_files,
            "modified_files": self.modified_files,
            "is_worktree": self.is_worktree,
            "is_auxiliary_clone": self.is_auxiliary_clone,
            "is_harness_host": self.is_harness_host,
            "authenticated_user": self.authenticated_user,
            "canonical_upstream_remote": self.canonical_upstream_remote,
            "push_target_remote": self.push_target_remote,
            "pr_target_repo": self.pr_target_repo,
            "pr_base_branch": self.pr_base_branch,
            "pr_head_branch": self.pr_head_branch,
            "requires_fork": self.requires_fork,
            "viewer_permission": self.viewer_permission,
        }


def _parse_remote_url(url: str) -> Tuple[Optional[str], Optional[str], bool]:
    """Extracts (owner, repo, is_github) from a git remote URL."""
    url = url.strip()
    is_github = "github.com" in url.lower()

    # 1. SCP-style: [user@]host:owner/repo[.git]
    scp_m = re.match(r"^(?:[\w\.\-]+@)?([^/:]+):([^/]+)/([^/]+?)(?:\.git)?$", url)
    if scp_m:
        host, owner, repo = scp_m.group(1), scp_m.group(2), scp_m.group(3)
        return owner, repo, "github.com" in host.lower()

    # 2. URI-style: proto://[user@]host[:port]/owner/repo[.git]
    uri_m = re.match(r"^[a-zA-Z0-9_\-]+://(?:[\w\.\-]+@)?([^/:]+)(?::\d+)?/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if uri_m:
        host, owner, repo = uri_m.group(1), uri_m.group(2), uri_m.group(3)
        return owner, repo, "github.com" in host.lower()

    return None, None, is_github


class GitTopologyProbe:
    """Probes repository remotes, permissions, dirtiness, worktrees, and delivery targets."""

    @classmethod
    def probe(cls, repo_path: Path, upstream_remote: Optional[str] = None) -> GitTopology:
        ws = Path(repo_path).resolve()
        if not ws.is_dir():
            raise FileNotFoundError(f"Path does not exist or is not a directory: {ws}")

        # 1. Validate git repository
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=ws,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode != 0 or proc.stdout.strip() != "true":
                raise ValueError(f"Directory is not inside a git repository work-tree: {ws}")
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f"Failed to verify git repository at {ws}: {exc}") from exc

        # 2. Worktree detection
        git_entry = ws / ".git"
        is_worktree = False
        if git_entry.is_file():
            try:
                content = git_entry.read_text(encoding="utf-8", errors="replace")
                if "gitdir:" in content:
                    is_worktree = True
            except OSError:
                pass

        # 3. Current branch
        current_branch = ""
        try:
            proc = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=ws,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0:
                current_branch = proc.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass

        if not current_branch:
            try:
                proc = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=ws,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0:
                    current_branch = proc.stdout.strip()
                else:
                    current_branch = "HEAD"
            except (OSError, subprocess.SubprocessError):
                current_branch = "HEAD"

        # 4. Active base branch default
        active_base_branch = "main"
        try:
            proc = subprocess.run(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                cwd=ws,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0:
                ref = proc.stdout.strip()
                parts = ref.split("/")
                if parts:
                    active_base_branch = parts[-1]
        except Exception:
            pass

        if active_base_branch == "main":
            try:
                proc = subprocess.run(
                    ["git", "rev-parse", "--verify", "refs/heads/develop"],
                    cwd=ws,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0:
                    active_base_branch = "develop"
                else:
                    proc = subprocess.run(
                        ["git", "rev-parse", "--verify", "refs/remotes/origin/develop"],
                        cwd=ws,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    if proc.returncode == 0:
                        active_base_branch = "develop"
            except Exception:
                pass

        # 5. Parse remotes
        remotes: Dict[str, RemoteInfo] = {}
        try:
            proc = subprocess.run(
                ["git", "remote", "-v"],
                cwd=ws,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) >= 3:
                        r_name = parts[0]
                        r_url = parts[1]
                        r_dir = parts[2].strip("()")
                        owner, repo, is_github = _parse_remote_url(r_url)
                        if r_name not in remotes:
                            remotes[r_name] = RemoteInfo(
                                name=r_name,
                                fetch_url=r_url,
                                push_url=r_url,
                                owner=owner,
                                repo=repo,
                                is_github=is_github,
                            )
                        else:
                            if r_dir == "fetch":
                                remotes[r_name].fetch_url = r_url
                            elif r_dir == "push":
                                remotes[r_name].push_url = r_url
                            if not remotes[r_name].owner and owner:
                                remotes[r_name].owner = owner
                                remotes[r_name].repo = repo
                                remotes[r_name].is_github = is_github
        except Exception:
            pass

        # 6. Working tree dirtiness
        untracked_files: List[str] = []
        modified_files: List[str] = []
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ws,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    if not line:
                        continue
                    if line.startswith("??"):
                        untracked_files.append(line[2:].strip().strip('"'))
                    else:
                        modified_files.append(line[2:].strip().strip('"'))
        except Exception:
            pass
        is_dirty = bool(untracked_files or modified_files)

        # 7. Auxiliary clone detection
        is_auxiliary_clone = False
        dir_name = ws.name
        if dir_name.endswith("-2") or dir_name.endswith("-worktrees") or dir_name.endswith("-worktree") or "-worktrees" in dir_name:
            is_auxiliary_clone = True
        else:
            m = re.match(r"^(.+)-(\d+)$", dir_name)
            if m:
                canonical_name = m.group(1)
                sibling = ws.parent / canonical_name
                if sibling.is_dir() and ((sibling / ".git").exists() or (sibling / ".git").is_file()):
                    is_auxiliary_clone = True

        # 8. Host repo self-detection (is_harness_host)
        is_harness_host = False
        try:
            if ws.resolve() == REPO_ROOT.resolve():
                is_harness_host = True
        except Exception:
            pass

        if not is_harness_host:
            for r in remotes.values():
                for u in (r.fetch_url, r.push_url):
                    cu = u.rstrip("/")
                    if cu.endswith(".git"):
                        cu = cu[:-4]
                    if cu.endswith("/psl-agy-harness") or cu.endswith("/agyis-harness"):
                        is_harness_host = True
                        break
                if is_harness_host:
                    break

        if not is_harness_host:
            if (ws / "harness" / "__init__.py").exists() and (ws / "matrix.json").exists() and (ws / "plugin.json").exists():
                try:
                    pj_data = json.loads((ws / "plugin.json").read_text(encoding="utf-8"))
                    if pj_data.get("name") in ("agyis-harness", "psl-agy-harness"):
                        is_harness_host = True
                except Exception:
                    pass

        # 9. GitHub authentication & permission checking
        has_github_remote = any(r.is_github for r in remotes.values())
        auth_user: Optional[str] = None
        if has_github_remote and not (os.environ.get("AGYIS_OFFLINE") == "1" or os.environ.get("PSL_OFFLINE") == "1"):
            try:
                proc = subprocess.run(
                    ["gh", "api", "user", "--jq", ".login"],
                    cwd=ws,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    auth_user = proc.stdout.strip()
            except (OSError, subprocess.SubprocessError):
                auth_user = None

        canonical_upstream_remote: Optional[str] = None
        push_target_remote: Optional[str] = None
        pr_target_repo: Optional[str] = None
        pr_base_branch: Optional[str] = None
        pr_head_branch: Optional[str] = None
        requires_fork: bool = False
        viewer_permission: Optional[str] = None

        if not auth_user:
            # Offline / non-GitHub / unauthenticated fallback
            push_target_remote = upstream_remote or ("origin" if "origin" in remotes else (next(iter(remotes.keys())) if remotes else "origin"))
            canonical_upstream_remote = upstream_remote or ("origin" if "origin" in remotes else None)
            requires_fork = False
            if canonical_upstream_remote and canonical_upstream_remote in remotes:
                rem = remotes[canonical_upstream_remote]
                if rem.owner and rem.repo:
                    pr_target_repo = f"{rem.owner}/{rem.repo}"
            pr_base_branch = active_base_branch
            pr_head_branch = current_branch
        else:
            # GitHub authenticated
            is_inverted_fork = False
            origin_info = remotes.get("origin")
            cand_upstream: Optional[RemoteInfo] = None

            if origin_info and origin_info.owner and origin_info.owner.lower() == auth_user.lower():
                if upstream_remote and upstream_remote in remotes and upstream_remote != "origin":
                    cand_upstream = remotes[upstream_remote]
                elif "upstream" in remotes:
                    cand_upstream = remotes["upstream"]
                else:
                    for rname, rinfo in remotes.items():
                        if rname != "origin" and ((rinfo.owner and rinfo.owner.lower() != auth_user.lower()) or rname in ("canonical", "purrfectsoft")):
                            cand_upstream = rinfo
                            break
                if cand_upstream:
                    is_inverted_fork = True

            if is_inverted_fork and cand_upstream:
                push_target_remote = "origin"
                canonical_upstream_remote = cand_upstream.name
                pr_target_repo = f"{cand_upstream.owner}/{cand_upstream.repo}" if cand_upstream.owner and cand_upstream.repo else cand_upstream.name
                pr_head_branch = f"{auth_user}:{current_branch}"
                requires_fork = False
                viewer_permission = "WRITE"
                if cand_upstream.is_github and cand_upstream.owner and cand_upstream.repo:
                    try:
                        view_proc = subprocess.run(
                            ["gh", "repo", "view", pr_target_repo, "--json", "viewerPermission,defaultBranchRef"],
                            cwd=ws,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=5,
                            check=False,
                        )
                        if view_proc.returncode == 0:
                            view_data = json.loads(view_proc.stdout)
                            perm = view_data.get("viewerPermission")
                            if perm:
                                viewer_permission = perm
                            d_ref = view_data.get("defaultBranchRef")
                            if isinstance(d_ref, dict) and d_ref.get("name"):
                                active_base_branch = d_ref["name"]
                            elif isinstance(d_ref, str) and d_ref:
                                active_base_branch = d_ref
                    except Exception:
                        pass
                pr_base_branch = active_base_branch
            else:
                target_name = upstream_remote or ("upstream" if "upstream" in remotes else ("origin" if "origin" in remotes else next(iter(remotes.keys()), "origin")))
                canonical_upstream_remote = target_name
                target_rem = remotes.get(target_name)

                if not target_rem or not target_rem.is_github or not target_rem.owner or not target_rem.repo:
                    push_target_remote = target_name
                    pr_head_branch = current_branch
                    pr_base_branch = active_base_branch
                    requires_fork = False
                    viewer_permission = None
                    if target_rem and target_rem.owner and target_rem.repo:
                        pr_target_repo = f"{target_rem.owner}/{target_rem.repo}"
                else:
                    target_repo_slug = f"{target_rem.owner}/{target_rem.repo}"
                    pr_target_repo = target_repo_slug
                    viewer_permission = None
                    try:
                        view_proc = subprocess.run(
                            ["gh", "repo", "view", target_repo_slug, "--json", "viewerPermission,defaultBranchRef"],
                            cwd=ws,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=5,
                            check=False,
                        )
                        if view_proc.returncode == 0:
                            view_data = json.loads(view_proc.stdout)
                            viewer_permission = view_data.get("viewerPermission")
                            d_ref = view_data.get("defaultBranchRef")
                            if isinstance(d_ref, dict) and d_ref.get("name"):
                                active_base_branch = d_ref["name"]
                            elif isinstance(d_ref, str) and d_ref:
                                active_base_branch = d_ref
                    except Exception:
                        pass

                    pr_base_branch = active_base_branch

                    if viewer_permission in ["ADMIN", "MAINTAIN", "WRITE"]:
                        push_target_remote = target_name
                        pr_head_branch = current_branch
                        requires_fork = False
                    elif viewer_permission in ["READ", "TRIAGE", "NONE"]:
                        requires_fork = True
                        fork_exists = False
                        try:
                            chk_proc = subprocess.run(
                                ["gh", "repo", "view", f"{auth_user}/{target_rem.repo}", "--json", "nameWithOwner"],
                                cwd=ws,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                                timeout=5,
                                check=False,
                            )
                            fork_exists = (chk_proc.returncode == 0)
                        except Exception:
                            fork_exists = False

                        if not fork_exists:
                            try:
                                subprocess.run(
                                    ["gh", "repo", "fork", target_repo_slug, "--clone=false", "--remote=true", "--remote-name=fork"],
                                    cwd=ws,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True,
                                    timeout=10,
                                    check=False,
                                )
                            except Exception:
                                pass

                        if "fork" not in remotes:
                            fork_url = f"https://github.com/{auth_user}/{target_rem.repo}.git"
                            try:
                                subprocess.run(
                                    ["git", "remote", "add", "fork", fork_url],
                                    cwd=ws,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True,
                                    timeout=5,
                                    check=False,
                                )
                                remotes["fork"] = RemoteInfo(
                                    name="fork",
                                    fetch_url=fork_url,
                                    push_url=fork_url,
                                    owner=auth_user,
                                    repo=target_rem.repo,
                                    is_github=True,
                                )
                            except Exception:
                                pass

                        push_target_remote = "fork"
                        pr_head_branch = f"{auth_user}:{current_branch}"
                    else:
                        push_target_remote = target_name
                        pr_head_branch = current_branch
                        requires_fork = False

        return GitTopology(
            workspace=ws,
            remotes=remotes,
            current_branch=current_branch,
            active_base_branch=active_base_branch,
            is_dirty=is_dirty,
            untracked_files=untracked_files,
            modified_files=modified_files,
            is_worktree=is_worktree,
            is_auxiliary_clone=is_auxiliary_clone,
            is_harness_host=is_harness_host,
            authenticated_user=auth_user,
            canonical_upstream_remote=canonical_upstream_remote,
            push_target_remote=push_target_remote,
            pr_target_repo=pr_target_repo,
            pr_base_branch=pr_base_branch,
            pr_head_branch=pr_head_branch,
            requires_fork=requires_fork,
            viewer_permission=viewer_permission,
        )


def create_pull_request(
    topology: GitTopology,
    title: str,
    body: str,
    draft: bool = False,
    base: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Submits a GitHub Pull Request via `gh pr create` based on evaluated topology.

    Returns (True, pr_url) on success, or (False, error_message) on failure/skip.
    """
    if topology.is_harness_host:
        return (False, "Notice: Workspace is the Agyis harness host repository. Skipping self-referential PR creation.")

    if topology.is_auxiliary_clone:
        return (False, "Notice: Workspace is an auxiliary clone. Skipping duplicate PR creation.")

    target_repo = topology.pr_target_repo
    if not target_repo:
        if topology.canonical_upstream_remote and topology.canonical_upstream_remote in topology.remotes:
            rem = topology.remotes[topology.canonical_upstream_remote]
            if rem.owner and rem.repo:
                target_repo = f"{rem.owner}/{rem.repo}"
        if not target_repo and "origin" in topology.remotes:
            rem = topology.remotes["origin"]
            if rem.owner and rem.repo:
                target_repo = f"{rem.owner}/{rem.repo}"

    cmd = ["gh", "pr", "create"]
    if target_repo:
        cmd.extend(["--repo", target_repo])

    head_branch = topology.pr_head_branch or topology.current_branch
    cmd.extend(["--head", head_branch])

    base_b = base or topology.pr_base_branch or topology.active_base_branch or "main"
    cmd.extend(["--base", base_b])

    cmd.extend(["--title", title])
    cmd.extend(["--body", body])
    if draft:
        cmd.append("--draft")

    try:
        proc = subprocess.run(
            cmd,
            cwd=topology.workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0:
            return (True, proc.stdout.strip())
        else:
            err = proc.stderr.strip() or proc.stdout.strip()
            return (False, err)
    except FileNotFoundError:
        return (False, "gh CLI not found")
    except Exception as exc:
        return (False, str(exc))
