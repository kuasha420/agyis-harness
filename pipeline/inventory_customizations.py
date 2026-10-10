#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
PSL Harness for Google Antigravity™
Customization Inventory Scanner

Scans and catalogs:
- Built-in skills (~/.gemini/antigravity/builtin/skills/)
- Config & active skills (~/.gemini/config/skills/, ~/.gemini/antigravity/skills/)
- Plugins (~/.gemini/config/plugins/)
- Active MCP servers and tools (~/.gemini/config/mcp_config.json, ~/.gemini/antigravity/mcp/)
- Rules (GEMINI.md, AGENTS.md)
- Lifecycle hooks (~/.gemini/config/hooks.json)

Calculates declared tool counts, estimated token footprint, and operational scope.
Outputs to data/customization_inventory.json.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional


from harness.utils.frontmatter import parse_frontmatter
from harness.utils.tokens import estimate_tokens


def scan_skills_directory(skills_dir: Path, scope: str) -> list[dict[str, Any]]:
    """Scan a directory of skills and catalog SKILL.md metadata."""
    results = []
    if not skills_dir.exists() or not skills_dir.is_dir():
        return results

    for item in sorted(skills_dir.iterdir()):
        resolved = item.resolve()
        skill_file = resolved / "SKILL.md" if resolved.is_dir() else (item / "SKILL.md" if item.is_dir() else None)
        
        # If item itself is a SKILL.md file directly
        if item.is_file() and item.name == "SKILL.md":
            skill_file = item
            skill_name = item.parent.name
        elif skill_file and skill_file.exists():
            skill_name = item.name
        else:
            continue

        try:
            content = skill_file.read_text(encoding="utf-8", errors="replace")
            fm, body = parse_frontmatter(content)
            description = fm.get("description", "")
            
            # Check for subdirectories (scripts, examples, references)
            parent_dir = skill_file.parent
            subdirs = [p.name for p in parent_dir.iterdir() if p.is_dir()]
            
            # Count total files in skill folder
            total_files = sum(1 for _ in parent_dir.rglob("*") if _.is_file())
            total_bytes = sum(_.stat().st_size for _ in parent_dir.rglob("*") if _.is_file())

            results.append({
                "name": fm.get("name", skill_name),
                "scope": scope,
                "path": str(skill_file),
                "is_symlink": item.is_symlink(),
                "symlink_target": str(resolved) if item.is_symlink() else None,
                "description": description,
                "frontmatter": fm,
                "subdirectories": subdirs,
                "total_files": total_files,
                "file_size_bytes": skill_file.stat().st_size,
                "skill_dir_bytes": total_bytes,
                "estimated_injection_tokens": estimate_tokens(f"{skill_name}: {description}"),
                "estimated_full_tokens": estimate_tokens(content),
            })
        except Exception as e:
            results.append({
                "name": item.name,
                "scope": scope,
                "path": str(skill_file or item),
                "error": str(e)
            })

    return results


