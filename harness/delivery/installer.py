# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness Delivery & Global Plugin Installer (ADR-030).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional
import zipfile

from harness.delivery.bin_launcher import install_launchers, install_psl_launcher
from harness.delivery.constants import (
    DEFAULT_PLUGIN_DIR,
    DEFAULT_SURFACE_NAMES,
    REPO_ROOT,
    SYNC_SURFACE_ITEMS,
    DeliveryMode,
    DeliveryResult,
)
from harness.delivery.copy_install import copy_distributable_tree
from harness.delivery.surfaces import (
    enforce_single_source_agents_impl,
    sync_surfaces_impl,
)


class PluginInstaller:
    """
    Manages global installation and lifecycle of the agyis-harness plugin.

    Enforces ADR-014 Product vs. Project Bifurcation and strict path safety
    guards to protect the source repository root.
    """

    def __init__(
        self,
        source_dir: Optional[Path] = None,
        default_target_dir: Optional[Path] = None,
        bin_dir: Optional[Path] = None,
        aux_bin_dirs: Optional[List[Path]] = None,
        config_dir: Optional[Path] = None,
        surfaces: Optional[List[Path]] = None,
    ) -> None:
        self.source_dir = Path(source_dir).resolve() if source_dir else REPO_ROOT.resolve()
        if default_target_dir is not None:
            self.default_target_dir = Path(default_target_dir)
        elif "AGYIS_PLUGINS_DIR" in os.environ or "PSL_PLUGINS_DIR" in os.environ:
            env_val = os.environ.get("AGYIS_PLUGINS_DIR") or os.environ.get("PSL_PLUGINS_DIR")
            self.default_target_dir = Path(env_val)
        else:
            self.default_target_dir = DEFAULT_PLUGIN_DIR

        if config_dir is not None:
            self.config_dir = Path(config_dir).resolve()
        elif self.default_target_dir.parent.name == "plugins":
            self.config_dir = self.default_target_dir.parent.parent.resolve()
        else:
            self.config_dir = (Path.home() / ".gemini" / "config").resolve()

        if surfaces is not None:
            self.surfaces = [Path(s).resolve() for s in surfaces]
        else:
            base_gemini = self.config_dir.parent
            self.surfaces = [
                (base_gemini / name).resolve()
                for name in DEFAULT_SURFACE_NAMES
            ]

        if bin_dir is not None:
            self.bin_dir = Path(bin_dir).resolve()
        elif "AGYIS_BIN_DIR" in os.environ or "PSL_BIN_DIR" in os.environ:
            val = os.environ.get("AGYIS_BIN_DIR") or os.environ["PSL_BIN_DIR"]
            self.bin_dir = Path(val).expanduser().resolve()
        else:
            self.bin_dir = (Path.home() / ".local" / "bin").resolve()

        if aux_bin_dirs is not None:
            self.aux_bin_dirs = [Path(d).resolve() for d in aux_bin_dirs]
        elif "AGYIS_AUX_BIN_DIRS" in os.environ or "PSL_AUX_BIN_DIRS" in os.environ:
            val = os.environ.get("AGYIS_AUX_BIN_DIRS") or os.environ["PSL_AUX_BIN_DIRS"]
            self.aux_bin_dirs = [
                Path(p).expanduser().resolve()
                for p in val.split(":")
                if p.strip()
            ]
        else:
            self.aux_bin_dirs = [
                (Path.home() / ".gemini" / "antigravity" / "bin").resolve(),
                (Path.home() / ".gemini" / "antigravity-cli" / "bin").resolve(),
                Path("/usr/local/bin").resolve(),
            ]

        # Verify safety guard on default target directory
        self._verify_path_safety(self.default_target_dir)

    def _install_bin(self, target: Path) -> Path:
        """Installs standalone CLI executable launchers (agyis and psl) into self.bin_dir and auxiliary bin paths with mode 0o755."""
        agyis_bin, _ = install_launchers(self.bin_dir, self.aux_bin_dirs, self.source_dir, target)
        return agyis_bin

    def _build_frozen_wheel(self, output_dir: Path) -> Path:
        """Builds a binary wheel distribution using uv build (with pip fallback)."""
        if shutil.which("uv"):
            cmd = ["uv", "build", "--wheel", "--out-dir", str(output_dir)]
        else:
            cmd = [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "-w",
                str(output_dir),
                str(self.source_dir),
            ]

        res = subprocess.run(
            cmd,
            cwd=str(self.source_dir),
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(
                f"Release wheel build failed (exit code {res.returncode}): {res.stderr or res.stdout}"
            )
        wheels = list(output_dir.glob("*.whl"))
        if not wheels:
            raise RuntimeError(f"No wheel artifact found in build output directory {output_dir}")
        return wheels[0]

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

        if item_name == "skills":
            skills_dir = self.source_dir / "harness" / "skills"
            if skills_dir.exists():
                return skills_dir

        if item_name == "agents":
            agents_dir = self.source_dir / "harness" / "agents"
            if agents_dir.exists():
                return agents_dir

        if item_name == "rules":
            rules_dir = self.source_dir / "harness" / "rules"
            if rules_dir.exists():
                return rules_dir

        return None

    def _ensure_source_root_plugin_symlinks(self) -> None:
        """
        Ensures standard top-level plugin symlinks exist at source repository root:
        skills -> harness/skills, agents -> harness/agents, rules -> harness/rules,
        hooks.json -> harness/hooks/hooks.json, matrix.json -> harness/runtime/matrix.json.
        """
        links = {
            "skills": Path("harness/skills"),
            "agents": Path("harness/agents"),
            "rules": Path("harness/rules"),
            "hooks.json": Path("harness/hooks/hooks.json"),
            "matrix.json": Path("harness/runtime/matrix.json"),
        }
        for name, rel_target in links.items():
            link_path = self.source_dir / name
            src_target = self.source_dir / rel_target
            if not link_path.exists() and src_target.exists():
                try:
                    link_path.symlink_to(rel_target)
                except OSError:
                    pass

    def _enable_in_config(self, plugin_name: str = "agyis-harness") -> None:
        """Ensures plugin is marked enabled in global ~/.gemini/config/config.json."""
        config_path = Path.home() / ".gemini" / "config" / "config.json"
        try:
            data: Dict[str, Any] = {}
            if config_path.is_file():
                data = json.loads(config_path.read_text(encoding="utf-8"))
            if "plugins" not in data or not isinstance(data["plugins"], dict):
                data["plugins"] = {}
            data["plugins"][plugin_name] = {"enabled": True}
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass

    def _enforce_single_source_agents(
        self, target: Path, dry_run: bool = False
    ) -> List[str]:
        """Enforces single-source agent delivery (Issue #30)."""
        plugin_agents_dir = self._find_distributable_item("agents")
        return enforce_single_source_agents_impl(
            plugin_agents_dir, self.config_dir, target, self.source_dir, dry_run=dry_run
        )

    def sync_surfaces(
        self,
        surfaces: Optional[List[Path]] = None,
        config_dir: Optional[Path] = None,
        dry_run: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Synchronizes all Antigravity surfaces (~/.gemini/antigravity,
        ~/.gemini/antigravity-cli, ~/.gemini/antigravity-ide) to link
        agents, skills, plugins, rules, hooks.json, AGENTS.md to canonical config.
        """
        target_surfaces = (
            [Path(s).resolve() for s in surfaces]
            if surfaces is not None
            else self.surfaces
        )
        cfg_root = Path(config_dir).resolve() if config_dir is not None else self.config_dir
        return sync_surfaces_impl(target_surfaces, cfg_root, dry_run=dry_run)

    def install(
        self,
        mode: DeliveryMode = DeliveryMode.SYMLINK,
        dry_run: bool = False,
        target_dir: Optional[Path] = None,
        all_surfaces: bool = False,
    ) -> DeliveryResult:
        """
        Installs agyis-harness into the target plugin directory.

        Supports SYMLINK mode (live link) and COPY mode (isolated packaged release).
        """
        target = Path(target_dir) if target_dir is not None else self.default_target_dir
        self._verify_path_safety(target)

        # Enforce single-source agent delivery (Issue #30)
        duplicates_removed = self._enforce_single_source_agents(target, dry_run=dry_run)

        # Multi-surface sync if requested (Issues #29 & #23)
        surfaces_synced: List[Dict[str, Any]] = []
        if all_surfaces:
            surfaces_synced = self.sync_surfaces(dry_run=dry_run)

        # Clean up legacy plugin directory if migrating to agyis-harness
        if target.name == "agyis-harness":
            legacy_dir = target.parent / "psl-agy-harness"
            if legacy_dir.is_symlink() or legacy_dir.exists():
                if not dry_run:
                    try:
                        if legacy_dir.is_symlink():
                            legacy_dir.unlink()
                        elif legacy_dir.is_dir():
                            shutil.rmtree(legacy_dir)
                    except OSError:
                        pass
                duplicates_removed.append(str(legacy_dir))

        # Distributables discovery
        distributables: List[str] = []
        for item in ("plugin.json", "harness", "matrix.json", "hooks.json"):
            if self._find_distributable_item(item) is not None:
                distributables.append(item)

        if dry_run:
            items = list(distributables)
            if mode == DeliveryMode.WHEEL:
                items.append("wheel")
            return DeliveryResult(
                success=True,
                mode=mode.value,
                target_dir=target,
                source_dir=self.source_dir,
                items_installed=items,
                duplicates_removed=duplicates_removed,
                surfaces_synced=surfaces_synced,
                message=f"Dry-run: simulate {mode.value} installation to {target}",
            )

        if mode == DeliveryMode.SYMLINK:
            self._ensure_source_root_plugin_symlinks()
            if target.is_symlink():
                try:
                    if target.resolve() == self.source_dir.resolve():
                        self._install_bin(target)
                        self._enable_in_config(target.name)
                        return DeliveryResult(
                            success=True,
                            mode=DeliveryMode.SYMLINK.value,
                            target_dir=target,
                            source_dir=self.source_dir,
                            items_installed=distributables,
                            duplicates_removed=duplicates_removed,
                            surfaces_synced=surfaces_synced,
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
            self._enable_in_config(target.name)

            return DeliveryResult(
                success=True,
                mode=DeliveryMode.SYMLINK.value,
                target_dir=target,
                source_dir=self.source_dir,
                items_installed=distributables,
                duplicates_removed=duplicates_removed,
                surfaces_synced=surfaces_synced,
                message=f"Successfully symlinked plugin {target} -> {self.source_dir}",
            )

        elif mode == DeliveryMode.COPY:
            if target.is_symlink():
                target.unlink()
            target.mkdir(parents=True, exist_ok=True)

            installed_items = copy_distributable_tree(
                self.source_dir, target, self._find_distributable_item
            )

            self._install_bin(target)
            self._enable_in_config(target.name)

            return DeliveryResult(
                success=True,
                mode=DeliveryMode.COPY.value,
                target_dir=target,
                source_dir=self.source_dir,
                items_installed=installed_items,
                duplicates_removed=duplicates_removed,
                surfaces_synced=surfaces_synced,
                message=f"Successfully packaged and copied plugin to {target}",
            )

        elif mode == DeliveryMode.WHEEL:
            if target.is_symlink():
                target.unlink()
            elif target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            target.mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_out = Path(tmp_dir)
                wheel_path = self._build_frozen_wheel(tmp_out)
                with zipfile.ZipFile(wheel_path, "r") as zf:
                    zf.extractall(target)
                target_dist = target / "dist"
                target_dist.mkdir(parents=True, exist_ok=True)
                shutil.copy2(wheel_path, target_dist / wheel_path.name)

            installed_items = copy_distributable_tree(
                self.source_dir,
                target,
                self._find_distributable_item,
                skip_harness_package=True,
            )
            installed_items.append("wheel")
            installed_items.append("harness")

            # Scoped rule isolation: global plugin must only publish GLOBAL_AGENTS.md
            if (target / "rules" / "AGENTS.md").exists():
                try:
                    (target / "rules" / "AGENTS.md").unlink()
                except OSError:
                    pass
            global_rules_src = self.source_dir / "GLOBAL_AGENTS.md"
            if not global_rules_src.exists():
                global_rules_src = self.source_dir / "harness" / "rules" / "GLOBAL_AGENTS.md"
            if global_rules_src.exists():
                (target / "rules").mkdir(parents=True, exist_ok=True)
                shutil.copy2(global_rules_src, target / "rules" / "GLOBAL_AGENTS.md")

            self._install_bin(target)
            self._enable_in_config(target.name)

            return DeliveryResult(
                success=True,
                mode=DeliveryMode.WHEEL.value,
                target_dir=target,
                source_dir=self.source_dir,
                items_installed=installed_items,
                duplicates_removed=duplicates_removed,
                surfaces_synced=surfaces_synced,
                message=f"Successfully built and installed frozen release wheel to {target}",
            )

        raise ValueError(f"Unsupported delivery mode: {mode}")

    def uninstall(
        self,
        dry_run: bool = False,
        target_dir: Optional[Path] = None,
        clean_surfaces: bool = True,
    ) -> DeliveryResult:
        """
        Uninstalls the plugin from the target directory and unlinks bin_dir / psl.

        Safety invariant: if target is a symlink, unlinks ONLY the symlink
        without touching the resolved source path.
        """
        target = Path(target_dir) if target_dir is not None else self.default_target_dir
        self._verify_path_safety(target)

        if not dry_run:
            targets_to_unlink = (
                [self.bin_dir / "agyis", self.bin_dir / "psl"]
                + [d / "agyis" for d in self.aux_bin_dirs]
                + [d / "psl" for d in self.aux_bin_dirs]
            )
            for target_bin in targets_to_unlink:
                if target_bin.is_symlink() or target_bin.exists():
                    try:
                        target_bin.unlink()
                    except (PermissionError, OSError):
                        pass

            # Also clean up legacy plugin directory if present
            if target.name == "agyis-harness":
                legacy_dir = target.parent / "psl-agy-harness"
                if legacy_dir.is_symlink() or legacy_dir.exists():
                    try:
                        if legacy_dir.is_symlink():
                            legacy_dir.unlink()
                        elif legacy_dir.is_dir():
                            shutil.rmtree(legacy_dir)
                    except (PermissionError, OSError):
                        pass

        # Clean up surface symlinks (Issues #29 & #23)
        if clean_surfaces:
            for surface in self.surfaces:
                if not surface.exists():
                    continue
                for item in SYNC_SURFACE_ITEMS:
                    surface_item = surface / item
                    if surface_item.is_symlink():
                        should_unlink = False
                        canon = (self.config_dir / item).resolve()
                        try:
                            if surface_item.resolve() == canon:
                                should_unlink = True
                        except (OSError, ValueError):
                            pass
                        if not should_unlink:
                            try:
                                raw_target = os.readlink(surface_item)
                                raw_resolved = (
                                    (surface / raw_target).resolve()
                                    if not Path(raw_target).is_absolute()
                                    else Path(raw_target).resolve()
                                )
                                if raw_resolved == canon or str(self.config_dir) in raw_target:
                                    should_unlink = True
                            except OSError:
                                pass
                        if should_unlink and not dry_run:
                            try:
                                surface_item.unlink()
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

        if target.is_symlink():
            mode = DeliveryMode.SYMLINK.value
        elif (target / "dist").is_dir() or any(target.glob("*.dist-info")):
            mode = DeliveryMode.WHEEL.value
        else:
            mode = DeliveryMode.COPY.value

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
            target_mode = (
                DeliveryMode.WHEEL.value
                if (target / "dist").is_dir() or any(target.glob("*.dist-info"))
                else DeliveryMode.COPY.value
            )
            shutil.rmtree(target)
            return DeliveryResult(
                success=True,
                mode=target_mode,
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
            mode = (
                "wheel"
                if (target / "dist").is_dir() or any(target.glob("*.dist-info"))
                else "copy"
            )

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
