#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
MCP Tool Schema Discovery & Argument Normalization (Task 1.2A.1).

Handles multi-server MCP schema resolution across Antigravity / Agyis / Gemini
appDataDir overrides, longest-prefix server matching for direct `mcp_<srv>_<tool>`
names (such as `mcp_google_workspace_*`), argument alias normalization, and
PSL-RE-001 >10MB pre-analyzed Ghidra cache enforcement.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from harness.utils.context import get_app_data_dir_candidates

REA_PROCEDURE_TOOLS: frozenset[str] = frozenset({
    "procedure_pseudo_code",
    "procedure_assembly",
    "procedure_callers",
    "procedure_callees",
    "procedure_info",
})
REA_SEARCH_TOOLS: frozenset[str] = frozenset({"search_strings", "search_procedures"})
REA_BYTE_TOOLS: frozenset[str] = frozenset({"read_bytes"})
REA_INSPECTION_TOOLS: frozenset[str] = frozenset({
    "inspect_native_instruction",
    "goto_address",
    "address_name",
    "address_to_file_offset",
})
FILE_PATH_TOOLS: frozenset[str] = frozenset({"open_binary", "binary_overview"})


def _get_mcp_schema_dirs() -> List[Path]:
    """Build ordered, deduplicated list of MCP schema directories from env and candidates."""
    raw_dirs: List[Path] = []
    explicit_schemas = os.environ.get("AGYIS_MCP_SCHEMAS_DIR", "").strip()
    if explicit_schemas:
        raw_dirs.append(Path(explicit_schemas))
    for env_key in ("ANTIGRAVITY_APP_DATA_DIR", "AGYIS_APP_DATA_DIR", "GEMINI_APP_DATA_DIR"):
        env_val = os.environ.get(env_key, "").strip()
        if env_val:
            raw_dirs.append(Path(env_val) / "mcp")
    for cand in get_app_data_dir_candidates():
        raw_dirs.append(cand / "mcp")
    raw_dirs.append(Path.home() / ".gemini" / "antigravity" / "mcp")

    seen: set[str] = set()
    unique_dirs: List[Path] = []
    for d in raw_dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            unique_dirs.append(d)
    return unique_dirs


def _discover_known_mcp_servers() -> List[str]:
    """
    Discover known MCP server names from `mcp/` subdirectories and `mcp_config.json`,
    sorted longest-first by normalized identifier length for unambiguous prefix matching.
    """
    servers: set[str] = set()
    schema_dirs = _get_mcp_schema_dirs()
    checked_configs: set[str] = set()

    for schema_dir in schema_dirs:
        if schema_dir.is_dir():
            try:
                for entry in schema_dir.iterdir():
                    if entry.is_dir() and not entry.name.startswith("."):
                        servers.add(entry.name)
            except OSError:
                pass
        config_path = schema_dir.parent / "mcp_config.json"
        cfg_key = str(config_path)
        if cfg_key not in checked_configs and config_path.is_file():
            checked_configs.add(cfg_key)
            try:
                cfg_data = json.loads(config_path.read_text(encoding="utf-8"))
                mcp_servers = cfg_data.get("mcpServers") if isinstance(cfg_data, dict) else None
                if isinstance(mcp_servers, dict):
                    for srv_name in mcp_servers:
                        s = str(srv_name).strip()
                        if s:
                            servers.add(s)
            except (OSError, json.JSONDecodeError, ValueError):
                pass

    return sorted(
        servers,
        key=lambda s: (len(s.replace("-", "_")), len(s), s),
        reverse=True,
    )


def _split_direct_mcp_name(rest: str) -> Tuple[str, str]:
    """Split `<server>_<tool>` after `mcp_` using longest-first known server prefixes."""
    rest_norm = rest.replace("-", "_").lower()
    for srv in _discover_known_mcp_servers():
        norm_prefix = srv.replace("-", "_").lower() + "_"
        if rest_norm.startswith(norm_prefix) and len(rest) > len(norm_prefix):
            return srv, rest[len(norm_prefix):]
    return rest.split("_", 1)