def scan_plugins(plugins_dir: Path) -> list[dict[str, Any]]:
    """Scan plugins directory for manifests, bundled skills, rules, hooks, and MCP configs."""
    results = []
    if not plugins_dir.exists() or not plugins_dir.is_dir():
        return results

    for item in sorted(plugins_dir.iterdir()):
        plugin_root = item.resolve() if item.is_symlink() else item
        if not plugin_root.is_dir():
            continue

        manifest_file = plugin_root / "plugin.json"
        manifest_data = {}
        if manifest_file.exists():
            try:
                manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            except Exception as e:
                manifest_data = {"error": f"Failed to parse plugin.json: {e}"}

        # Check for bundled skills
        bundled_skills_dir = plugin_root / "skills"
        bundled_skills = scan_skills_directory(bundled_skills_dir, scope=f"plugin:{item.name}")

        # Check for bundled rules
        bundled_rules = []
        rules_dir = plugin_root / "rules"
        if rules_dir.exists():
            for rf in rules_dir.glob("*.md"):
                try:
                    content = rf.read_text(encoding="utf-8", errors="replace")
                    bundled_rules.append({
                        "name": rf.name,
                        "path": str(rf),
                        "size_bytes": rf.stat().st_size,
                        "estimated_tokens": estimate_tokens(content)
                    })
                except OSError:
                    continue

        # Check for bundled hooks
        hooks_file = plugin_root / "hooks.json"
        bundled_hooks = None
        if hooks_file.exists():
            try:
                bundled_hooks = json.loads(hooks_file.read_text(encoding="utf-8"))
            except Exception as e:
                bundled_hooks = {"error": str(e)}

        # Check for bundled MCP
        mcp_file = plugin_root / "mcp_config.json"
        bundled_mcp = None
        if mcp_file.exists():
            try:
                bundled_mcp = json.loads(mcp_file.read_text(encoding="utf-8"))
            except Exception as e:
                bundled_mcp = {"error": str(e)}

        results.append({
            "name": manifest_data.get("name", item.name),
            "displayName": manifest_data.get("displayName", ""),
            "version": manifest_data.get("version", ""),
            "directory_name": item.name,
            "path": str(plugin_root),
            "is_symlink": item.is_symlink(),
            "manifest": manifest_data,
            "bundled_skills": bundled_skills,
            "bundled_rules": bundled_rules,
            "has_hooks": hooks_file.exists(),
            "hooks": bundled_hooks,
            "has_mcp": mcp_file.exists(),
            "mcp_config": bundled_mcp,
        })

    return results


def scan_mcp_environment(mcp_config_path: Path, mcp_schemas_dir: Path) -> dict[str, Any]:
    """Scan MCP servers declared in mcp_config.json and schemas cached in ~/.gemini/antigravity/mcp/."""
    config_servers = {}
    if mcp_config_path.exists():
        try:
            raw_cfg = json.loads(mcp_config_path.read_text(encoding="utf-8"))
            config_servers = raw_cfg.get("mcpServers", {})
        except Exception as e:
            config_servers = {"_error": str(e)}

    schemas_by_server = {}
    total_tools = 0
    total_schema_tokens = 0

    if mcp_schemas_dir.exists() and mcp_schemas_dir.is_dir():
        for server_dir in sorted(mcp_schemas_dir.iterdir()):
            if not server_dir.is_dir():
                continue
            server_name = server_dir.name
            tools = []
            instructions = None
            instr_file = server_dir / "instructions.md"
            if instr_file.exists():
                instructions = instr_file.read_text(encoding="utf-8", errors="replace")

            for tool_file in sorted(server_dir.glob("*.json")):
                try:
                    tool_data = json.loads(tool_file.read_text(encoding="utf-8"))
                    name = tool_data.get("name", tool_file.stem)
                    desc = tool_data.get("description", "")
                    params = tool_data.get("parameters", {})
                    raw_str = tool_file.read_text(encoding="utf-8")
                    t_tokens = estimate_tokens(raw_str)
                    total_tools += 1
                    total_schema_tokens += t_tokens

                    tools.append({
                        "name": name,
                        "description": desc,
                        "schema_file": str(tool_file),
                        "required_params": params.get("required", []),
                        "properties": list(params.get("properties", {}).keys()),
                        "estimated_schema_tokens": t_tokens
                    })
                except Exception as e:
                    tools.append({
                        "file": tool_file.name,
                        "error": str(e)
                    })

            schemas_by_server[server_name] = {
                "server_name": server_name,
                "tool_count": len(tools),
                "has_instructions": instructions is not None,
                "instructions_tokens": estimate_tokens(instructions) if instructions else 0,
                "tools": tools
            }

    return {
        "configured_servers": config_servers,
        "active_schemas": schemas_by_server,
        "total_active_tools": total_tools,
        "total_schema_tokens": total_schema_tokens
    }


