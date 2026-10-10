# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Authentication and HTTP client utilities for telemetry sync (ADR-030).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
import urllib.error
import urllib.request

from harness.telemetry import config


def verify_auth_token(
    endpoint: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Verifies GitHub PAT against the centralized telemetry hub (/api/v1/auth/verify)."""
    resolved_endpoint = endpoint or config.get_sync_endpoint()
    resolved_token = token or config.get_auth_token()

    if not resolved_endpoint:
        raise ValueError("Sync endpoint required for token verification.")
    if not resolved_token:
        raise ValueError("Authentication token required for token verification.")

    endpoint_clean = resolved_endpoint.rstrip("/")
    url = f"{endpoint_clean}/api/v1/auth/verify"
    payload = json.dumps({"token": resolved_token}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {resolved_token}",
            "Content-Type": "application/json",
            "User-Agent": "psl-harness/1.0.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as err:
        err_body = ""
        try:
            err_body = err.read().decode("utf-8")
        except Exception:
            pass
        raise ValueError(
            f"Token verification failed (HTTP {err.code}): {err_body or err.reason}"
        ) from err
    except urllib.error.URLError as err:
        raise ConnectionError(
            f"Failed to connect to telemetry hub at {url}: {err.reason}"
        ) from err