def load_mcp_tool_schema(server_name: str, tool_name: str) -> Optional[Dict[str, Any]]:
    """Load tool JSON schema from configured Antigravity/Agyis/Gemini MCP schema directories."""
    if not server_name or not tool_name:
        return None
    srv_variants: List[str] = []
    for cand_srv in (
        server_name,
        server_name.lower(),
        server_name.replace("-", "_"),
        server_name.replace("-", "_").lower(),
        server_name.replace("_", "-"),
        server_name.replace("_", "-").lower(),
    ):
        if cand_srv not in srv_variants:
            srv_variants.append(cand_srv)

    for base in _get_mcp_schema_dirs():
        for srv_dir in srv_variants:
            cand = base / srv_dir / f"{tool_name}.json"
            try:
                if cand.is_file():
                    return json.loads(cand.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                sys.stderr.write(f"PSL Command Safety Warning: Failed to load MCP schema '{cand}': {exc}\n")
                continue
    return None


def get_schema_properties(schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract property dictionary from tool JSON schema."""
    if not isinstance(schema, dict):
        return {}
    if isinstance(schema.get("properties"), dict):
        return schema["properties"]
    params = schema.get("parameters")
    return params["properties"] if isinstance(params, dict) and isinstance(params.get("properties"), dict) else {}


def _check_rea_ghidra_cache(modified_args: Dict[str, Any]) -> Optional[str]:
    """Enforce PSL-RE-001 >10MB pre-analyzed Ghidra project cache check for REA tools."""
    target_path_str = modified_args.get("path") or modified_args.get("binary_path") or modified_args.get("binary")
    if not target_path_str:
        return None
    try:
        target_p = Path(target_path_str)
        if not (target_p.is_file() and (target_p.stat().st_size / (1024 * 1024)) > 10.0):
            return None
        from harness.re.scaffold import get_dirtyroom_db, get_dirtyroom_root

        dr = get_dirtyroom_root(target_p.parent) or get_dirtyroom_root(Path(os.getcwd()))
        has_gpr = bool(dr and (dr / "ghidra").is_dir() and list((dr / "ghidra").glob("*.gpr")))
        if not has_gpr and dr:
            conn = None
            try:
                conn = get_dirtyroom_db(dr)
                if conn:
                    cur = conn.cursor()
                    cur.execute("SELECT 1 FROM binaries WHERE name = ? LIMIT 1", (target_p.name,))
                    if cur.fetchone():
                        has_gpr = True
            except Exception as exc:
                sys.stderr.write(f"PSL Command Safety Warning: Failed querying dirtyroom DB for '{target_p.name}': {exc}\n")
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
        env_gpr = os.environ.get("REA_GHIDRA_PROJECT_DIR")
        if not has_gpr and env_gpr and Path(env_gpr).is_dir():
            has_gpr = any(Path(env_gpr).glob("*.gpr"))
        if not has_gpr:
            size_mb = target_p.stat().st_size / (1024 * 1024)
            return (
                f"[PSL-RE-001 VIOLATION] Target binary '{target_p.name}' is {size_mb:.1f} MB (>10 MB) "
                "without a pre-analyzed Ghidra project cache. Ad-hoc decompiler analysis will exceed 180s timeout. "
                f"Run 'agyis re pre-analyze {target_p.name}' or set REA_GHIDRA_PROJECT_DIR first."
            )
    except Exception as exc:
        sys.stderr.write(f"PSL Command Safety Warning: Error checking REA Ghidra cache: {exc}\n")
    return None


def normalize_mcp_tool_call(tool_name: str, tool_args: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
    """Normalize MCP tool arguments and enforce PSL-RE-001 >10MB Ghidra cache checks."""
    is_direct_mcp = tool_name.startswith("mcp_") and "_" in tool_name[4:]
    if tool_name != "call_mcp_tool" and not is_direct_mcp:
        return ("allow", None, None)
    if not isinstance(tool_args, dict):
        return ("allow", None, None)

    if is_direct_mcp:
        server_name, subtool = _split_direct_mcp_name(tool_name[4:])
        raw_arguments = tool_args
        args_key = None
    else:
        server_name = str(tool_args.get("ServerName") or tool_args.get("server_name") or tool_args.get("server") or "").strip()
        subtool = str(tool_args.get("ToolName") or tool_args.get("tool_name") or tool_args.get("tool") or "").strip()
        args_key = "Arguments" if "Arguments" in tool_args else ("arguments" if "arguments" in tool_args else "Arguments")
        raw_arguments = tool_args.get(args_key)
        if not isinstance(raw_arguments, dict):
            return ("allow", None, None)

    modified_args, reasons = dict(raw_arguments), []
    canonical_props = set(get_schema_properties(load_mcp_tool_schema(server_name, subtool)).keys())
    srv_lower = server_name.lower()

    alias_map: Dict[str, str] = {}
    for active, target_k, aliases in (
        (subtool in REA_PROCEDURE_TOOLS or (srv_lower == "rea" and "procedure" in canonical_props), "procedure", ("Address", "address", "addr", "procedure_name", "target", "proc")),
        (subtool in REA_SEARCH_TOOLS, "pattern", ("query", "search", "text", "pattern_str", "Query")),
        (subtool in REA_BYTE_TOOLS, "length", ("Length", "size", "count", "bytes", "len")),
        (subtool in REA_BYTE_TOOLS or subtool in REA_INSPECTION_TOOLS, "address", ("Address", "addr")),
        (srv_lower == "context7" or subtool in ("query-docs", "resolve-library-id") or "libraryId" in canonical_props, "libraryId", ("library_id", "LibraryId", "libraryID", "lib_id")),
        (subtool in FILE_PATH_TOOLS or srv_lower == "rea" or "path" in canonical_props, "path", ("file_path", "filePath", "binary_path")),
        (subtool in FILE_PATH_TOOLS, "path", ("binary",)),
    ):
        if active:
            alias_map.update({k: target_k for k in aliases})
    if srv_lower == "rea":
        alias_map.setdefault("Address", "procedure" if subtool in ("procedure_assembly", "procedure_pseudo_code") else "address")
        alias_map.setdefault("Length", "length")
        if subtool in REA_SEARCH_TOOLS:
            alias_map.setdefault("query", "pattern")

    for old_k in list(modified_args.keys()):
        if canonical_props and old_k in canonical_props:
            continue
        target_k = alias_map.get(old_k)
        if target_k is None and canonical_props:
            target_k = next((p for p in canonical_props if old_k.lower() == p.lower()), None)
            if target_k is None:
                norm_old = re.sub(r"[_\-]", "", old_k).lower()
                target_k = next((p for p in canonical_props if norm_old == re.sub(r"[_\-]", "", p).lower()), None)
        elif target_k is None and not canonical_props:
            if srv_lower == "context7" and "_" in old_k:
                parts = old_k.split("_")
                target_k = parts[0].lower() + "".join(p.capitalize() for p in parts[1:])
            elif old_k in ("Address", "Length", "Pattern", "Query"):
                target_k = old_k.lower()

        if target_k and target_k != old_k:
            if target_k in modified_args:
                modified_args.pop(old_k, None)
                reasons.append(f"removed redundant alias '{old_k}' in favor of '{target_k}'")
            else:
                modified_args[target_k] = modified_args.pop(old_k)
                reasons.append(f"normalized argument '{old_k}' -> '{target_k}'")

    if srv_lower == "rea":
        deny_reason = _check_rea_ghidra_cache(modified_args)
        if deny_reason:
            return ("deny", None, deny_reason)

    if reasons:
        if is_direct_mcp:
            return ("allow", modified_args, "; ".join(reasons))
        return ("allow", {**tool_args, args_key: modified_args}, "; ".join(reasons))
    return ("allow", None, None)


normalize_rea_mcp_tool_call = normalize_mcp_tool_call
