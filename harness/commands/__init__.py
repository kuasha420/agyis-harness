# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis CLI command modules (ADR-014).
"""

from __future__ import annotations

from harness.commands.doctor import cmd_doctor
from harness.commands.hook import cmd_hook
from harness.commands.test import cmd_test
from harness.commands.audit import cmd_audit
from harness.commands.auth import cmd_auth
from harness.commands.sync import cmd_sync
from harness.commands.skills import cmd_skills
from harness.commands.rules import cmd_rules
from harness.commands.agents import cmd_agents
from harness.commands.subagents import cmd_subagents
from harness.commands.remote import cmd_remote
from harness.commands.status import cmd_status
from harness.commands.install import cmd_init, cmd_install, cmd_uninstall
from harness.commands.harmonize import cmd_harmonize
from harness.commands.onboard import cmd_onboard
from harness.commands.verify import cmd_verify
from harness.commands.gui import cmd_gui
from harness.commands.release_notes import cmd_release_notes
from harness.commands.checkpoint import cmd_checkpoint
from harness.commands.cockpit import cmd_cockpit
from harness.commands.clean import cmd_clean

__all__ = [
    "cmd_doctor",
    "cmd_hook",
    "cmd_test",
    "cmd_audit",
    "cmd_auth",
    "cmd_sync",
    "cmd_skills",
    "cmd_rules",
    "cmd_agents",
    "cmd_subagents",
    "cmd_remote",
    "cmd_status",
    "cmd_init",
    "cmd_install",
    "cmd_uninstall",
    "cmd_harmonize",
    "cmd_onboard",
    "cmd_verify",
    "cmd_gui",
    "cmd_release_notes",
    "cmd_checkpoint",
    "cmd_cockpit",
    "cmd_clean",
]
