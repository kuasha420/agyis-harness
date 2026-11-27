# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workspace SSOT Documentation, Manifest, Tool-Registry & Telemetry Sync Validator (Task 1.2D).

Pure `harness.delivery` validator with zero coupling to `pipeline/` or `harness.commands`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tomllib
import unittest
from typing import Any, Dict, List, Optional, Tuple

from harness.cli_parsers_core import register_core_parsers
from harness.cli_parsers_ops import register_ops_parsers
from harness.subagents.spec import (
    ANTIGRAVITY_PLATFORM_TOOLS,
    CANONICAL_PLATFORM_TOOLS,
    LEGACY_PLATFORM_TOOL_ALIASES,
    MAX_AGENT_TOOLS,
    ROOT_PLAN_MODE_TOOLS,
    SWARM_RUNTIME_TOOLS,
)
from harness.utils import theme

_TEST_PARITY_DOCS: Tuple[str, ...] = (
    "README.md",
    "roadmap.md",
    "docs/taxonomy/project-ledger.md",
    "docs/official-specs/testing-contracts.md",
    "docs/official-specs/cli-palette.md",
    "docs/adr/README.md",
    "harness/rules/AGENTS.md",
    "harness/agents/agyis_auditor.md",
    "harness/skills/subagent-router/SKILL.md",
    "harness/skills/psl-stack-python/SKILL.md",
    "harness/skills/subagent-router/references/pipeline-lifecycle.md",
)

_TOTAL_TEST_RE = re.compile(
    r"(?:Tests-(?P<badge>\d+)_Hermetic_Passing"
    r"|All\s+\*\*(?P<bold>\d[\d,]*)\*\*\s+unit,\s+integration"
    r"|\b(?P<count>\d[\d,]{3,})\s*(?:\*\*\s*)?(?:hermetic\s+|automated\s+|unit\s+|and\s+contract\s+|native\s+)*tests?\b)",
    re.I,
)
_MODULE_COUNT_RE = re.compile(
    r"(?:\b(?P<mods>\d{3})\s+(?:total\s+)?test\s+(?:files|modules)\b"
    r"|\((?P<tot>\d{3})\s+total(?:,\s*`python3|\)))",
    re.I,
)
_HISTORICAL_LINE_MARKERS = (
    "| **`v0.",
    "| **`v1.0.",
    "| **`v1.1.",
    "(historical baseline",
    "pre-hardening baseline",
)
_SEMVER_PATTERN = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
_OG_OVERLAY_VER_RE = re.compile(rf"\bVersion\s+(?P<ver>{_SEMVER_PATTERN})\b")
_SITE_RELEASE_VERSION_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("title/brand release version", re.compile(rf"\bAgyis(?:\s+Harness)?\s+(?P<ver>{_SEMVER_PATTERN})\b")),
    ("release tag URL", re.compile(rf"/releases/tag/v(?P<ver>{_SEMVER_PATTERN})\b")),
    ("install CTA version", re.compile(rf"\bInstall\s+v(?P<ver>{_SEMVER_PATTERN})\b")),
    ("verification ledger version", re.compile(rf"\bVersion\s+(?P<ver>{_SEMVER_PATTERN})\s+verification ledger\b")),
    ("wheel install version", re.compile(rf"\bfrozen\s+v(?P<ver>{_SEMVER_PATTERN})\s+wheel\b")),
    ("release link CTA version", re.compile(rf"\bView\s+v(?P<ver>{_SEMVER_PATTERN})\s+release\b")),
    ("brand card release version", re.compile(rf"\bfor\s+v(?P<ver>{_SEMVER_PATTERN})\s+release\s+links\b")),
)


def count_live_tests_and_modules(tests_dir: Path, workspace_root: Path) -> Tuple[int, int]:
    """Discover exact live unittest cases and test_*.py module file count."""
    if not tests_dir.is_dir():
        return 0, 0
    mod_count = sum(1 for p in tests_dir.rglob("test_*.py") if p.is_file())
    top_dir = workspace_root if (tests_dir / "__init__.py").is_file() else tests_dir
    orig_path = list(sys.path)
    try:
        for p_ins in (str(top_dir), str(workspace_root)):
            if p_ins not in sys.path:
                sys.path.insert(0, p_ins)
        loader = unittest.TestLoader()
        suite = loader.discover(start_dir=str(tests_dir), top_level_dir=str(top_dir))
        return suite.countTestCases(), mod_count
    finally:
        sys.path[:] = orig_path


