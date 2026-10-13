# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Client Sync Engine for PSL Telemetry (ADR-030).
"""

from __future__ import annotations

from harness.telemetry.schema import ensure_sync_columns
from harness.telemetry.sync.constants import (
    DEFAULT_BATCH_SESSION_LIMIT,
    DEFAULT_BATCH_STEP_LIMIT,
    _get_retry_backoff,
)
from harness.telemetry.sync.client import verify_auth_token
from harness.telemetry.sync.ui import interactive_select_sessions
from harness.telemetry.sync.push import push_local_sessions
from harness.telemetry.sync.pull import pull_remote_sessions
from harness.telemetry.sync.coordinator import sync_telemetry
from harness.telemetry.sync.systemd import generate_systemd_service
from harness.telemetry.sync.daemon import watch_and_sync

__all__ = [
    "DEFAULT_BATCH_SESSION_LIMIT",
    "DEFAULT_BATCH_STEP_LIMIT",
    "_get_retry_backoff",
    "ensure_sync_columns",
    "verify_auth_token",
    "interactive_select_sessions",
    "push_local_sessions",
    "pull_remote_sessions",
    "sync_telemetry",
    "generate_systemd_service",
    "watch_and_sync",
]
