# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Coexistence Engine: 3-tier resource precedence and git pollution guard (ADR-030).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.delivery.constants import REPO_ROOT
from harness.delivery.git_hygiene import verify_zero_git_pollution


class CoexistenceEngine:
    """
    Evaluates 3-tier resource precedence and guarantees zero workspace git pollution.

    Precedence Hierarchy:
    - Layer 3 (Workspace Local `.agents/` or project root) [Highest Precedence]
    - Layer 2 (User Preferences `~/.gemini/antigravity/`)
    - Layer 1 (Global Plugin Installation or `harness/`) [Default Fallback]
    """

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        user_dir: Optional[Path] = None,
        plugin_dir: Optional[Path] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self.user_dir = (
            Path(user_dir).resolve()
            if user_dir
            else Path.home() / ".gemini" / "antigravity"
        )
        self.plugin_dir = (
            Path(plugin_dir).resolve()
            if plugin_dir
            else REPO_ROOT.resolve()
        )

    def resolve_resource(
        self,
        resource_type: str,
        resource_name: str,
        workspace_root: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Resolves a configuration, agent, skill, or rule file against the 3 layers.

        Returns layer metadata and concrete resolved path adhering to Layer 3 > 2 > 1.
        """
        ws = (
            Path(workspace_root).resolve()
            if workspace_root is not None
            else self.workspace_root
        )
        rtype = resource_type.strip().lower()
        rname = resource_name.strip()

        # Candidates generators for each layer
        def get_workspace_candidates() -> List[Path]:
            if not ws:
                return []
            candidates: List[Path] = []
            if rtype in ("agent", "agents"):
                candidates.extend([
                    ws / ".agents" / "agents" / f"{rname}.md",
                    ws / ".agents" / "agents" / rname,
                    ws / ".agents" / f"{rname}.md",
                ])
            elif rtype in ("skill", "skills"):
                candidates.extend([
                    ws / ".agents" / "skills" / rname / "SKILL.md",
                    ws / ".agents" / "skills" / rname,
                ])
            elif rtype in ("rule", "rules"):
                candidates.extend([
                    ws / ".agents" / "rules" / f"{rname}.md",
                    ws / ".agents" / "rules" / rname,
                    ws / "AGENTS.md" if rname.lower() in ("agents.md", "agents") else ws / rname,
                ])
            else:
                candidates.extend([
                    ws / ".agents" / rtype / rname,
                    ws / ".agents" / rname,
                    ws / rname,
                ])
            return candidates

        def get_user_candidates() -> List[Path]:
            candidates: List[Path] = []
            if rtype in ("agent", "agents"):
                candidates.extend([
                    self.user_dir / "agents" / f"{rname}.md",
                    self.user_dir / "agents" / rname,
                ])
            elif rtype in ("skill", "skills"):
                candidates.extend([
                    self.user_dir / "skills" / rname / "SKILL.md",
                    self.user_dir / "skills" / rname,
                    self.user_dir.parent / "config" / "skills" / rname / "SKILL.md",
                ])
            elif rtype in ("rule", "rules"):
                candidates.extend([
                    self.user_dir / "rules" / f"{rname}.md",
                    self.user_dir / "rules" / rname,
                ])
            else:
                candidates.extend([
                    self.user_dir / rtype / rname,
                    self.user_dir / rname,
                ])
            return candidates

        def get_plugin_candidates() -> List[Path]:
            candidates: List[Path] = []
            if rtype in ("agent", "agents"):
                candidates.extend([
                    self.plugin_dir / "harness" / "agents" / f"{rname}.md",
                    self.plugin_dir / "harness" / "agents" / rname,
                    self.plugin_dir / "agents" / f"{rname}.md",
                ])
            elif rtype in ("skill", "skills"):
                candidates.extend([
                    self.plugin_dir / "skills" / rname / "SKILL.md",
                    self.plugin_dir / "harness" / "skills" / rname / "SKILL.md",
                ])
            elif rtype in ("hooks", "hook"):
                candidates.extend([
                    self.plugin_dir / "hooks.json",
                    self.plugin_dir / "harness" / "hooks" / "hooks.json",
                ])
            elif rtype in ("matrix", "runtime"):
                candidates.extend([
                    self.plugin_dir / "matrix.json",
                    self.plugin_dir / "harness" / "runtime" / "matrix.json",
                ])
            else:
                candidates.extend([
                    self.plugin_dir / rtype / rname,
                    self.plugin_dir / "harness" / rtype / rname,
                    self.plugin_dir / rname,
                ])
            return candidates

        # 1. Check Layer 3 (Workspace)
        for cand in get_workspace_candidates():
            if cand.exists():
                return {
                    "found": True,
                    "layer": 3,
                    "layer_name": "workspace",
                    "path": cand,
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                }

        # 2. Check Layer 2 (User Preferences)
        for cand in get_user_candidates():
            if cand.exists():
                return {
                    "found": True,
                    "layer": 2,
                    "layer_name": "user",
                    "path": cand,
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                }

        # 3. Check Layer 1 (Global Plugin)
        for cand in get_plugin_candidates():
            if cand.exists():
                return {
                    "found": True,
                    "layer": 1,
                    "layer_name": "plugin",
                    "path": cand,
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                }

        return {
            "found": False,
            "layer": None,
            "layer_name": None,
            "path": None,
            "resource_type": resource_type,
            "resource_name": resource_name,
        }

    def verify_zero_git_pollution(self, workspace_root: Path) -> List[str]:
        """
        Audits workspace repository status to ensure zero runtime or telemetry pollution.
        """
        return verify_zero_git_pollution(workspace_root)
