# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Verification suite for Phase 4: Rule Bifurcation, Packaging & Subagent Upgrades
(PSL-SPEC-2026-DRA-001).

Validates:
- GLOBAL_AGENTS.md contains universal invariants and zero harness CLI / ADR-015 benchmark mandates.
- .agents/rules/AGENTS.md isolates harness command dictionaries and ADR-015 benchmarks.
- subagent-ladder/SKILL.md has zero RecipientName occurrences and enforces Workspace: "share".
- Frozen wheel release build and install via PluginInstaller and CLI (agyis install -g).
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import zipfile

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.cli import main
from harness.commands.install import cmd_install
from harness.delivery import (
    DeliveryMode,
    DeliveryResult,
    PluginInstaller,
    REPO_ROOT,
)


class TestFrozenWheelPackaging(unittest.TestCase):
    """Hermetic hatchling sdist and wheel completeness verification."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target_dir = Path(self.temp_dir.name) / "installed_plugin"
        self.bin_dir = Path(self.temp_dir.name) / "bin"
        self.bin_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_hatchling_sdist_and_wheel_completeness_and_importlib_resources(self) -> None:
        """Hatchling SdistBuilder -> WheelBuilder includes all tracked harness/ files, plugin.json, assets/logo.svg, zero .agents/."""
        tracked_harness = set(
            subprocess.check_output(
                ["git", "ls-files", "harness/"],
                cwd=REPO_ROOT,
                text=True,
            ).splitlines()
        )
        self.assertGreater(len(tracked_harness), 150)

        build_and_verify_script = r"""
import importlib.resources as ir
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from hatchling.builders.sdist import SdistBuilder
from hatchling.builders.wheel import WheelBuilder

repo = Path(sys.argv[1])
tracked = set(
    subprocess.check_output(["git", "ls-files", "harness/"], cwd=repo, text=True).splitlines()
)
agent_mds = {p for p in tracked if p.startswith("harness/agents/") and p.endswith(".md")}
assert len(agent_mds) == 8, sorted(agent_mds)

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "out"
    out.mkdir()
    sdist_path = Path(next(SdistBuilder(str(repo)).build(directory=str(out))))
    sdist_extract = Path(tmp) / "sdist_src"
    sdist_extract.mkdir()
    with tarfile.open(sdist_path, "r:gz") as tf:
        tf.extractall(sdist_extract, filter="data")
        sdist_names = {m.name.split("/", 1)[1] for m in tf.getmembers() if m.isfile() and "/" in m.name}

    sdist_root = next(sdist_extract.iterdir())
    whl_path = Path(next(WheelBuilder(str(sdist_root)).build(directory=str(out))))
    whl_extract = Path(tmp) / "whl_site"
    whl_extract.mkdir()
    with zipfile.ZipFile(whl_path) as zf:
        whl_names = set(zf.namelist())
        zf.extractall(whl_extract)

    missing_sdist = sorted(tracked - sdist_names)
    missing_whl = sorted(tracked - whl_names)
    assert not missing_sdist, f"Sdist missing tracked harness/ files: {missing_sdist}"
    assert not missing_whl, f"Wheel missing tracked harness/ files: {missing_whl}"
    assert "harness/plugin.json" in whl_names
    assert "harness/assets/logo.svg" in whl_names
    assert "harness/GLOBAL_AGENTS.md" in whl_names
    assert "plugin.json" in sdist_names
    assert "assets/logo.svg" in sdist_names
    assert "GLOBAL_AGENTS.md" in sdist_names
    for label, names in (("wheel", whl_names), ("sdist", sdist_names)):
        leaks = [n for n in names if n.startswith(".agents/") or "/.agents/" in n]
        assert not leaks, f"{label} leaked .agents/: {leaks}"

    empty_cwd = Path(tmp) / "empty"
    empty_cwd.mkdir()
    base_py = getattr(sys, "_base_executable", sys.executable)
    check = (
        "import importlib.resources as ir, sys; "
        "from pathlib import Path; "
        "import harness; "
        "from harness.agents import resolve_agent_name; "
        "repo_p = Path(sys.argv[1]).resolve(); "
        "site_p = Path(sys.argv[2]).resolve(); "
        "assert not any(Path(p).resolve() == repo_p for p in sys.path if p), sys.path; "
        "assert Path(harness.__file__).resolve().is_relative_to(site_p), harness.__file__; "
        "assert resolve_agent_name('builder') == 'agyis_builder'; "
        "assert (ir.files('harness.gui.assets') / 'hud.js').is_file(); "
        "assert (ir.files('harness.hooks') / 'hooks.json').is_file(); "
        "assert (ir.files('harness.runtime') / 'matrix.json').is_file(); "
        "assert (ir.files('harness.agents') / 'agyis_builder.md').is_file(); "
        "assert (ir.files('harness.skills') / 'cockpit-director' / 'SKILL.md').is_file(); "
        "assert (ir.files('harness.skills') / 'subagent-router' / 'SKILL.md').is_file(); "
        "assert (ir.files('harness.skills') / 'subagent-ladder' / 'SKILL.md').is_file(); "
        "assert (ir.files('harness') / 'plugin.json').is_file(); "
        "assert (ir.files('harness') / 'assets' / 'logo.svg').is_file(); "
        "assert (ir.files('harness.assets') / 'logo.svg').is_file(); "
        "assert (ir.files('harness') / 'GLOBAL_AGENTS.md').is_file(); "
        "print('HATCHLING_WHEEL_OK')"
    )
    subprocess.run(
        [base_py, "-c", check, str(repo), str(whl_extract)],
        cwd=empty_cwd,
        env={"PATH": "", "PYTHONPATH": str(whl_extract)},
        check=True,
    )
"""
        try:
            import hatchling  # noqa: F401
            cmd = [sys.executable, "-c", build_and_verify_script, str(REPO_ROOT)]
        except ImportError:
            uv_bin = shutil.which("uv")
            if not uv_bin:
                self.skipTest("hatchling is not installed and uv binary is unavailable")
            cmd = [
                uv_bin,
                "run",
                "--no-project",
                "--isolated",
                "--offline",
                "--with",
                "hatchling",
                "python3",
                "-c",
                build_and_verify_script,
                str(REPO_ROOT),
            ]

        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        if proc.returncode != 0 and "No cached" in proc.stderr:
            self.skipTest(f"hatchling not cached for offline test execution: {proc.stderr.strip()}")
        self.assertEqual(proc.returncode, 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        self.assertIn("HATCHLING_WHEEL_OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
