# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Global user-space dirtyroom registry for multi-workspace REA MCP auto-discovery."""

from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from typing import Any, Dict, Iterator, List, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]

MAX_REGISTRY_ENTRIES = 64
MAX_BINARIES_PER_DIRTYROOM = 256
_REGISTRY_VERSION = 1
_HEX_CHARS = frozenset("0123456789abcdef")


def _has_dot_component(path: Path) -> bool:
    return any(part.startswith(".") and part not in (".", "..") for part in path.parts)


def _safe_float(val: Any) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


@contextmanager
def _registry_lock(reg_path: Path) -> Iterator[None]:
    if fcntl is None:
        yield
        return
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(reg_path.parent / f".{reg_path.name}.lock", "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def get_registry_path(registry_path: Optional[Path] = None) -> Path:
    """Resolves the active dirtyroom registry file path with hermetic env overrides."""
    if registry_path is not None:
        return Path(registry_path)
    if env_reg := os.environ.get("AGYIS_DIRTYROOM_REGISTRY"):
        return Path(env_reg)
    if state_dir := (os.environ.get("AGYIS_HARNESS_STATE_DIR") or os.environ.get("PSL_HARNESS_STATE_DIR")):
        return Path(state_dir) / "agyis_dirtyrooms.json"
    return Path.home() / ".gemini" / "config" / "agyis_dirtyrooms.json"


def resolve_nondot_ghidra_dir(dirtyroom_root: Path) -> Optional[Path]:
    """Resolves an absolute non-dot Ghidra project directory for DEF-BB-038 compliance."""
    raw_root = Path(os.path.abspath(dirtyroom_root))
    ghidra_raw = raw_root / "ghidra"
    if not ghidra_raw.is_dir():
        return None
    try:
        resolved_ghidra = ghidra_raw.resolve()
    except OSError:
        return None
    alias_root = raw_root.parent / raw_root.name.lstrip(".") if raw_root.name.startswith(".") and raw_root.name.lstrip(".") else None

    def _valid_alias() -> Optional[Path]:
        cand = (alias_root / "ghidra") if alias_root is not None else None
        try:
            return cand if cand and cand.is_dir() and cand.resolve() == resolved_ghidra and not _has_dot_component(cand) else None
        except OSError:
            return None

    for candidate in (_valid_alias(), ghidra_raw, resolved_ghidra):
        if candidate is not None and not _has_dot_component(candidate):
            return candidate
    if alias_root is not None and not alias_root.exists() and not alias_root.is_symlink() and any(p.is_file() for p in ghidra_raw.glob("*.gpr")):
        try:
            alias_root.symlink_to(raw_root.name, target_is_directory=True)
        except OSError:
            return None
        return _valid_alias()
    return None


def _read_registered_binaries(dirtyroom_root: Path) -> Dict[str, str]:
    """Reads registered {sha256[:12].lower(): name} mappings from dirtyroom SQLite DBs."""
    sym_dir = dirtyroom_root / "symbols"
    raw_cands: List[Path] = [sym_dir / "dirtyroom.db"]
    if sym_dir.is_dir():
        try:
            raw_cands.extend(sorted(sym_dir.glob("*.db")) + sorted(sym_dir.glob("*.sqlite")))
        except OSError:
            pass
    raw_cands.extend([dirtyroom_root / "symbols.db", dirtyroom_root / "symbols.sqlite"])
    binaries: Dict[str, str] = {}
    seen: set[Path] = set()
    for cand in raw_cands:
        if len(seen) >= 16 or len(binaries) >= MAX_BINARIES_PER_DIRTYROOM:
            break
        try:
            if not cand.is_file() or cand.stat().st_size <= 0 or (rp := cand.resolve()) in seen:
                continue
            seen.add(rp)
            with closing(sqlite3.connect(f"{rp.as_uri()}?mode=ro", uri=True)) as conn:
                for name, sha256 in conn.execute("SELECT name, sha256 FROM binaries").fetchall():
                    if len(binaries) >= MAX_BINARIES_PER_DIRTYROOM:
                        break
                    if isinstance(name, str) and name.strip() and isinstance(sha256, str):
                        prefix = sha256.strip()[:12].lower()
                        if len(prefix) == 12 and prefix != "000000000000" and _HEX_CHARS.issuperset(prefix):
                            binaries.setdefault(prefix, name.strip())
        except (sqlite3.Error, OSError, ValueError):
            continue
    return binaries


def load_dirtyroom_registry(registry_path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads the dirtyroom registry JSON safely, returning an empty skeleton on error."""
    reg_path = get_registry_path(registry_path)
    empty: Dict[str, Any] = {"version": _REGISTRY_VERSION, "updated_at": None, "dirtyrooms": {}}
    if not reg_path.is_file():
        return empty
    try:
        raw = json.loads(reg_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("dirtyrooms"), dict):
            return {"version": int(raw.get("version", _REGISTRY_VERSION)), "updated_at": raw.get("updated_at"), "dirtyrooms": dict(raw["dirtyrooms"])}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    return empty


def _atomic_write_json(target: Path, payload: Dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, prefix=".agyis_dirtyrooms.", suffix=".tmp", delete=False) as tmp_f:
            tmp_name = tmp_f.name
            json.dump(payload, tmp_f, indent=2)
            tmp_f.write("\n")
        os.replace(tmp_name, target)
    except OSError:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)
        raise


def register_dirtyroom(dirtyroom_root: Path, registry_path: Optional[Path] = None) -> Dict[str, Any]:
    """Atomically upserts a dirtyroom entry into the user-space registry (bounded to 64)."""
    raw_root = Path(os.path.abspath(dirtyroom_root))
    ghidra_dir = resolve_nondot_ghidra_dir(raw_root)
    if ghidra_dir is None:
        return {"registered": False, "reason": "no_nondot_ghidra_dir", "dirtyroom_root": str(raw_root)}
    projects = sorted(p.stem for p in ghidra_dir.glob("*.gpr") if p.is_file())
    binaries = _read_registered_binaries(raw_root)
    now_iso, now_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), time.time()
    reg_path = get_registry_path(registry_path)
    try:
        target_resolved = ghidra_dir.resolve()
    except OSError:
        target_resolved = ghidra_dir

    with _registry_lock(reg_path):
        pruned: Dict[str, Dict[str, Any]] = {}
        for key, entry in load_dirtyroom_registry(reg_path).get("dirtyrooms", {}).items():
            entry_raw = entry.get("ghidra_dir") or key if isinstance(entry, dict) else ""
            if isinstance(entry_raw, str) and entry_raw:
                entry_dir = Path(entry_raw)
                try:
                    if entry_dir.is_absolute() and entry_dir.is_dir() and entry_dir.resolve() != target_resolved:
                        pruned[str(entry_dir)] = entry
                except OSError:
                    continue
        key_str = str(ghidra_dir)
        pruned[key_str] = {
            "ghidra_dir": key_str, "dirtyroom_root": str(raw_root), "workspace": str(raw_root.parent),
            "projects": projects, "binaries": binaries, "updated_at": now_iso, "last_seen": now_ts,
        }
        if len(pruned) > MAX_REGISTRY_ENTRIES:
            pruned = dict(sorted(pruned.items(), key=lambda kv: _safe_float(kv[1].get("last_seen")), reverse=True)[:MAX_REGISTRY_ENTRIES])
        _atomic_write_json(reg_path, {"version": _REGISTRY_VERSION, "updated_at": now_iso, "dirtyrooms": pruned})

    return {"registered": True, "registry_path": str(reg_path), "ghidra_dir": key_str, "projects": projects, "binaries": binaries, "entry_count": len(pruned)}
