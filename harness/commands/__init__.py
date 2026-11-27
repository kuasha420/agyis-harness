# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis CLI command modules (ADR-014).
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, List, Tuple

_COMMAND_MAP: Dict[str, Tuple[str, str]] = {
    "cmd_doctor": ("harness.commands.doctor", "cmd_doctor"),
    "cmd_hook": ("harness.commands.hook", "cmd_hook"),
    "cmd_test": ("harness.commands.test", "cmd_test"),
    "cmd_audit": ("harness.commands.audit", "cmd_audit"),
    "cmd_auth": ("harness.commands.auth", "cmd_auth"),
    "cmd_sync": ("harness.commands.sync", "cmd_sync"),
    "cmd_skills": ("harness.commands.skills", "cmd_skills"),
    "cmd_rules": ("harness.commands.rules", "cmd_rules"),
    "cmd_agents": ("harness.commands.agents", "cmd_agents"),
    "cmd_subagents": ("harness.commands.subagents", "cmd_subagents"),
    "cmd_remote": ("harness.commands.remote", "cmd_remote"),
    "cmd_status": ("harness.commands.status", "cmd_status"),
    "cmd_init": ("harness.commands.install", "cmd_init"),
    "cmd_install": ("harness.commands.install", "cmd_install"),
    "cmd_uninstall": ("harness.commands.install", "cmd_uninstall"),
    "cmd_harmonize": ("harness.commands.harmonize", "cmd_harmonize"),
    "cmd_onboard": ("harness.commands.onboard", "cmd_onboard"),
    "cmd_verify": ("harness.commands.verify", "cmd_verify"),
    "cmd_gui": ("harness.commands.gui", "cmd_gui"),
    "cmd_release": ("harness.commands.release", "cmd_release"),
    "cmd_release_notes": ("harness.commands.release_notes", "cmd_release_notes"),
    "cmd_changelog": ("harness.commands.changelog", "cmd_changelog"),
    "cmd_checkpoint": ("harness.commands.checkpoint", "cmd_checkpoint"),
    "cmd_cockpit": ("harness.commands.cockpit", "cmd_cockpit"),
    "cmd_clean": ("harness.commands.clean", "cmd_clean"),
}

__all__ = list(_COMMAND_MAP.keys())


def __getattr__(name: str) -> Any:
    spec = _COMMAND_MAP.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod_name, attr_name = spec
    value = getattr(importlib.import_module(mod_name), attr_name)
    globals()[name] = value
    return value


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(__all__))
