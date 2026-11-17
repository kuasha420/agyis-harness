# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Deterministic Decompiler & RE Query Cache Engine (ADR-028, PSL-INV-009, Issue #113).
Provides sub-millisecond query retrieval, atomic hit/miss metrics tracking,
and cache lifecycle governance across dirtyroom workspaces.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from harness.re.scaffold import get_dirtyroom_root


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024.0 or unit == "GB":
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{num_bytes} B"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} GB"


def get_cache_root(root: Optional[Path] = None) -> Path:
    """Returns the root cache directory within the active dirtyroom."""
    dr = root or get_dirtyroom_root()
    if dr:
        return dr / "cache"
    return Path.cwd() / ".dirtyroom" / "cache"


def get_cache_dir(root: Optional[Path] = None, category: str = "decompile") -> Path:
    """Returns a specific category cache directory under .dirtyroom/cache/."""
    cache_root = get_cache_root(root)
    return cache_root / category


def get_stats_file(root: Optional[Path] = None) -> Path:
    """Returns the path to the atomic cache statistics JSON file."""
    return get_cache_root(root) / "stats.json"


def read_cache_stats(root: Optional[Path] = None) -> Dict[str, Any]:
    """Reads latest cache metrics JSON, returning empty defaults if unavailable."""
    path = get_stats_file(root)
    if not path.is_file():
        return {"hits": 0, "misses": 0, "last_hit": None, "last_miss": None, "categories": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"hits": 0, "misses": 0, "last_hit": None, "last_miss": None, "categories": {}}


