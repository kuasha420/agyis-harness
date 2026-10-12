# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workspace instantiation, tagged rules management, and stack-tailored skill deployment (ADR-030).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional

from harness.delivery.constants import REPO_ROOT
from harness.delivery.surfaces import find_workspace_root
from harness.skills import (
    STACK_PRESETS,
    detect_workspace_stack,
)

TAG_START = "<!-- Added by AGYIS-HARNESS -->"
TAG_END = "<!-- End AGYIS-HARNESS -->"
LEGACY_TAG_START = "<!-- Added by PSL-HARNESS -->"
LEGACY_TAG_END = "<!-- End PSL-HARNESS -->"

TAGGED_BLOCK_PATTERN = re.compile(
    r"<!-- Added by (?:AGYIS-HARNESS|PSL-HARNESS) -->[\s\S]*?<!-- End (?:AGYIS-HARNESS|PSL-HARNESS) -->"
)

STACK_SKILL_PRESETS: Dict[str, List[str]] = {
    **STACK_PRESETS,
    "audit": ["psl-audit-toolkit"],
    "all": [
        "psl-stack-typescript",
        "psl-stack-python",
        "psl-stack-systems",
        "psl-stack-shell",
        "psl-stack-backend",
        "psl-audit-toolkit",
    ],
}


STANDARD_VERB_DESCRIPTIONS: Dict[str, str] = {
    "test": "Run complete project test suite",
    "build": "Build project artifacts",
    "lint": "Code quality & linting checks",
    "dev": "Start local development server",
    "start": "Launch production runtime",
    "check": "Verification & type check",
    "typecheck": "Static type checking",
    "format": "Code style & formatting",
    "clean": "Clean build artifacts & caches",
    "install": "Install project dependencies",
    "all": "Build all targets",
    "vet": "Go static analysis",
    "run": "Run project executable",
}