def scan_hooks(hooks_config_path: Path) -> dict[str, Any]:
    """Scan hooks configured in hooks.json."""
    if not hooks_config_path.exists():
        return {"configured": False, "hooks": {}}

    try:
        data = json.loads(hooks_config_path.read_text(encoding="utf-8"))
        summary = {}
        for hook_name, hook_spec in data.items():
            summary[hook_name] = {
                "enabled": hook_spec.get("enabled", True),
                "events": [
                    evt for evt in ["PreToolUse", "PostToolUse", "PreInvocation", "PostInvocation", "Stop"]
                    if evt in hook_spec
                ],
                "details": hook_spec
            }
        return {"configured": True, "path": str(hooks_config_path), "hooks": summary}
    except Exception as e:
        return {"configured": True, "path": str(hooks_config_path), "error": str(e)}


def scan_rules(gemini_md_path: Path, config_rules_dir: Path) -> list[dict[str, Any]]:
    """Scan global and directory rule files."""
    rules = []
    
    # Global GEMINI.md
    if gemini_md_path.exists():
        content = gemini_md_path.read_text(encoding="utf-8", errors="replace")
        rules.append({
            "name": "Global GEMINI.md",
            "path": str(gemini_md_path),
            "scope": "global",
            "size_bytes": gemini_md_path.stat().st_size,
            "estimated_tokens": estimate_tokens(content),
            "is_empty": len(content.strip()) == 0
        })

    # ~/.gemini/config/rules/ if any
    if config_rules_dir.exists() and config_rules_dir.is_dir():
        for rf in config_rules_dir.glob("*.md"):
            content = rf.read_text(encoding="utf-8", errors="replace")
            rules.append({
                "name": rf.name,
                "path": str(rf),
                "scope": "global_rules_dir",
                "size_bytes": rf.stat().st_size,
                "estimated_tokens": estimate_tokens(content),
                "is_empty": len(content.strip()) == 0
            })

    return rules


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Inventory Antigravity customizations.")
    parser.add_argument("--output", "-o", default="data/customization_inventory.json",
                        help="Path to save output JSON (default: data/customization_inventory.json)")
    parser.add_argument("--print-summary", action="store_true", default=True,
                        help="Print a human-readable summary to stdout")
    args = parser.parse_args(argv)

    home = Path.home()
    gemini_dir = home / ".gemini"
    antigravity_dir = gemini_dir / "antigravity"
    config_dir = gemini_dir / "config"

    # Builtin skills
    builtin_skills_dir = antigravity_dir / "builtin" / "skills"
    builtin_skills = scan_skills_directory(builtin_skills_dir, scope="builtin")

    # Config skills
    config_skills_dir = config_dir / "skills"
    config_skills = scan_skills_directory(config_skills_dir, scope="global:config_skills")

    # Antigravity root skills
    agy_skills_dir = antigravity_dir / "skills"
    agy_skills = scan_skills_directory(agy_skills_dir, scope="global:antigravity_skills")

    # Deduplicate skills by resolved path
    all_skills_map = {}
    for s in builtin_skills + config_skills + agy_skills:
        p = s.get("path")
        if p and p not in all_skills_map:
            all_skills_map[p] = s

    # Plugins
    plugins_dir = config_dir / "plugins"
    plugins = scan_plugins(plugins_dir)

    # MCP Environment
    mcp_config_path = config_dir / "mcp_config.json"
    mcp_schemas_dir = antigravity_dir / "mcp"
    mcp_inventory = scan_mcp_environment(mcp_config_path, mcp_schemas_dir)

    # Lifecycle Hooks
    hooks_config_path = config_dir / "hooks.json"
    hooks_inventory = scan_hooks(hooks_config_path)

    # Rules
    gemini_md_path = gemini_dir / "GEMINI.md"
    config_rules_dir = config_dir / "rules"
    rules_inventory = scan_rules(gemini_md_path, config_rules_dir)

    # Summary calculations
    total_skills = len(all_skills_map)
    total_plugins = len(plugins)
    total_mcp_servers = len(mcp_inventory.get("active_schemas", {}))
    total_mcp_tools = mcp_inventory.get("total_active_tools", 0)
    total_mcp_tokens = mcp_inventory.get("total_schema_tokens", 0)
    total_skill_injection_tokens = sum(s.get("estimated_injection_tokens", 0) for s in all_skills_map.values())
    total_skill_full_tokens = sum(s.get("estimated_full_tokens", 0) for s in all_skills_map.values())

    report = {
        "timestamp": os.popen("date -Iseconds").read().strip(),
        "workstation": {
            "user": os.getenv("USER", "unknown"),
            "home": str(home),
            "antigravity_dir": str(antigravity_dir),
            "config_dir": str(config_dir),
        },
        "summary": {
            "total_skills": total_skills,
            "builtin_skills_count": len(builtin_skills),
            "custom_skills_count": len(config_skills),
            "total_plugins": total_plugins,
            "active_mcp_servers": total_mcp_servers,
            "declared_mcp_tools": total_mcp_tools,
            "total_mcp_schema_tokens": total_mcp_tokens,
            "total_skill_injection_tokens": total_skill_injection_tokens,
            "total_skill_full_tokens": total_skill_full_tokens,
            "hooks_active": hooks_inventory.get("configured", False) and len(hooks_inventory.get("hooks", {})) > 0,
        },
        "skills": {
            "builtin": builtin_skills,
            "config_skills": config_skills,
            "antigravity_skills": agy_skills,
            "unique_resolved": list(all_skills_map.values()),
        },
        "plugins": plugins,
        "mcp": mcp_inventory,
        "hooks": hooks_inventory,
        "rules": rules_inventory,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.print_summary:
        print("=" * 70)
        print(" 🛰️  PSL HARNESS: CUSTOMIZATION & EXTENSION INVENTORY")
        print("=" * 70)
        print(f"Total Unique Skills Cataloged:    {total_skills}")
        print(f"  - Built-in Skills:              {len(builtin_skills)}")
        print(f"  - Custom / Mesh Skills:         {len(config_skills)}")
        print(f"  - Progressive Injection Tokens: ~{total_skill_injection_tokens} tokens")
        print(f"  - Total Full Content Volume:    ~{total_skill_full_tokens} tokens")
        print("-" * 70)
        print(f"Plugins Installed:                {total_plugins}")
        for p in plugins:
            b_skills = len(p.get("bundled_skills", []))
            print(f"  • {p['name']} (v{p.get('version', 'N/A')}): {b_skills} bundled skills")
        print("-" * 70)
        print(f"MCP Servers Active:               {total_mcp_servers}")
        print(f"  - Total Declared Tools:         {total_mcp_tools}")
        print(f"  - Tool Schema Context Cost:     ~{total_mcp_tokens} tokens")
        for s_name, s_info in mcp_inventory.get("active_schemas", {}).items():
            print(f"  • {s_name}: {s_info['tool_count']} tools (~{sum(t.get('estimated_schema_tokens', 0) for t in s_info.get('tools', []))} tokens)")
        print("-" * 70)
        hooks_active = hooks_inventory.get("configured") and bool(hooks_inventory.get("hooks"))
        print(f"Lifecycle Hooks Configured:       {hooks_active}")
        if hooks_active:
            for h_name, h_val in hooks_inventory.get("hooks", {}).items():
                print(f"  • {h_name}: events={h_val.get('events')}")
        print("-" * 70)
        print(f"Active Rules:                     {len(rules_inventory)}")
        for r in rules_inventory:
            status = "EMPTY" if r.get("is_empty") else f"~{r.get('estimated_tokens')} tokens"
            print(f"  • {r['name']}: {status}")
        print("=" * 70)
        print(f"Inventory saved successfully -> {out_path}")
        print("=" * 70)


if __name__ == "__main__":
    main()
