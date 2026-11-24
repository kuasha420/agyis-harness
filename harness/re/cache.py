# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Deterministic Decompiler & RE Query Cache Engine (ADR-028, PSL-RE-001, PSL-INV-008, Issue #113).
Provides sub-millisecond query retrieval, locked atomic hit/miss metrics tracking,
bounded LRU eviction, and path-contained cache lifecycle governance across dirtyroom workspaces.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, Iterator, List, Optional, Tuple

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]

from harness.re.scaffold import get_dirtyroom_root

DEFAULT_MAX_CACHE_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_CACHE_ENTRIES = 5000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_size(num_bytes: int) -> str:
    val = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(val) < 1024.0 or unit == "GB":
            return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= 1024.0
    return f"{val:.1f} GB"


def _safe_stat_size(path: Path) -> int:
    try:
        if path.is_symlink() or not path.is_file():
            return 0
        return path.stat().st_size
    except OSError:
        return 0


def _validate_category_dir(cache_root: Path, category: str) -> Path:
    """Validates category name and guarantees resolved directory stays strictly within cache_root."""
    if not category or "/" in category or "\\" in category or category in (".", "..") or category.startswith("."):
        raise ValueError(f"Invalid cache category '{category}': must be a simple relative directory name")
    root_res = cache_root.resolve()
    cand = cache_root / category
    if cand.is_symlink():
        raise ValueError(f"Refusing symlinked cache category directory: {cand}")
    cand_res = cand.resolve()
    if not cand_res.is_relative_to(root_res) or cand_res == root_res:
        raise ValueError(f"Cache category '{category}' escapes cache root '{cache_root}'")
    return cand


@contextmanager
def _stats_lock(root: Optional[Path] = None) -> Iterator[None]:
    if fcntl is None:
        yield
        return
    cache_root = get_cache_root(root)
    cache_root.mkdir(parents=True, exist_ok=True)
    lock_file = cache_root / ".stats.json.lock"
    with open(lock_file, "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def get_cache_root(root: Optional[Path] = None) -> Path:
    """Returns the root cache directory within the active dirtyroom."""
    dr = root or get_dirtyroom_root()
    if dr:
        return dr / "cache"
    return Path.cwd() / ".dirtyroom" / "cache"


def get_cache_dir(root: Optional[Path] = None, category: str = "decompile") -> Path:
    """Returns a validated category cache directory strictly under .dirtyroom/cache/."""
    cache_root = get_cache_root(root)
    return _validate_category_dir(cache_root, category)


def compute_cache_key(binary_path: Optional[Path], binary_name: str, procedure: str) -> str:
    """Computes deterministic decompiler cache key matching cmd_decompile."""
    clean_proc = str(procedure).replace(":", "_").replace("/", "_").replace("\\", "_")
    bin_p = Path(binary_path) if binary_path else None
    bin_id = "00000000"
    if bin_p and bin_p.is_file():
        try:
            st = bin_p.stat()
            bin_id = hashlib.sha256(f"{st.st_size}_{st.st_mtime_ns}".encode()).hexdigest()[:8]
        except OSError:
            pass
    target_name = bin_p.name if bin_p else (Path(binary_name).name if binary_name else "target")
    return f"{target_name}_{bin_id}_{clean_proc}"


def get_stats_file(root: Optional[Path] = None) -> Path:
    """Returns the path to the atomic cache statistics JSON file."""
    return get_cache_root(root) / "stats.json"


def read_cache_stats(root: Optional[Path] = None) -> Dict[str, Any]:
    """Reads latest cache metrics JSON, returning empty defaults if unavailable."""
    path = get_stats_file(root)
    if path.is_symlink() or not path.is_file():
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
    if path.is_symlink():
        return
    tmp_name: Optional[str] = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".stats.",
            suffix=".tmp",
            delete=False,
        ) as tmp_f:
            tmp_name = tmp_f.name
            json.dump(stats, tmp_f, indent=2)
            tmp_f.write("\n")
        os.replace(tmp_name, path)
    except OSError as exc:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)
        sys.stderr.write(f"[!] Warning: Could not write cache stats {path}: {exc}\n")


def record_cache_hit(root: Optional[Path] = None, category: str = "decompile", key: Optional[str] = None) -> None:
    """Records a cache hit atomically in stats.json under an exclusive file lock."""
    with _stats_lock(root):
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
    """Records a cache miss atomically in stats.json under an exclusive file lock."""
    with _stats_lock(root):
        stats = read_cache_stats(root)
        stats["misses"] = stats.get("misses", 0) + 1
        stats["last_miss"] = _utc_now_iso()
        cats = stats.setdefault("categories", {})
        cat_entry = cats.setdefault(category, {"hits": 0, "misses": 0})
        cat_entry["misses"] = cat_entry.get("misses", 0) + 1
        if key:
            cat_entry["last_key"] = key
        _write_cache_stats(stats, root)