def _write_cache_stats(stats: Dict[str, Any], root: Optional[Path] = None) -> None:
    path = get_stats_file(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def record_cache_hit(root: Optional[Path] = None, category: str = "decompile", key: Optional[str] = None) -> None:
    """Records a cache hit atomically in stats.json."""
    stats = read_cache_stats(root)
    stats["hits"] = stats.get("hits", 0) + 1
    stats["last_hit"] = _utc_now_iso()
    cats = stats.setdefault("categories", {})
    cat_entry = cats.setdefault(category, {"hits": 0, "misses": 0})
    cat_entry["hits"] = cat_entry.get("hits", 0) + 1
    if key:
        cat_entry["last_key"] = key
    _write_cache_stats(stats, root)


def record_cache_miss(root: Optional[Path] = None, category: str = "decompile", key: Optional[str] = None) -> None:
    """Records a cache miss atomically in stats.json."""
    stats = read_cache_stats(root)
    stats["misses"] = stats.get("misses", 0) + 1
    stats["last_miss"] = _utc_now_iso()
    cats = stats.setdefault("categories", {})
    cat_entry = cats.setdefault(category, {"hits": 0, "misses": 0})
    cat_entry["misses"] = cat_entry.get("misses", 0) + 1
    if key:
        cat_entry["last_key"] = key
    _write_cache_stats(stats, root)


def get_cache_stats(root: Optional[Path] = None) -> Dict[str, Any]:
    """Inspects cache directory entries, disk usage, and hit rates."""
    cache_root = get_cache_root(root)
    stats = read_cache_stats(root)

    total_entries = 0
    total_bytes = 0
    breakdown: Dict[str, Dict[str, Any]] = {}

    if cache_root.is_dir():
        for item in sorted(cache_root.iterdir()):
            if item.name == "stats.json" or item.name.startswith("."):
                continue
            if item.is_dir():
                cat_name = item.name
                cat_files = [p for p in item.rglob("*") if p.is_file() and not p.name.startswith(".")]
                cat_bytes = sum(p.stat().st_size for p in cat_files)
                total_entries += len(cat_files)
                total_bytes += cat_bytes
                cat_stats = stats.get("categories", {}).get(cat_name, {})
                breakdown[cat_name] = {
                    "entries": len(cat_files),
                    "bytes": cat_bytes,
                    "human_size": _format_size(cat_bytes),
                    "hits": cat_stats.get("hits", 0),
                    "misses": cat_stats.get("misses", 0),
                }
            elif item.is_file():
                sz = item.stat().st_size
                total_entries += 1
                total_bytes += sz

    hits = stats.get("hits", 0)
    misses = stats.get("misses", 0)
    total_queries = hits + misses
    hit_rate = (hits / total_queries * 100.0) if total_queries > 0 else 0.0

    return {
        "status": "active" if cache_root.is_dir() else "uninitialized",
        "cache_root": str(cache_root),
        "entries": total_entries,
        "total_bytes": total_bytes,
        "total_human": _format_size(total_bytes),
        "hits": hits,
        "misses": misses,
        "total_queries": total_queries,
        "hit_rate_pct": round(hit_rate, 2),
        "last_hit": stats.get("last_hit"),
        "last_miss": stats.get("last_miss"),
        "categories": breakdown,
    }


def clear_cache(root: Optional[Path] = None, category: str = "all", dry_run: bool = False) -> Dict[str, Any]:
    """Purges cached query artifacts and optionally resets metrics."""
    cache_root = get_cache_root(root)
    if not cache_root.is_dir():
        return {
            "success": True,
            "dry_run": dry_run,
            "category": category,
            "deleted_count": 0,
            "reclaimed_bytes": 0,
            "reclaimed_human": "0 B",
            "cleared_files": [],
        }

    files_to_delete: List[Path] = []
    if category in ("all", "*"):
        for p in cache_root.rglob("*"):
            if p.is_file() and p.name != "stats.json" and not p.name.startswith("."):
                files_to_delete.append(p)
    else:
        cat_dir = cache_root / category
        if cat_dir.is_dir():
            for p in cat_dir.rglob("*"):
                if p.is_file() and not p.name.startswith("."):
                    files_to_delete.append(p)

    reclaimed_bytes = sum(p.stat().st_size for p in files_to_delete if p.is_file())

    if not dry_run:
        for p in files_to_delete:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        # Reset or update stats if purging all
        if category in ("all", "*"):
            stats_p = get_stats_file(root)
            try:
                stats_p.unlink(missing_ok=True)
            except OSError:
                pass
        else:
            stats = read_cache_stats(root)
            if "categories" in stats and category in stats["categories"]:
                stats["categories"][category] = {"hits": 0, "misses": 0}
                _write_cache_stats(stats, root)

    return {
        "success": True,
        "dry_run": dry_run,
        "category": category,
        "deleted_count": len(files_to_delete),
        "reclaimed_bytes": reclaimed_bytes,
        "reclaimed_human": _format_size(reclaimed_bytes),
        "cleared_files": [str(p) for p in files_to_delete],
    }


def cmd_cache(args: argparse.Namespace) -> int:
    """CLI dispatcher for 'agyis re cache [status|clear]'."""
    action = getattr(args, "cache_action", "status") or "status"

    if action == "status":
        stats = get_cache_stats()
        if getattr(args, "json", False):
            print(json.dumps(stats, indent=2))
            return 0

        print("======================================================================")
        print(" ⚡ Agyis Decompiler Query Cache Status (PSL-INV-009, Issue #113)")
        print("======================================================================")
        print(f" Cache Directory:  {stats['cache_root']}")
        print(f" Status:           {stats['status'].upper()}")
        print(f" Total Entries:    {stats['entries']:,}")
        print(f" Disk Usage:       {stats['total_human']}")
        print(f" Cache Hits:       {stats['hits']:,}")
        print(f" Cache Misses:     {stats['misses']:,}")
        print(f" Query Hit Rate:   {stats['hit_rate_pct']:.2f}%")
        if stats.get("last_hit"):
            print(f" Last Cache Hit:   {stats['last_hit']}")
        if stats.get("last_miss"):
            print(f" Last Cache Miss:  {stats['last_miss']}")

        if stats.get("categories"):
            print("----------------------------------------------------------------------")
            print(" Category Breakdown:")
            for cat, data in stats["categories"].items():
                print(f"   • {cat:<14} {data['entries']:>5} files | {data['human_size']:>10} | {data['hits']} hits / {data['misses']} misses")
        print("======================================================================")
        return 0

    if action == "clear":
        cat = getattr(args, "type", "all") or "all"
        dry_run = getattr(args, "dry_run", False)
        res = clear_cache(category=cat, dry_run=dry_run)
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
            return 0

        prefix = "[DRY-RUN] Would clear" if dry_run else "[+] Purged"
        print(f"{prefix} {res['deleted_count']} cache file(s) ({res['reclaimed_human']}) for category '{cat}'.")
        return 0

    print(f"[!] Unknown cache action '{action}'. Use 'status' or 'clear'.", file=sys.stderr)
    return 1
