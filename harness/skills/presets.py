# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Modular Skills Preset Dictionaries & Runtime Configurations.
"""

from __future__ import annotations

from typing import Dict, List

LANGUAGE_RUNTIME_PRESETS: Dict[str, List[str]] = {
    "typescript": [
        "psl-stack-typescript",
        "psl-test-node",
    ],
    "node": [
        "psl-stack-typescript",
        "psl-test-node",
    ],
    "javascript": [
        "psl-stack-typescript",
        "psl-test-node",
    ],
    "python": [
        "psl-stack-python",
        "psl-test-python",
    ],
    "rust": [
        "psl-test-cargo",
        "psl-stack-systems",
        "psl-stack-shell",
    ],
    "cargo": [
        "psl-test-cargo",
        "psl-stack-systems",
        "psl-stack-shell",
    ],
    "go": [
        "psl-test-go",
    ],
    "systems": [
        "psl-stack-systems",
        "psl-stack-shell",
    ],
    "shell": [
        "psl-stack-shell",
    ],
}

ARCHITECTURAL_ROLE_PRESETS: Dict[str, List[str]] = {
    "backend": [
        "psl-stack-backend",
        "db-ops",
    ],
    "frontend": [
        "modern-web-guidance",
    ],
    "fullstack": [
        "modern-web-guidance",
        "psl-stack-backend",
        "db-ops",
    ],
    "mobile": [
        "android-cli",
    ],
    "desktop_gui": [
        "display-ops",
    ],
    "cli": [],
    "library": [],
    "media": [
        "media-ops",
    ],
    "audio": [
        "audio-ops",
    ],
    "infra": [
        "mesh-ops",
        "remote-ops",
        "sec-forensics",
        "storage-ops",
    ],
}

# Backward compatibility mapping for STACK_PRESETS
STACK_PRESETS: Dict[str, List[str]] = {
    **LANGUAGE_RUNTIME_PRESETS,
    "backend": [
        "psl-stack-backend",
        "db-ops",
    ],
}

GROUP_PRESETS: Dict[str, List[str]] = {
    "stack": [
        "psl-stack-python",
        "psl-stack-typescript",
        "psl-stack-shell",
        "psl-stack-systems",
        "psl-stack-backend",
    ],
    "testing": [
        "psl-test-python",
        "psl-test-node",
        "psl-test-cargo",
        "psl-test-go",
        "psl-test-harmonize",
    ],
    "runners": [
        "psl-test-python",
        "psl-test-node",
        "psl-test-cargo",
        "psl-test-go",
        "psl-test-harmonize",
    ],
    "ops": [
        "storage-ops",
        "audio-ops",
        "display-ops",
        "sec-forensics",
        "media-ops",
        "db-ops",
        "mesh-ops",
        "git-worktree-ops",
        "remote-ops",
    ],
    "workstation": [
        "storage-ops",
        "audio-ops",
        "display-ops",
        "sec-forensics",
        "media-ops",
        "db-ops",
        "mesh-ops",
        "git-worktree-ops",
    ],
    "workflow": [
        "agent-builder",
        "subagent-ladder",
        "milestone-handoff",
        "code-review",
        "psl-audit-toolkit",
    ],
    "ladder": [
        "agent-builder",
        "subagent-ladder",
        "milestone-handoff",
        "code-review",
    ],
    "resilience": [
        "powerloss-resume",
        "db-ops",
        "storage-ops",
    ],
    "continuity": [
        "graceful-parking",
        "milestone-handoff",
        "git-worktree-ops",
    ],
}