def enforce_cache_limits(
    root: Optional[Path] = None,
    max_bytes: int = DEFAULT_MAX_CACHE_BYTES,
    max_entries: int = DEFAULT_MAX_CACHE_ENTRIES,
) -> Dict[str, Any]:
    """Enforces bounded LRU capacity on .dirtyroom/cache/ (PSL-INV-008 §4)."""
    cache_root = get_cache_root(root)
    if not cache_root.is_dir() or cache_root.is_symlink():
        return {"evicted_count": 0, "reclaimed_bytes": 0}

    root_res = cache_root.resolve()
    entries: List[Tuple[float, int, Path]] = []
    total_bytes = 0
    for p in cache_root.rglob("*"):
        if p.name == "stats.json" or p.name.startswith(".") or p.is_symlink():
            continue
        try:
            if not p.is_file() or not p.resolve().is_relative_to(root_res):
                continue
            st = p.stat()
            entries.append((st.st_mtime, st.st_size, p))
            total_bytes += st.st_size
        except OSError:
            continue

    if len(entries) <= max_entries and total_bytes <= max_bytes:
        return {"evicted_count": 0, "reclaimed_bytes": 0}

    # Evict oldest mtime entries first (LRU)
    entries.sort(key=lambda item: item[0])
    evicted = 0
    reclaimed = 0
    remaining_count = len(entries)
    for _, sz, path in entries:
        if remaining_count <= max_entries and total_bytes <= max_bytes:
            break
        try:
            path.unlink(missing_ok=True)
            evicted += 1
            reclaimed += sz
            total_bytes -= sz
            remaining_count -= 1
        except OSError:
            continue

    return {"evicted_count": evicted, "reclaimed_bytes": reclaimed}


def get_cache_stats(root: Optional[Path] = None) -> Dict[str, Any]:
    """Inspects cache directory entries, disk usage, and hit rates."""
    cache_root = get_cache_root(root)
    stats = read_cache_stats(root)

    total_entries = 0
    total_bytes = 0
    breakdown: Dict[str, Dict[str, Any]] = {}

    if cache_root.is_dir() and not cache_root.is_symlink():
        for item in sorted(cache_root.iterdir()):
            if item.name == "stats.json" or item.name.startswith(".") or item.is_symlink():
                continue
            if item.is_dir():
                cat_name = item.name
                cat_files = [
                    p for p in item.rglob("*")
                    if not p.is_symlink() and p.is_file() and not p.name.startswith(".")
                ]
                cat_bytes = sum(_safe_stat_size(p) for p in cat_files)
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
                sz = _safe_stat_size(item)
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
        "max_bytes": DEFAULT_MAX_CACHE_BYTES,
        "max_entries": DEFAULT_MAX_CACHE_ENTRIES,
        "hits": hits,
        "misses": misses,
        "total_queries": total_queries,
        "hit_rate_pct": round(hit_rate, 2),
        "last_hit": stats.get("last_hit"),
        "last_miss": stats.get("last_miss"),
        "categories": breakdown,
    }


def clear_cache(root: Optional[Path] = None, category: str = "all", dry_run: bool = False) -> Dict[str, Any]:
    """Purges cached query artifacts within cache_root and optionally resets metrics."""
    cache_root = get_cache_root(root)
    if not cache_root.is_dir() or cache_root.is_symlink():
        return {
            "success": True,
            "dry_run": dry_run,
            "category": category,
            "deleted_count": 0,
            "reclaimed_bytes": 0,
            "reclaimed_human": "0 B",
            "cleared_files": [],
        }

    root_res = cache_root.resolve()
    files_to_delete: List[Path] = []
    if category in ("all", "*"):
        for p in cache_root.rglob("*"):
            if p.is_symlink() or p.name == "stats.json" or p.name.startswith("."):
                continue
            try:
                if p.is_file() and p.resolve().is_relative_to(root_res):
                    files_to_delete.append(p)
            except OSError:
                continue
    else:
        try:
            cat_dir = _validate_category_dir(cache_root, category)
        except ValueError as exc:
            return {
                "success": False,
                "dry_run": dry_run,
                "category": category,
                "deleted_count": 0,
                "reclaimed_bytes": 0,
                "reclaimed_human": "0 B",
                "cleared_files": [],
                "error": str(exc),
            }
        if cat_dir.is_dir():
            for p in cat_dir.rglob("*"):
                if p.is_symlink() or p.name.startswith("."):
                    continue
                try:
                    if p.is_file() and p.resolve().is_relative_to(root_res):
                        files_to_delete.append(p)
                except OSError:
                    continue

    reclaimed_bytes = sum(_safe_stat_size(p) for p in files_to_delete)

    if not dry_run:
        for p in files_to_delete:
            try:
                if not p.is_symlink() and p.resolve().is_relative_to(root_res):
                    p.unlink(missing_ok=True)
            except OSError:
                pass
        with _stats_lock(root):
            if category in ("all", "*"):
                stats_p = get_stats_file(root)
                try:
                    if not stats_p.is_symlink():
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
        print(" ⚡ Agyis Decompiler Query Cache Status (PSL-RE-001, Issue #113)")
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
            return 0 if res.get("success") else 1

        if not res.get("success"):
            print(f"[!] Error clearing cache: {res.get('error')}", file=sys.stderr)
            return 1

        prefix = "[DRY-RUN] Would clear" if dry_run else "[+] Purged"
        print(f"{prefix} {res['deleted_count']} cache file(s) ({res['reclaimed_human']}) for category '{cat}'.")
        return 0

    print(f"[!] Unknown cache action '{action}'. Use 'status' or 'clear'.", file=sys.stderr)
    return 1
