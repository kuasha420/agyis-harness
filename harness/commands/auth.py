# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Telemetry authentication CLI command (ADR-014, ADR-030).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
import urllib.error

from harness.telemetry import config


def cmd_auth(args: argparse.Namespace) -> int:
    """Manages GitHub PAT authentication and telemetry credentials."""
    sub = getattr(args, "auth_cmd", None) or "status"

    if sub == "login":
        token = getattr(args, "token", None)
        endpoint = getattr(args, "endpoint", None) or config.get_sync_endpoint()

        if getattr(args, "gh", False):
            token = config.get_gh_cli_token()
            if not token:
                sys.stderr.write("Error: Failed to retrieve token from GitHub CLI ('gh auth token'). Ensure gh is installed and authenticated.\n")
                return 1

        if not token:
            if sys.stdin.isatty():
                gh_token = config.get_gh_cli_token()
                if gh_token:
                    try:
                        ans = input("GitHub CLI token detected. Use it for authentication? [Y/n]: ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        sys.stderr.write("\nAborted.\n")
                        return 1
                    if ans in ("", "y", "yes"):
                        token = gh_token

            if not token:
                if sys.stdin.isatty():
                    import getpass
                    try:
                        token = getpass.getpass("Enter GitHub Personal Access Token (PAT): ").strip()
                    except (EOFError, KeyboardInterrupt):
                        sys.stderr.write("\nAborted.\n")
                        return 1
                else:
                    try:
                        token = input().strip()
                    except (EOFError, KeyboardInterrupt):
                        sys.stderr.write("Error: GitHub PAT required. Provide via --token or stdin.\n")
                        return 1

        if not token:
            sys.stderr.write("Error: GitHub PAT required.\n")
            return 1

        from harness.telemetry.sync import verify_auth_token
        try:
            verify_res = verify_auth_token(endpoint=endpoint, token=token)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                sys.stderr.write("Error 401: Invalid GitHub Personal Access Token.\n")
            elif exc.code == 403:
                sys.stderr.write("Error 403: User is not an authorized member of the organization.\n")
            else:
                sys.stderr.write(f"Error {exc.code}: {exc.reason}\n")
            return 1
        except Exception as exc:
            sys.stderr.write(f"Error verifying authentication: {exc}\n")
            return 1

        username = verify_res.get("username")
        org = verify_res.get("org", "purrfectsoft")

        config.save_credentials({
            "token": token,
            "github_username": username,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        if getattr(args, "workspace_scope", False):
            ws_cfg = config.load_config()
            if getattr(args, "endpoint", None):
                ws_cfg["endpoint"] = endpoint
            config.save_config(ws_cfg, scope="workspace")
        elif getattr(args, "endpoint", None):
            cfg = config.load_config()
            cfg["endpoint"] = endpoint
            config.save_config(cfg, scope="global")

        if getattr(args, "json", False):
            print(json.dumps({
                "status": "success",
                "authenticated": True,
                "username": username,
                "org": org,
                "endpoint": endpoint,
            }, indent=2))
        else:
            print(f"✔ Successfully authenticated as {username} ({org})")
            print(f"  Endpoint: {endpoint}")
        return 0

    elif sub == "status":
        creds = config.load_credentials()
        cfg = config.load_config()
        endpoint = cfg.get("endpoint", "http://localhost:8000")
        token = creds.get("token")
        username = creds.get("github_username")
        is_auth = bool(token and username)

        masked = None
        if token:
            masked = f"{token[:4]}****{token[-4:]}" if len(token) > 8 else "****"

        if getattr(args, "json", False):
            print(json.dumps({
                "authenticated": is_auth,
                "username": username,
                "token_masked": masked,
                "endpoint": endpoint,
            }, indent=2))
            return 0 if is_auth else 1

        print("=" * 60)
        print(" PSL Telemetry Authentication Status")
        print("=" * 60)
        print(f"  Authenticated: {'Yes' if is_auth else 'No'}")
        print(f"  Username:      {username or 'Not logged in'}")
        print(f"  Token:         {masked or 'None'}")
        print(f"  Hub Endpoint:  {endpoint}")
        print("=" * 60)
        return 0 if is_auth else 1

    elif sub == "logout":
        config.clear_credentials()
        if getattr(args, "json", False):
            print(json.dumps({"status": "success", "message": "Credentials cleared successfully."}, indent=2))
        else:
            print("✔ Credentials cleared successfully.")
        return 0

    else:
        sys.stderr.write(f"Error: Unknown auth command '{sub}'. Use login, status, or logout.\n")
        return 1