def extract_command_dictionary(workspace_dir: Path) -> Dict[str, str]:
    """
    Extracts an explicit project command dictionary from workspace configuration.

    Inspects in order:
    1. package.json scripts (Node / TypeScript)
    2. pyproject.toml / test runner configs (Python)
    3. Cargo.toml (Rust)
    4. go.mod (Go)
    5. Makefile targets (Systems / C / Shell)

    Returns a mapping of semantic actions/verbs (e.g. 'test', 'build', 'lint', 'dev')
    to their executable command strings (e.g. 'pnpm test', 'make build', 'pytest').
    """
    ws = Path(workspace_dir).resolve()
    if not ws.exists() or not ws.is_dir():
        return {}

    commands: Dict[str, str] = {}

    # 1. Node / TypeScript (package.json)
    pkg_json = ws / "package.json"
    if pkg_json.is_file():
        try:
            import json

            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            raw_scripts = data.get("scripts", {})
            if isinstance(raw_scripts, dict):
                # Detect package manager
                if (ws / "pnpm-lock.yaml").is_file() or (ws / "pnpm-workspace.yaml").is_file():
                    pm = "pnpm"
                elif (ws / "yarn.lock").is_file():
                    pm = "yarn"
                elif (ws / "bun.lockb").is_file() or (ws / "bun.lock").is_file():
                    pm = "bun"
                else:
                    pm = "npm"

                def format_node_cmd(script_name: str) -> str:
                    if pm == "pnpm":
                        return f"pnpm {script_name}"
                    elif pm == "yarn":
                        return f"yarn {script_name}"
                    elif pm == "bun":
                        return "bun test" if script_name == "test" else f"bun run {script_name}"
                    else:
                        if script_name in ("test", "start"):
                            return f"npm {script_name}"
                        return f"npm run {script_name}"

                priority_verbs = [
                    "test",
                    "build",
                    "lint",
                    "dev",
                    "start",
                    "check",
                    "format",
                    "typecheck",
                    "clean",
                ]
                for v in priority_verbs:
                    if v in raw_scripts and v not in commands:
                        commands[v] = format_node_cmd(v)
                for k in raw_scripts:
                    if k not in commands and len(commands) < 12:
                        commands[k] = format_node_cmd(k)
        except Exception:
            pass

    # 2. Python (pyproject.toml)
    pyproj = ws / "pyproject.toml"
    if pyproj.is_file():
        if (ws / "poetry.lock").is_file():
            prefix = "poetry run "
        elif (ws / "uv.lock").is_file():
            prefix = "uv run "
        elif (ws / "Pipfile.lock").is_file() or (ws / "Pipfile").is_file():
            prefix = "pipenv run "
        else:
            prefix = ""

        toml_data: Dict[str, Any] = {}
        try:
            import tomllib

            toml_data = tomllib.loads(pyproj.read_text(encoding="utf-8"))
        except Exception:
            pass

        tools = toml_data.get("tool", {}) if isinstance(toml_data, dict) else {}
        if "test" not in commands:
            has_pytest = (
                "pytest" in tools
                or (ws / "tests").is_dir()
                or (ws / "test").is_dir()
                or (ws / "pytest.ini").is_file()
                or (ws / "setup.cfg").is_file()
            )
            if has_pytest:
                commands["test"] = f"{prefix}pytest"
            elif (ws / "tests").is_dir():
                commands["test"] = f"{prefix}python3 -m unittest discover -s tests -v"

        if "lint" not in commands:
            if "ruff" in tools:
                commands["lint"] = f"{prefix}ruff check ."
            elif "flake8" in tools:
                commands["lint"] = f"{prefix}flake8"

        if "format" not in commands:
            if "ruff" in tools:
                commands["format"] = f"{prefix}ruff format ."
            elif "black" in tools:
                commands["format"] = f"{prefix}black ."

        if "check" not in commands and "typecheck" not in commands:
            if "mypy" in tools:
                commands["check"] = f"{prefix}mypy ."
            elif "pyright" in tools:
                commands["check"] = f"{prefix}pyright"

    # 3. Rust (Cargo.toml)
    if (ws / "Cargo.toml").is_file():
        if "test" not in commands:
            commands["test"] = "cargo test"
        if "build" not in commands:
            commands["build"] = "cargo build"
        if "lint" not in commands:
            commands["lint"] = "cargo clippy"

    # 4. Go (go.mod)
    if (ws / "go.mod").is_file():
        if "test" not in commands:
            commands["test"] = "go test ./..."
        if "build" not in commands:
            commands["build"] = "go build ./..."
        if "vet" not in commands:
            commands["vet"] = "go vet ./..."

    # 5. Systems / C / Shell (Makefile)
    makefile = ws / "Makefile"
    if makefile.is_file():
        try:
            content = makefile.read_text(encoding="utf-8", errors="replace")
            targets = re.findall(r"^([a-zA-Z0-9_\.-]+)\s*:(?!=)", content, re.MULTILINE)
            valid_targets = [
                t
                for t in targets
                if not t.startswith(".") and not t.startswith("_") and "%" not in t
            ]
            common_make = [
                "test",
                "build",
                "lint",
                "check",
                "clean",
                "all",
                "install",
                "dev",
                "run",
                "format",
            ]
            for ct in common_make:
                if ct in valid_targets and ct not in commands:
                    commands[ct] = f"make {ct}"
            for t in valid_targets:
                if t not in commands and len(commands) < 12:
                    commands[t] = f"make {t}"
        except Exception:
            pass

    return commands


def format_command_dictionary(cmd_dict: Dict[str, str]) -> str:
    """Formats the command dictionary into shell code block annotations."""
    if not cmd_dict:
        return ""
    lines = ["# 🧪 Project Verification & Native Toolchain"]
    for verb, cmd in cmd_dict.items():
        desc = STANDARD_VERB_DESCRIPTIONS.get(verb, f"Execute {verb}")
        lines.append(f"{cmd:<46} # {desc}".rstrip())
    return "\n".join(lines)


