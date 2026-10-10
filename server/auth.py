# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Authentication and Authorization Module for PSL Telemetry Hub (ADR-030).

Verifies GitHub Personal Access Tokens (PAT) against GitHub API for organization
membership (`purrfectsoft`), with 300s in-memory token caching and hermetic test mode.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import threading
import time
from typing import Dict, Optional, Tuple
import urllib.error
import urllib.request


@dataclass
class AuthResult:
    """Result of GitHub PAT verification."""
    authenticated: bool
    username: Optional[str] = None
    org: Optional[str] = None
    status_code: int = 200
    error: Optional[str] = None


# Thread-safe in-memory cache: token_hash -> (expiry_timestamp, AuthResult)
_TOKEN_CACHE: Dict[str, Tuple[float, AuthResult]] = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL_SECONDS = 300.0


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clear_auth_cache() -> None:
    """Clears the token verification cache."""
    with _CACHE_LOCK:
        _TOKEN_CACHE.clear()


def verify_github_token(token: Optional[str]) -> AuthResult:
    """Verifies a GitHub token against GitHub API and checks organization membership."""
    if not token or not token.strip():
        return AuthResult(
            authenticated=False,
            status_code=401,
            error="Missing or empty authentication token",
        )

    token_clean = token.strip()
    if token_clean.lower().startswith("bearer "):
        token_clean = token_clean[7:].strip()

    org = os.environ.get("PSL_GITHUB_ORG", "purrfectsoft").strip()
    team = os.environ.get("PSL_GITHUB_TEAM")

    # 1. Hermetic test bypass mode
    if os.environ.get("PSL_HUB_TEST_AUTH") == "1":
        if token_clean in ("invalid-token", "expired-token", ""):
            return AuthResult(
                authenticated=False,
                status_code=401,
                org=org,
                error="Invalid or expired GitHub token",
            )
        if token_clean in ("forbidden-token", "non-member-token"):
            return AuthResult(
                authenticated=False,
                username="external-user",
                status_code=403,
                org=org,
                error=f"User is not an authorized member of organization '{org}'",
            )
        if token_clean in ("team-forbidden-token",):
            return AuthResult(
                authenticated=False,
                username="team-forbidden-user",
                status_code=403,
                org=org,
                error=f"User is not an authorized member of team '{team}'",
            )

        username = "test-user"
        if token_clean.startswith("test-token-"):
            username = token_clean[len("test-token-"):]
        return AuthResult(
            authenticated=True,
            username=username,
            org=org,
            status_code=200,
        )

    # 2. Check token cache
    token_key = _hash_token(token_clean)
    now = time.time()
    with _CACHE_LOCK:
        if token_key in _TOKEN_CACHE:
            expires_at, cached_res = _TOKEN_CACHE[token_key]
            if now < expires_at:
                return cached_res
            else:
                del _TOKEN_CACHE[token_key]

    # 3. Query GitHub API: User Profile (/user)
    headers = {
        "Authorization": f"Bearer {token_clean}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "PSL-Telemetry-Hub/1.0.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    req_user = urllib.request.Request("https://api.github.com/user", headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req_user, timeout=10.0) as resp:
            user_data = json.loads(resp.read().decode("utf-8"))
            username = user_data.get("login")
            if not username:
                return AuthResult(
                    authenticated=False,
                    status_code=401,
                    org=org,
                    error="Unable to retrieve username from GitHub profile",
                )
    except urllib.error.HTTPError as err:
        if err.code == 401:
            res = AuthResult(
                authenticated=False,
                status_code=401,
                org=org,
                error="Invalid or expired GitHub token",
            )
            with _CACHE_LOCK:
                _TOKEN_CACHE[token_key] = (now + 60.0, res)
            return res
        return AuthResult(
            authenticated=False,
            status_code=err.code,
            org=org,
            error=f"GitHub API user error: {err.reason}",
        )
    except Exception as exc:
        return AuthResult(
            authenticated=False,
            status_code=500,
            org=org,
            error=f"GitHub API connection failure: {exc}",
        )

    # 4. Query GitHub API: Organization Membership (/orgs/{org}/members/{username})
    org_url = f"https://api.github.com/orgs/{org}/members/{username}"
    req_org = urllib.request.Request(org_url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req_org, timeout=10.0) as resp:
            # 204 No Content indicates the user is a member
            pass
    except urllib.error.HTTPError as err:
        if err.code in (404, 302):
            res = AuthResult(
                authenticated=False,
                username=username,
                status_code=403,
                org=org,
                error=f"User '{username}' is not an authorized member of organization '{org}'",
            )
            with _CACHE_LOCK:
                _TOKEN_CACHE[token_key] = (now + CACHE_TTL_SECONDS, res)
            return res
        return AuthResult(
            authenticated=False,
            username=username,
            status_code=err.code,
            org=org,
            error=f"GitHub organization membership verification error: {err.reason}",
        )

    # 5. Optional Team Check
    if team:
        team_url = f"https://api.github.com/orgs/{org}/teams/{team}/memberships/{username}"
        req_team = urllib.request.Request(team_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req_team, timeout=10.0) as resp:
                team_data = json.loads(resp.read().decode("utf-8"))
                if team_data.get("state") != "active":
                    res = AuthResult(
                        authenticated=False,
                        username=username,
                        status_code=403,
                        org=org,
                        error=f"User '{username}' is not active in team '{team}'",
                    )
                    with _CACHE_LOCK:
                        _TOKEN_CACHE[token_key] = (now + CACHE_TTL_SECONDS, res)
                    return res
        except urllib.error.HTTPError as err:
            res = AuthResult(
                authenticated=False,
                username=username,
                status_code=403,
                org=org,
                error=f"User '{username}' is not a member of team '{team}': {err.reason}",
            )
            with _CACHE_LOCK:
                _TOKEN_CACHE[token_key] = (now + CACHE_TTL_SECONDS, res)
            return res

    # 6. Verification Succeeded
    success_res = AuthResult(
        authenticated=True,
        username=username,
        org=org,
        status_code=200,
    )
    with _CACHE_LOCK:
        _TOKEN_CACHE[token_key] = (now + CACHE_TTL_SECONDS, success_res)
    return success_res
