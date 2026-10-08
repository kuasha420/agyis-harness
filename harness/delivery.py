"""
PSL Harness Delivery & Global Plugin Installer (ADR-030).

Implements the Layer 1 vs. Layer 3 coexistence contract, packaging filter
for ADR-014 Product vs. Project Bifurcation, and global installation of
psl-agy-harness into Google Antigravity extension paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Set

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_PLUGIN_DIR = (
    Path(os.environ["PSL_PLUGINS_DIR"])
    if "PSL_PLUGINS_DIR" in os.environ
    else Path.home() / ".gemini" / "config" / "plugins" / "psl-agy-harness"
)

DISTRIBUTABLE_ITEMS: frozenset[str] = frozenset({
    "plugin.json",
    "harness",
    "matrix.json",
    "hooks.json",
})

EXCLUDED_PACKAGING_NAMES: frozenset[str] = frozenset({
    "pipeline",
    "data",
    "tests",
    "docs",
    "scratch",
    ".git",
    "artifacts",
    "__pycache__",
})


class DeliveryMode(str, Enum):
    """Plugin installation modes."""

    SYMLINK = "symlink"
    COPY = "copy"


@dataclass
class DeliveryResult:
    """Outcome report for plugin installation or uninstallation."""

    success: bool
    mode: str
    target_dir: Path
    source_dir: Path
    items_installed: List[str] = field(default_factory=list)
    message: str = ""


class PluginInstaller:
    """
    Manages global installation and lifecycle of the psl-agy-harness plugin.

    Enforces ADR-014 Product vs. Project Bifurcation and strict path safety
    guards to protect the source repository root.
    """

    def __init__(
        self,
        source_dir: Optional[Path] = None,
        default_target_dir: Optional[Path] = None,
        bin_dir: Optional[Path] = None,
    ) -> None:
        self.source_dir = Path(source_dir).resolve() if source_dir else REPO_ROOT.resolve()
        if default_target_dir is not None:
            self.default_target_dir = Path(default_target_dir)
        elif "PSL_PLUGINS_DIR" in os.environ:
            self.default_target_dir = Path(os.environ["PSL_PLUGINS_DIR"])
        else:
            self.default_target_dir = Path.home() / ".gemini" / "config" / "plugins" / "psl-agy-harness"

        if bin_dir is not None:
            self.bin_dir = Path(bin_dir).resolve()
        elif "PSL_BIN_DIR" in os.environ:
            self.bin_dir = Path(os.environ["PSL_BIN_DIR"]).expanduser().resolve()
        else:
            self.bin_dir = (Path.home() / ".local" / "bin").resolve()

        # Verify safety guard on default target directory
        self._verify_path_safety(self.default_target_dir)

    def _install_bin(self, target: Path) -> Path:
        """Installs standalone CLI executable launcher into self.bin_dir with mode 0o755."""
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        psl_bin = self.bin_dir / "psl"
        if psl_bin.is_symlink() or psl_bin.exists():
            try:
                psl_bin.unlink()
            except OSError:
                pass

        target_resolved = str(target.resolve()) if target.exists() else str(target)
        source_resolved = str(self.source_dir.resolve())
        launcher_content = (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "from pathlib import Path\n\n"
            f"target_dir = Path({target_resolved!r})\n"
            "if target_dir.exists() and str(target_dir) not in sys.path:\n"
            "    sys.path.insert(0, str(target_dir))\n\n"
            "plugin_default = Path.home() / '.gemini' / 'config' / 'plugins' / 'psl-agy-harness'\n"
            "if plugin_default.exists() and str(plugin_default) not in sys.path:\n"
            "    sys.path.insert(0, str(plugin_default))\n\n"
            f"source_dir = Path({source_resolved!r})\n"
            "if source_dir.exists() and str(source_dir) not in sys.path:\n"
            "    sys.path.insert(0, str(source_dir))\n\n"
            "venv_py = source_dir / '.venv' / 'bin' / 'python'\n"
            "if venv_py.exists() and sys.executable != str(venv_py):\n"
            "    import os\n"
            "    os.execv(str(venv_py), [str(venv_py)] + sys.argv)\n\n"
            "from harness.cli import main\n\n"
            "if __name__ == '__main__':\n"
            "    sys.exit(main())\n"
        )
        psl_bin.write_text(launcher_content, encoding="utf-8")
        psl_bin.chmod(0o755)
        return psl_bin

    def _verify_path_safety(self, target_dir: Path) -> None:
        """
        Critical safety invariant: target path must NEVER equal or contain source repository root.
        """
        resolved_source = self.source_dir.resolve()

        if target_dir.is_symlink():
            symlink_location = target_dir.parent.resolve() / target_dir.name
            if symlink_location == resolved_source or resolved_source.is_relative_to(symlink_location):
                raise ValueError("Target cannot be or contain source repository root")
            return

        resolved_target = target_dir.resolve()
        if resolved_target == resolved_source or resolved_source.is_relative_to(resolved_target):
            raise ValueError("Target cannot be or contain source repository root")

    def _find_distributable_item(self, item_name: str) -> Optional[Path]:
        """Locates canonical source for a distributable item."""
        direct = self.source_dir / item_name
        if direct.exists():
            return direct

        if item_name == "matrix.json":
            runtime_matrix = self.source_dir / "harness" / "runtime" / "matrix.json"
            if runtime_matrix.exists():
                return runtime_matrix

        if item_name == "hooks.json":
            runtime_hooks = self.source_dir / "harness" / "hooks" / "hooks.json"
            if runtime_hooks.exists():
                return runtime_hooks

        return None

    def install(
        self,
        mode: DeliveryMode = DeliveryMode.SYMLINK,
        dry_run: bool = False,
        target_dir: Optional[Path] = None,
    ) -> DeliveryResult:
        """
        Installs psl-agy-harness into the target plugin directory.

        Supports SYMLINK mode (live link) and COPY mode (isolated packaged release).
        """
        target = Path(target_dir) if target_dir is not None else self.default_target_dir
        self._verify_path_safety(target)

        # Distributables discovery
        distributables: List[str] = []
        for item in ("plugin.json", "harness", "matrix.json", "hooks.json"):
            if self._find_distributable_item(item) is not None:
                distributables.append(item)

        if dry_run:
            return DeliveryResult(
                success=True,
                mode=mode.value,
                target_dir=target,
                source_dir=self.source_dir,
                items_installed=distributables,
                message=f"Dry-run: simulate {mode.value} installation to {target}",
            )

        if mode == DeliveryMode.SYMLINK:
            if target.is_symlink():
                try:
                    if target.resolve() == self.source_dir.resolve():
                        self._install_bin(target)
                        return DeliveryResult(
                            success=True,
                            mode=DeliveryMode.SYMLINK.value,
                            target_dir=target,
                            source_dir=self.source_dir,
                            items_installed=distributables,
                            message=f"Symlink already points to source at {target}",
                        )
                except OSError:
                    pass
                target.unlink()
            elif target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()

            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(self.source_dir.resolve())
            self._install_bin(target)

            return DeliveryResult(
                success=True,
                mode=DeliveryMode.SYMLINK.value,
                target_dir=target,
                source_dir=self.source_dir,
                items_installed=distributables,
                message=f"Successfully symlinked plugin {target} -> {self.source_dir}",
            )

        elif mode == DeliveryMode.COPY:
            if target.is_symlink():
                target.unlink()
            target.mkdir(parents=True, exist_ok=True)

            installed_items: List[str] = []

            # 1. plugin.json
            plugin_src = self._find_distributable_item("plugin.json")
            if plugin_src and plugin_src.is_file():
                shutil.copy2(plugin_src, target / "plugin.json")
                installed_items.append("plugin.json")

            # 2. harness/ package directory
            harness_src = self.source_dir / "harness"
            if harness_src.is_dir():
                harness_dst = target / "harness"
                if harness_dst.exists():
                    shutil.rmtree(harness_dst)
                shutil.copytree(
                    harness_src,
                    harness_dst,
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "*.pyc", "*.pyo", "*.db*", "telemetry.db"
                    ),
                )
                installed_items.append("harness")

            # 3. matrix.json
            matrix_src = self._find_distributable_item("matrix.json")
            if matrix_src and matrix_src.is_file():
                shutil.copy2(matrix_src, target / "matrix.json")
                installed_items.append("matrix.json")

            # 4. hooks.json
            hooks_src = self._find_distributable_item("hooks.json")
            if hooks_src and hooks_src.is_file():
                shutil.copy2(hooks_src, target / "hooks.json")
                installed_items.append("hooks.json")

            self._install_bin(target)

            return DeliveryResult(
                success=True,
                mode=DeliveryMode.COPY.value,
                target_dir=target,
                source_dir=self.source_dir,
                items_installed=installed_items,
                message=f"Successfully packaged and copied plugin to {target}",
            )

        raise ValueError(f"Unsupported delivery mode: {mode}")

    def uninstall(
        self,
        dry_run: bool = False,
        target_dir: Optional[Path] = None,
    ) -> DeliveryResult:
        """
        Uninstalls the plugin from the target directory and unlinks bin_dir / psl.

        Safety invariant: if target is a symlink, unlinks ONLY the symlink
        without touching the resolved source path.
        """
        target = Path(target_dir) if target_dir is not None else self.default_target_dir
        self._verify_path_safety(target)

        if not dry_run:
            psl_bin = self.bin_dir / "psl"
            if psl_bin.is_symlink() or psl_bin.exists():
                try:
                    psl_bin.unlink()
                except OSError:
                    pass

        if not target.exists() and not target.is_symlink():
            return DeliveryResult(
                success=True,
                mode="none",
                target_dir=target,
                source_dir=self.source_dir,
                items_installed=[],
                message=f"Target {target} does not exist; nothing to uninstall",
            )

        mode = "symlink" if target.is_symlink() else "copy"

        if dry_run:
            return DeliveryResult(
                success=True,
                mode=mode,
                target_dir=target,
                source_dir=self.source_dir,
                items_installed=[],
                message=f"Dry-run: simulate removal of {target}",
            )

        if target.is_symlink():
            target.unlink()
            return DeliveryResult(
                success=True,
                mode=DeliveryMode.SYMLINK.value,
                target_dir=target,
                source_dir=self.source_dir,
                items_installed=[],
                message=f"Successfully unlinked plugin symlink {target}",
            )
        elif target.is_dir():
            shutil.rmtree(target)
            return DeliveryResult(
                success=True,
                mode=DeliveryMode.COPY.value,
                target_dir=target,
                source_dir=self.source_dir,
                items_installed=[],
                message=f"Successfully removed installed plugin directory {target}",
            )
        elif target.is_file():
            target.unlink()
            return DeliveryResult(
                success=True,
                mode="file",
                target_dir=target,
                source_dir=self.source_dir,
                items_installed=[],
                message=f"Successfully removed file {target}",
            )

        return DeliveryResult(
            success=False,
            mode=mode,
            target_dir=target,
            source_dir=self.source_dir,
            items_installed=[],
            message=f"Failed to uninstall unrecognized target type at {target}",
        )

    def is_installed(self, target_dir: Optional[Path] = None) -> bool:
        """Checks whether the plugin is currently installed at target path."""
        target = Path(target_dir) if target_dir is not None else self.default_target_dir
        if not target.exists() and not target.is_symlink():
            return False

        if target.is_symlink():
            try:
                resolved = target.resolve()
                return resolved.exists() and (target / "plugin.json").exists()
            except OSError:
                return False

        if target.is_dir():
            return (target / "plugin.json").exists() and (target / "harness").is_dir()

        return False

    def get_install_info(self, target_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Returns structured metadata about the installed plugin instance."""
        target = Path(target_dir) if target_dir is not None else self.default_target_dir
        installed = self.is_installed(target)

        mode = "none"
        if target.is_symlink():
            mode = "symlink"
        elif target.is_dir() and installed:
            mode = "copy"

        version = None
        plugin_file = target / "plugin.json"
        if plugin_file.is_file():
            try:
                data = json.loads(plugin_file.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, dict):
                    version = data.get("version")
            except (json.JSONDecodeError, OSError):
                pass

        items: List[str] = []
        if target.exists() and target.is_dir():
            try:
                items = sorted([child.name for child in target.iterdir()])
            except OSError:
                items = []

        return {
            "installed": installed,
            "mode": mode,
            "target_dir": str(target),
            "source_dir": str(self.source_dir),
            "version": version,
            "items": items,
        }


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

        Checks for untracked database files, temporary test state files, or unignored
        scratch files that would violate clean-tree invariants.
        """
        ws = Path(workspace_root).resolve()
        if not ws.exists():
            return []

        polluting_patterns = [
            "telemetry.db*",
            "verification_state_*.json",
            "*.pyc",
            "__pycache__",
            ".coverage*",
            ".pytest_cache",
        ]

        polluting_files: List[str] = []

        # 1. Use git status --porcelain if git repo exists
        git_dir = ws / ".git"
        if git_dir.exists():
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
                        entry = line.strip()
                        if entry.startswith("??"):
                            rel_path = entry[2:].strip().strip('"')
                            base_name = Path(rel_path).name
                            if (
                                "telemetry.db" in base_name
                                or "verification_state_" in base_name
                                or base_name.endswith(".pyc")
                                or base_name in ("__pycache__", ".coverage", ".pytest_cache")
                            ):
                                polluting_files.append(rel_path)
                    return sorted(polluting_files)
            except (OSError, subprocess.SubprocessError):
                pass

        # 2. Filesystem probe fallback
        for pattern in polluting_patterns:
            for match in ws.rglob(pattern):
                # Filter out intentional fixtures if inside tests/fixtures
                try:
                    rel = match.relative_to(ws)
                    if not str(rel).startswith("tests/"):
                        polluting_files.append(str(rel))
                except ValueError:
                    pass

        return sorted(list(set(polluting_files)))