@dataclass
class WorkspaceInstallResult:
    """Outcome report for workspace initialization."""

    success: bool
    workspace_dir: Path
    stack: str
    skills_installed: List[str] = field(default_factory=list)
    skills_skipped: List[str] = field(default_factory=list)
    agents_installed: List[str] = field(default_factory=list)
    agents_skipped: List[str] = field(default_factory=list)
    rules_updated: bool = False
    legacy_notice: Optional[str] = None
    command_dictionary: Dict[str, str] = field(default_factory=dict)
    dry_run: bool = False
    message: str = ""


def install_workspace(
    workspace_dir: Path,
    stack: Optional[str] = None,
    skills: Optional[List[str]] = None,
    agents: Optional[List[str]] = None,
    include_agents: bool = False,
    dedup: bool = True,
    override: bool = False,
    source_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> WorkspaceInstallResult:
    """
    Initializes a workspace with stack-tailored skills, tagged rules, and optional subagents.

    - Preserves existing rules in <ws>/AGENTS.md with tagged AGYIS delimiters (upgrading legacy PSL delimiters).
    - Installs stack skills to <ws>/.agents/skills/.
    - Installs subagents to <ws>/.agents/agents/ if requested.
    - Enforces byte-comparison deduplication and non-destructive overwrite guards.
    - Emits actionable notice if legacy .agent/ configuration is detected.
    - Supports dry-run preview mode with zero filesystem modifications.
    """
    ws = Path(workspace_dir).resolve()
    if not ws.exists() and not dry_run:
        ws.mkdir(parents=True, exist_ok=True)

    src = Path(source_dir).resolve() if source_dir else REPO_ROOT.resolve()

    # Legacy setup check
    legacy_notice: Optional[str] = None
    if (ws / ".agent").exists() and (ws / ".agent").is_dir():
        legacy_notice = (
            "Legacy '.agent/' directory detected. Run the /psl-harmonize skill "
            "to migrate legacy agents, workflows, and rules to modern '.agents/' structure."
        )
    elif (ws / "workflows").exists() or (ws / ".agent" / "workflows").exists():
        legacy_notice = (
            "Legacy workflow files detected. Run the /psl-harmonize skill "
            "to migrate legacy workflows to modular skills."
        )

    # Stack detection
    if stack:
        detected_stack = stack.strip().lower()
    else:
        detected_stack = detect_workspace_stack(ws) or "generic"

    # Command dictionary extraction
    cmd_dict = extract_command_dictionary(ws)

    # Skills installation
    src_skills = (src / "harness" / "skills") if (src / "harness" / "skills").is_dir() else (src / "skills")
    if skills is not None:
        selected_skills = list(skills)
    else:
        selected_skills = list(STACK_SKILL_PRESETS.get(detected_stack, []))

    target_skills_dir = ws / ".agents" / "skills"
    skills_installed: List[str] = []
    skills_skipped: List[str] = []

    if selected_skills and src_skills.is_dir():
        if not dry_run:
            target_skills_dir.mkdir(parents=True, exist_ok=True)
        for sk_name in selected_skills:
            sk_dir = src_skills / sk_name
            if not (sk_dir.exists() and sk_dir.is_dir()):
                for cand in src_skills.iterdir():
                    if cand.is_dir() and cand.name.lower().replace("_", "-") == sk_name.lower().replace("_", "-"):
                        sk_dir = cand
                        break
            if not (sk_dir.exists() and sk_dir.is_dir()):
                continue

            dst_sk_dir = target_skills_dir / sk_dir.name
            dst_skill_file = dst_sk_dir / "SKILL.md"
            src_skill_file = sk_dir / "SKILL.md"

            if dst_skill_file.exists() and not override:
                is_identical = (
                    src_skill_file.exists()
                    and dst_skill_file.read_bytes() == src_skill_file.read_bytes()
                )
                if dedup and is_identical:
                    skills_skipped.append(sk_dir.name)
                    continue
                skills_skipped.append(sk_dir.name)
                continue

            if not dry_run:
                dst_sk_dir.mkdir(parents=True, exist_ok=True)
                for item in sk_dir.rglob("*"):
                    if item.is_file():
                        rel = item.relative_to(sk_dir)
                        out_f = dst_sk_dir / rel
                        out_f.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, out_f)
            skills_installed.append(sk_dir.name)

    # Agents installation
    src_agents = (src / "harness" / "agents") if (src / "harness" / "agents").is_dir() else (src / "agents")
    agents_installed: List[str] = []
    agents_skipped: List[str] = []
    if agents is not None:
        selected_agents = list(agents)
    elif include_agents:
        selected_agents = [p.stem for p in sorted(src_agents.glob("*.md"))]
    else:
        selected_agents = []

    if selected_agents and src_agents.is_dir():
        target_agents_dir = ws / ".agents" / "agents"
        if not dry_run:
            target_agents_dir.mkdir(parents=True, exist_ok=True)
        for ag_name in selected_agents:
            ag_src = src_agents / f"{ag_name}.md"
            if not ag_src.is_file():
                for cand in src_agents.glob("*.md"):
                    if cand.stem.lower().replace("_", "-") == ag_name.lower().replace("_", "-"):
                        ag_src = cand
                        break
            if not ag_src.is_file():
                continue

            dst_ag_file = target_agents_dir / ag_src.name
            if dst_ag_file.exists() and not override:
                is_identical = dst_ag_file.read_bytes() == ag_src.read_bytes()
                if dedup and is_identical:
                    agents_skipped.append(ag_src.stem)
                    continue
                agents_skipped.append(ag_src.stem)
                continue

            if not dry_run:
                shutil.copy2(ag_src, dst_ag_file)
            agents_installed.append(ag_src.stem)

    # Tagged rules management in <ws>/AGENTS.md
    rules_updated = False
    rules_path = ws / "AGENTS.md"
    universal_rules_file = src / "harness" / "rules" / "universal_agents.md"
    if not universal_rules_file.is_file():
        for cand in [src / "rules" / "universal_agents.md", src / "rules" / "AGENTS.md"]:
            if cand.is_file():
                universal_rules_file = cand
                break
    if universal_rules_file.is_file():
        universal_text = universal_rules_file.read_text(encoding="utf-8").strip()
        formatted_cmds = format_command_dictionary(cmd_dict)
        if formatted_cmds:
            if "```bash\n" in universal_text:
                universal_text = universal_text.replace("```bash\n", f"```bash\n{formatted_cmds}\n\n", 1)
            else:
                universal_text = f"```bash\n{formatted_cmds}\n```\n\n{universal_text}"

        tagged_block = f"{TAG_START}\n{universal_text}\n{TAG_END}"

        if rules_path.exists():
            existing_rules = rules_path.read_text(encoding="utf-8")
            pattern = TAGGED_BLOCK_PATTERN
            if pattern.search(existing_rules):
                new_rules = pattern.sub(tagged_block, existing_rules)
            else:
                existing_clean = existing_rules.rstrip()
                if existing_clean:
                    new_rules = f"{existing_clean}\n\n{tagged_block}\n"
                else:
                    new_rules = f"{tagged_block}\n"
            if new_rules != existing_rules:
                if not dry_run:
                    rules_path.write_text(new_rules, encoding="utf-8")
                rules_updated = True
        else:
            if not dry_run:
                rules_path.write_text(f"{tagged_block}\n", encoding="utf-8")
            rules_updated = True

    return WorkspaceInstallResult(
        success=True,
        workspace_dir=ws,
        stack=detected_stack,
        skills_installed=skills_installed,
        skills_skipped=skills_skipped,
        agents_installed=agents_installed,
        agents_skipped=agents_skipped,
        rules_updated=rules_updated,
        legacy_notice=legacy_notice,
        command_dictionary=cmd_dict,
        dry_run=dry_run,
        message=(
            f"[DRY-RUN] Workspace initialization preview for stack '{detected_stack}'"
            if dry_run
            else f"Workspace initialized successfully for stack '{detected_stack}'"
        ),
    )