def count_surface_inventory(workspace_root: Path) -> Dict[str, int]:
    """Count product skills, agent specs, hooks.json blocks, and registered CLI subparsers."""
    skills_dir = workspace_root / "harness" / "skills"
    agents_dir = workspace_root / "harness" / "agents"
    hooks_file = workspace_root / "harness" / "hooks" / "hooks.json"

    skills = sum(1 for p in skills_dir.glob("*/SKILL.md") if p.is_file()) if skills_dir.is_dir() else 0
    agents = sum(1 for p in agents_dir.glob("*.md") if p.is_file()) if agents_dir.is_dir() else 0
    hooks = 0
    if hooks_file.is_file():
        try:
            hdata = json.loads(hooks_file.read_text(encoding="utf-8"))
            if isinstance(hdata, dict):
                hooks = len(hdata)
        except (OSError, json.JSONDecodeError, ValueError):
            hooks = 0

    parser = argparse.ArgumentParser(prog="agyis", add_help=False)
    subparsers = parser.add_subparsers(dest="command")
    register_core_parsers(subparsers)
    register_ops_parsers(subparsers)
    name_parser_map = getattr(subparsers, "_name_parser_map", {})
    cli_subparsers = len(name_parser_map)
    cli_logical_subcommands = len({id(p) for p in name_parser_map.values()})
    return {
        "skills": skills,
        "agents": agents,
        "hooks": hooks,
        "cli_subparsers": cli_subparsers,
        "cli_logical_subcommands": cli_logical_subcommands,
    }


def _check_manifests(root: Path, mismatches: List[str]) -> Dict[str, Optional[str]]:
    """Verify pyproject.toml agrees with plugin.json, harness/__init__.py, package.json, uv.lock, and og-overlay.svg."""
    py_ver: Optional[str] = None
    py_name: str = "agyis-harness"
    plugin_ver: Optional[str] = None
    harness_init_ver: Optional[str] = None
    package_json_ver: Optional[str] = None
    uv_lock_ver: Optional[str] = None
    og_overlay_ver: Optional[str] = None

    py_file = root / "pyproject.toml"
    if py_file.is_file():
        py_raw = py_file.read_text(encoding="utf-8", errors="replace")
        try:
            py_doc = tomllib.loads(py_raw)
            proj = py_doc.get("project") if isinstance(py_doc, dict) else None
            if isinstance(proj, dict):
                if isinstance(proj.get("version"), str) and proj["version"].strip():
                    py_ver = proj["version"].strip()
                if isinstance(proj.get("name"), str) and proj["name"].strip():
                    py_name = proj["name"].strip()
        except (tomllib.TOMLDecodeError, ValueError):
            m = re.search(r'^version\s*=\s*"([^"]+)"', py_raw, re.M)
            if m:
                py_ver = m.group(1).strip()

    for cand_rel in ("plugin.json", ".agents/plugin.json", ".claude-plugin/plugin.json"):
        p_file = root / cand_rel
        if p_file.is_file():
            try:
                pdata = json.loads(p_file.read_text(encoding="utf-8"))
                ver = str(pdata.get("version") or "").strip() if isinstance(pdata, dict) else ""
                if cand_rel == "plugin.json":
                    plugin_ver = ver or None
                if py_ver and ver and ver != py_ver:
                    mismatches.append(f"Manifest version mismatch: pyproject.toml={py_ver} != {cand_rel}={ver}")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                mismatches.append(f"Malformed manifest {cand_rel}: {exc}")

    if py_ver and not plugin_ver and (root / "plugin.json").is_file():
        mismatches.append("Missing version field in plugin.json")

    init_file = root / "harness" / "__init__.py"
    if init_file.is_file():
        init_raw = init_file.read_text(encoding="utf-8", errors="replace")
        m_init = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_raw, re.M)
        if m_init:
            harness_init_ver = m_init.group(1).strip()
            if py_ver and harness_init_ver != py_ver:
                mismatches.append(
                    f"Manifest version mismatch: pyproject.toml={py_ver} != harness/__init__.py={harness_init_ver}"
                )
        elif py_ver:
            mismatches.append("Missing __version__ declaration in harness/__init__.py")

    pkg_json_file = root / "package.json"
    if pkg_json_file.is_file():
        try:
            pkg_data = json.loads(pkg_json_file.read_text(encoding="utf-8"))
            ver = str(pkg_data.get("version") or "").strip() if isinstance(pkg_data, dict) else ""
            package_json_ver = ver or None
            if py_ver and ver and ver != py_ver:
                mismatches.append(f"Manifest version mismatch: pyproject.toml={py_ver} != package.json={ver}")
            elif py_ver and not ver:
                mismatches.append("Missing version field in package.json")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            mismatches.append(f"Malformed manifest package.json: {exc}")

    uv_lock_file = root / "uv.lock"
    if uv_lock_file.is_file():
        try:
            lock_doc = tomllib.loads(uv_lock_file.read_text(encoding="utf-8", errors="replace"))
            packages = lock_doc.get("package") if isinstance(lock_doc, dict) else None
            if isinstance(packages, list):
                for pkg in packages:
                    if isinstance(pkg, dict) and pkg.get("name") in (py_name, "agyis-harness"):
                        ver = str(pkg.get("version") or "").strip()
                        if ver:
                            uv_lock_ver = ver
                            break
            if py_ver and uv_lock_ver and uv_lock_ver != py_ver:
                mismatches.append(f"Manifest version mismatch: pyproject.toml={py_ver} != uv.lock={uv_lock_ver}")
            elif py_ver and not uv_lock_ver:
                mismatches.append(f"Missing package version entry for '{py_name}' in uv.lock")
        except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
            mismatches.append(f"Malformed lockfile uv.lock: {exc}")

    og_svg_file = root / "website" / "brand" / "svg" / "og-overlay.svg"
    if og_svg_file.is_file():
        og_raw = og_svg_file.read_text(encoding="utf-8", errors="replace")
        m_og = _OG_OVERLAY_VER_RE.search(og_raw)
        if m_og:
            og_overlay_ver = m_og.group("ver").strip()
            if py_ver and og_overlay_ver != py_ver:
                mismatches.append(
                    f"Manifest version mismatch: pyproject.toml={py_ver} != website/brand/svg/og-overlay.svg={og_overlay_ver}"
                )
        elif py_ver:
            mismatches.append("Missing 'Version <semver>' text in website/brand/svg/og-overlay.svg")

    return {
        "pyproject_version": py_ver,
        "plugin_version": plugin_ver,
        "harness_init_version": harness_init_ver,
        "package_json_version": package_json_ver,
        "uv_lock_version": uv_lock_ver,
        "og_overlay_version": og_overlay_ver,
    }


def _check_tool_registry(root: Path, mismatches: List[str]) -> Dict[str, int]:
    """Verify Antigravity tool registry counts and SSOT specification doc parity."""
    counts = {
        "canonical": len(CANONICAL_PLATFORM_TOOLS),
        "max_agent_tools": MAX_AGENT_TOOLS,
        "swarm_runtime": len(SWARM_RUNTIME_TOOLS),
        "root_plan_mode": len(ROOT_PLAN_MODE_TOOLS),
        "legacy_aliases": len(LEGACY_PLATFORM_TOOL_ALIASES),
        "antigravity_platform_total": len(ANTIGRAVITY_PLATFORM_TOOLS),
    }
    if counts["canonical"] > MAX_AGENT_TOOLS:
        mismatches.append(f"CANONICAL_PLATFORM_TOOLS ({counts['canonical']}) exceeds MAX_AGENT_TOOLS ({MAX_AGENT_TOOLS})")
    overlap = CANONICAL_PLATFORM_TOOLS & ROOT_PLAN_MODE_TOOLS
    if overlap:
        mismatches.append(f"ROOT_PLAN_MODE_TOOLS overlaps CANONICAL_PLATFORM_TOOLS: {sorted(overlap)}")

    custom_agents_doc = root / "docs" / "official-specs" / "custom-agents.md"
    if custom_agents_doc.is_file():
        text = custom_agents_doc.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\b(?:16|20)\b\s*canonical", text, re.I) or "totaling **32** entries" in text:
            mismatches.append("docs/official-specs/custom-agents.md still lists outdated canonical/total tool counts")

    adr_readme = root / "docs" / "adr" / "README.md"
    if adr_readme.is_file():
        text = adr_readme.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\b16\s+canonical\b|\b28-tool\b|\b28\s+tools\b", text, re.I):
            mismatches.append("docs/adr/README.md still cites outdated 16 canonical or 28 tools figure")

    agent_builder_skill = root / "harness" / "skills" / "agent-builder" / "SKILL.md"
    if agent_builder_skill.is_file():
        text = agent_builder_skill.read_text(encoding="utf-8", errors="replace")
        if re.search(r"obsolete v1 names\s*\([^)]*manage_subagents", text, re.I):
            mismatches.append("harness/skills/agent-builder/SKILL.md still classifies canonical 'manage_subagents' as obsolete v1")
    return counts


def _check_test_and_empirical_parity(
    root: Path,
    live_tests: int,
    live_modules: int,
    surface: Dict[str, int],
    include_site: bool,
    mismatches: List[str],
    py_ver: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify SSOT docs against live test counts and Gate 0 empirical telemetry JSON bundles."""
    if live_tests > 0:
        for rel_path in _TEST_PARITY_DOCS:
            fpath = root / rel_path
            if not fpath.is_file():
                continue
            for idx, line in enumerate(fpath.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if any(marker in line for marker in _HISTORICAL_LINE_MARKERS):
                    continue
                for tm in _TOTAL_TEST_RE.finditer(line):
                    raw_num = (tm.group("badge") or tm.group("bold") or tm.group("count") or "").replace(",", "")
                    if raw_num.isdigit():
                        claimed = int(raw_num)
                        if claimed >= 1500 and claimed != live_tests:
                            mismatches.append(f"{rel_path}:{idx} claims {claimed:,} tests (live discovered: {live_tests:,})")
                for mm in _MODULE_COUNT_RE.finditer(line):
                    raw_mod = (mm.group("mods") or mm.group("tot") or "").strip()
                    if raw_mod.isdigit() and int(raw_mod) >= 50 and int(raw_mod) != live_modules:
                        mismatches.append(f"{rel_path}:{idx} claims {raw_mod} test modules (live discovered: {live_modules})")

    empirical: Dict[str, Any] = {}
    data_dir = root / "website" / "data"
    overview_file = data_dir / "overview.json"
    eras_file = data_dir / "eras.json"
    if overview_file.is_file():
        try:
            ov = json.loads(overview_file.read_text(encoding="utf-8"))
            if isinstance(ov, dict):
                totals = ov.get("totals") if isinstance(ov.get("totals"), dict) else ov
                inv = ov.get("workspace_inventory") if isinstance(ov.get("workspace_inventory"), dict) else ov
                sessions = totals.get("total_sessions")
                empirical["total_sessions"] = sessions
                for key_surf, surf_label in (("skills", "skills"), ("agents", "agents"), ("hooks", "hooks")):
                    node = inv.get(key_surf)
                    if isinstance(node, dict) and isinstance(node.get("count"), int) and surface.get(surf_label) is not None:
                        if node["count"] != surface[surf_label]:
                            mismatches.append(
                                f"website/data/overview.json {key_surf}.count={node['count']} != live {surface[surf_label]}"
                            )
                if sessions is not None:
                    sessions_fmt = f"{int(sessions):,}"
                    for rel_doc in ("docs/taxonomy/empirical-baselines.md", "README.md"):
                        df = root / rel_doc
                        if df.is_file():
                            dtxt = df.read_text(encoding="utf-8", errors="replace")
                            if sessions_fmt not in dtxt:
                                mismatches.append(f"{rel_doc} missing Gate 0 baseline '{sessions_fmt}' sessions from website/data/overview.json")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            mismatches.append(f"Failed parsing website/data/overview.json: {exc}")

    if eras_file.is_file():
        try:
            er = json.loads(eras_file.read_text(encoding="utf-8"))
            era_list = er.get("eras") if isinstance(er, dict) else None
            if isinstance(era_list, list):
                empirical["eras_count"] = len(era_list)
                eb_doc = root / "docs" / "taxonomy" / "empirical-baselines.md"
                if eb_doc.is_file() and f"{len(era_list)} eras" not in eb_doc.read_text(encoding="utf-8", errors="replace"):
                    mismatches.append(f"docs/taxonomy/empirical-baselines.md missing '{len(era_list)} eras' baseline from website/data/eras.json")
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    if include_site and (root / "website").is_dir():
        for html_file in sorted((root / "website").rglob("*.html")):
            rel_html = html_file.relative_to(root).as_posix()
            htxt = html_file.read_text(encoding="utf-8", errors="replace")
            for idx, line in enumerate(htxt.splitlines(), 1):
                if any(marker in line for marker in _HISTORICAL_LINE_MARKERS):
                    continue
                if live_tests > 0:
                    for tm in _TOTAL_TEST_RE.finditer(line):
                        raw_num = (tm.group("badge") or tm.group("bold") or tm.group("count") or "").replace(",", "")
                        if raw_num.isdigit() and int(raw_num) >= 1500 and int(raw_num) != live_tests:
                            mismatches.append(f"{rel_html}:{idx} claims {int(raw_num):,} tests (live: {live_tests:,})")
                if py_ver:
                    for label, pattern in _SITE_RELEASE_VERSION_PATTERNS:
                        for vm in pattern.finditer(line):
                            found_ver = vm.group("ver").strip()
                            if found_ver != py_ver:
                                mismatches.append(
                                    f"{rel_html}:{idx} {label} '{found_ver}' != pyproject.toml '{py_ver}'"
                                )
    return empirical


def run_sync_check(
    workspace_root: Optional[Path] = None,
    *,
    include_site: bool = False,
) -> Dict[str, Any]:
    """Run all Wave 1.2 SSOT parity checks and return a structured report."""
    root = Path(workspace_root).resolve() if workspace_root is not None else Path.cwd().resolve()
    mismatches: List[str] = []

    manifests = _check_manifests(root, mismatches)
    tool_registry = _check_tool_registry(root, mismatches)
    surface = count_surface_inventory(root)
    live_tests, live_modules = count_live_tests_and_modules(root / "tests", root)
    empirical = _check_test_and_empirical_parity(
        root,
        live_tests,
        live_modules,
        surface,
        include_site,
        mismatches,
        py_ver=manifests.get("pyproject_version"),
    )

    return {
        "status": "PASS" if not mismatches else "FAIL",
        "workspace": str(root),
        "include_site": include_site,
        "manifest": manifests,
        "tool_registry": tool_registry,
        "surface_inventory": surface,
        "tests": {
            "live_tests": live_tests,
            "live_modules": live_modules,
        },
        "empirical_baselines": empirical,
        "mismatches": mismatches,
    }


def format_sync_check_report(report: Dict[str, Any]) -> str:
    """Format human-readable terminal summary for `agyis audit sync-check`."""
    status_val = str(report.get("status", "FAIL"))
    badge_kind = "PASS" if status_val == "PASS" else "FAIL"
    lines = [
        theme.banner("Agyis SSOT Sync Check", badge_label=status_val, status=badge_kind),
        f" Manifest:    pyproject={report['manifest'].get('pyproject_version')} plugin={report['manifest'].get('plugin_version')}",
        (
            " Tools:       "
            f"canonical={report['tool_registry'].get('canonical')}/"
            f"{report['tool_registry'].get('max_agent_tools')}, "
            f"root_plan={report['tool_registry'].get('root_plan_mode')}, "
            f"legacy={report['tool_registry'].get('legacy_aliases')}, "
            f"total={report['tool_registry'].get('antigravity_platform_total')}"
        ),
        (
            " Surfaces:    "
            f"skills={report['surface_inventory'].get('skills')}, "
            f"agents={report['surface_inventory'].get('agents')}, "
            f"hooks={report['surface_inventory'].get('hooks')}, "
            f"cli_subparsers={report['surface_inventory'].get('cli_subparsers')} "
            f"({report['surface_inventory'].get('cli_logical_subcommands', report['surface_inventory'].get('cli_subparsers'))} logical)"
        ),
        f" Tests:       {report['tests'].get('live_tests'):,} live across {report['tests'].get('live_modules')} modules",
        f" IncludeSite: {report.get('include_site')}",
        theme.rule(),
    ]
    mismatches = report.get("mismatches") or []
    if not mismatches:
        lines.append(" " + theme.badge("PASS", "PASS: Zero SSOT drift detected."))
    else:
        lines.append(" " + theme.badge("FAIL", f"FAIL: {len(mismatches)} mismatch(es) detected:"))
        for item in mismatches:
            lines.append(f"  - {item}")
    lines.append(theme.rule("━"))
    return "\n".join(lines)
