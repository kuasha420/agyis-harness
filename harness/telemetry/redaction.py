# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Client-Side Redaction & Sanitization Engine (ADR-030).

Provides deterministic, hermetic redaction for developer sessions, prompts,
and tool calls before telemetry serialization or transmission:
- strip_secrets: Removes API keys, tokens, credentials, private keys, passwords
- anonymize_paths: Anonymizes workspace roots and user home directories
- sanitize_intervention: Scrubs user prompts across sanitize, omit, and metadata_only modes
- sanitize_tool_call: Recursively sanitizes tool call dicts (arguments_json, snippets, paths)

Zero external dependencies: only standard library (re, json, os, pathlib, typing, copy).
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, Optional, Union

# ---------------------------------------------------------------------------
# Pre-compiled high-performance regex patterns
# ---------------------------------------------------------------------------

# Private keys (PEM blocks)
PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN [A-Z0-9_ -]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9_ -]*PRIVATE KEY-----"
)

# URLs with embedded credentials (e.g., postgres://user:pass@host:5432/db)
URL_PASSWORD_PATTERN = re.compile(
    r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:\s/@]*:)(?!\[REDACTED)([^@\s/]+)(@[^\s/]+)"
)

# CLI password flags (--password <val>, --password=<val>, --passwd <val>)
# and API key CLI flags (--api-key <val>, --api-key=<val>)
CLI_FLAG_PATTERN = re.compile(
    r"(--(?:password|passwd|api[_-]?key)(?:=|\s+))([\"']?)(?!\[REDACTED)([^\"'\s\r\n]+)\2",
    flags=re.IGNORECASE,
)

# Bearer tokens (Bearer <token> -> Bearer [REDACTED_SECRET])
BEARER_PATTERN = re.compile(
    r"Bearer\s+(?!\[REDACTED)[A-Za-z0-9_\-\.=~+/]+",
    flags=re.IGNORECASE,
)

# Authorization headers (Basic, Token, or raw tokens that are not Bearer)
AUTH_HEADER_PATTERN = re.compile(
    r"(Authorization\s*:\s*(?:Basic\s+|Token\s+)?)(?!(?:Bearer\s+)?\[REDACTED)([^\s\r\n,;\"']+)",
    flags=re.IGNORECASE,
)

# GitHub tokens (ghp_, gho_, ghu_, ghs_, ghr_, github_pat_)
GITHUB_PATTERN = re.compile(
    r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{16,}"
)

# AWS Access Key IDs (AKIA..., ASIA...)
AWS_KEY_PATTERN = re.compile(
    r"(?:AKIA|ASIA)[0-9A-Z]{16}"
)

# OpenAI API keys (sk-..., sk-proj-...)
OPENAI_KEY_PATTERN = re.compile(
    r"sk-(?:proj-|admin-)?[A-Za-z0-9_\-]{20,}"
)

# Google AI / GCP API keys (AIzaSy...)
GOOGLE_AI_PATTERN = re.compile(
    r"AIza[0-9A-Za-z_\-]{30,}"
)

# Slack tokens (xoxb-, xoxp-, xoxa-, xoxr-, xoxs-)
SLACK_KEY_PATTERN = re.compile(
    r"xox[baprs]-[0-9A-Za-z\-]{10,}"
)

# Mailgun and generic key- prefixed tokens
MAILGUN_KEY_PATTERN = re.compile(
    r"key-[A-Za-z0-9_\-]{16,}"
)

# Assignments: password=..., api_key=..., aws_secret_access_key=..., secret_key=..., client_secret=...
ASSIGNMENT_PATTERN = re.compile(
    r"\b(?P<k_pwd>password|passwd)"
    r"(?P<sep>\s*[:=]\s*)(?P<q1>[\"']?)(?!\[REDACTED|none\b|null\b|false\b|true\b)(?P<v1>[^\"'\s\r\n]+)(?P=q1)"
    r"|\b(?P<k_api>api[_-]?key)"
    r"(?P<sep2>\s*[:=]\s*)(?P<q2>[\"']?)(?!\[REDACTED|none\b|null\b|false\b|true\b)(?P<v2>[^\"'\s\r\n]+)(?P=q2)"
    r"|\b(?P<k_sec>aws[-_]?secret[-_]?access[-_]?key|secret[_-]?key|client[_-]?secret)"
    r"(?P<sep3>\s*[:=]\s*)(?P<q3>[\"']?)(?!\[REDACTED)(?P<v3>[^\"'\s\r\n]{8,})(?P=q3)",
    flags=re.IGNORECASE,
)

# Generic Unix/macOS user home directory pattern
HOME_DIR_PATTERN = re.compile(r"/(?:home|Users)/[A-Za-z0-9_\.\-]+")


def _cli_flag_replacer(match: re.Match) -> str:
    flag = match.group(1)
    quote = match.group(2) or ""
    flag_lower = flag.lower()
    marker = "[REDACTED_PASSWORD]" if "pass" in flag_lower else "[REDACTED_API_KEY]"
    return f"{flag}{quote}{marker}{quote}"


def _assignment_replacer(match: re.Match) -> str:
    if match.group("k_pwd"):
        key = match.group("k_pwd")
        sep = match.group("sep")
        quote = match.group("q1") or ""
        return f"{key}{sep}{quote}[REDACTED_PASSWORD]{quote}"
    elif match.group("k_api"):
        key = match.group("k_api")
        sep = match.group("sep2")
        quote = match.group("q2") or ""
        return f"{key}{sep}{quote}[REDACTED_API_KEY]{quote}"
    else:
        key = match.group("k_sec")
        sep = match.group("sep3")
        quote = match.group("q3") or ""
        return f"{key}{sep}{quote}[REDACTED_SECRET]{quote}"


def strip_secrets(text: str) -> str:
    """
    Strips sensitive credentials, tokens, passwords, and private keys from text.

    Scans for:
    - Bearer tokens -> Bearer [REDACTED_SECRET]
    - GitHub tokens -> [REDACTED_GITHUB_TOKEN]
    - AWS Access Keys -> [REDACTED_AWS_KEY]
    - API keys (OpenAI, Google AI, Slack, generic) -> [REDACTED_API_KEY]
    - Private keys -> [REDACTED_PRIVATE_KEY]
    - CLI & URL password flags -> [REDACTED_PASSWORD]
    - Authorization headers -> [REDACTED_SECRET]

    Maintains <1ms latency on 10KB payloads through pre-compiled regexes
    and literal-prefix skipping.
    """
    if not text:
        return text

    # 1. Private keys
    if "-----BEGIN " in text:
        text = PRIVATE_KEY_PATTERN.sub("[REDACTED_PRIVATE_KEY]", text)

    # 2. URLs with passwords
    if "://" in text and "@" in text:
        text = URL_PASSWORD_PATTERN.sub(r"\g<1>[REDACTED_PASSWORD]\g<3>", text)

    text_lower = text.lower()

    # 3. CLI password and API key flags
    if "--password" in text_lower or "--passwd" in text_lower or "--api" in text_lower:
        text = CLI_FLAG_PATTERN.sub(_cli_flag_replacer, text)
        text_lower = text.lower()

    # 4. Bearer tokens
    if "bearer" in text_lower:
        text = BEARER_PATTERN.sub("Bearer [REDACTED_SECRET]", text)
        text_lower = text.lower()

    # 5. Authorization headers
    if "authoriz" in text_lower:
        text = AUTH_HEADER_PATTERN.sub(r"\g<1>[REDACTED_SECRET]", text)
        text_lower = text.lower()

    # 6. Specific token providers
    if (
        "ghp_" in text
        or "gho_" in text
        or "ghu_" in text
        or "ghs_" in text
        or "ghr_" in text
        or "github_pat_" in text
    ):
        text = GITHUB_PATTERN.sub("[REDACTED_GITHUB_TOKEN]", text)

    if "AKIA" in text or "ASIA" in text:
        text = AWS_KEY_PATTERN.sub("[REDACTED_AWS_KEY]", text)

    if "sk-" in text:
        text = OPENAI_KEY_PATTERN.sub("[REDACTED_API_KEY]", text)

    if "AIza" in text:
        text = GOOGLE_AI_PATTERN.sub("[REDACTED_API_KEY]", text)

    if "xox" in text:
        text = SLACK_KEY_PATTERN.sub("[REDACTED_API_KEY]", text)

    if "key-" in text:
        text = MAILGUN_KEY_PATTERN.sub("[REDACTED_API_KEY]", text)

    # 7. Assignments (password=..., api_key=..., secret_key=...)
    if (
        "password" in text_lower
        or "passwd" in text_lower
        or "api" in text_lower
        or "secret" in text_lower
    ):
        text = ASSIGNMENT_PATTERN.sub(_assignment_replacer, text)

    return text


def anonymize_paths(
    text: str,
    workspace_root: Optional[Union[Path, str]] = None,
    home_dir: Optional[Union[Path, str]] = None,
    home_replacement: str = "[USER_HOME]",
) -> str:
    """
    Anonymizes filesystem paths in text to preserve privacy across environments.

    - Replaces workspace root path with '[WORKSPACE_ROOT]'
    - Replaces user home directories (/home/<user> or /Users/<user>) with '[USER_HOME]'
    - Preserves relative paths and repository internal directory hierarchy.
    """
    if not text:
        return text

    # 1. Workspace root replacement (if provided)
    if workspace_root:
        ws_str = str(Path(workspace_root).resolve()).rstrip("/")
        ws_raw = str(workspace_root).rstrip("/")
        for cand in sorted({ws_str, ws_raw}, key=len, reverse=True):
            if cand and cand != "/" and cand in text:
                text = text.replace(cand, "[WORKSPACE_ROOT]")

    # 2. Specific home_dir replacement (if provided)
    if home_dir:
        hd_str = str(Path(home_dir).resolve()).rstrip("/")
        hd_raw = str(home_dir).rstrip("/")
        for cand in sorted({hd_str, hd_raw}, key=len, reverse=True):
            if cand and cand != "/" and cand in text:
                text = text.replace(cand, home_replacement)

    # 3. System home directory replacement
    try:
        sys_home = str(Path.home().resolve()).rstrip("/")
        if sys_home and sys_home != "/" and sys_home in text:
            text = text.replace(sys_home, home_replacement)
    except (RuntimeError, KeyError):
        pass

    # 4. Generic /home/<user> or /Users/<user> pattern
    text = HOME_DIR_PATTERN.sub(home_replacement, text)

    return text


def sanitize_intervention(
    prompt: str,
    mode: str = "sanitize",
    workspace_root: Optional[Union[Path, str]] = None,
) -> str:
    """
    Sanitizes developer intervention prompts based on the selected mode:
    - 'sanitize': Strips secrets and anonymizes absolute filesystem paths
    - 'omit': Completely omits prompt contents, returning '[PROMPT_OMITTED]'
    - 'metadata_only': Redacts prompt contents, preserving only character length:
      '[PROMPT_REDACTED len=<length>]'
    """
    if mode == "sanitize":
        cleaned = strip_secrets(prompt)
        return anonymize_paths(cleaned, workspace_root=workspace_root)
    elif mode == "omit":
        return "[PROMPT_OMITTED]"
    elif mode == "metadata_only":
        return f"[PROMPT_REDACTED len={len(prompt)}]"
    else:
        raise ValueError(
            f"Invalid sanitization mode: {mode!r}. Must be 'sanitize', 'omit', or 'metadata_only'."
        )


def _scrub_value(val: Any, workspace_root: Optional[Union[Path, str]]) -> Any:
    """Recursively strips secrets and anonymizes paths within deserialized data structures."""
    if isinstance(val, str):
        return anonymize_paths(strip_secrets(val), workspace_root=workspace_root)
    elif isinstance(val, dict):
        return {k: _scrub_value(v, workspace_root) for k, v in val.items()}
    elif isinstance(val, list):
        return [_scrub_value(item, workspace_root) for item in val]
    return val


def sanitize_tool_call(
    tool_call: Dict[str, Any],
    workspace_root: Optional[Union[Path, str]] = None,
    mode: str = "sanitize",
) -> Dict[str, Any]:
    """
    Sanitizes tool execution telemetry records in a non-destructive manner.

    Recursively scrubs:
    - 'arguments_json': Deserializes valid JSON strings, recursively scrubs all
      string fields, and re-serializes; if invalid JSON, scrubs text directly.
    - 'arguments_snippet', 'command_line', 'error_snippet': Strips secrets and anonymizes paths.
    - 'target_path': Anonymizes paths.

    Returns a deep copy of tool_call without mutating the original dictionary.
    """
    if mode not in ("sanitize", "omit", "metadata_only"):
        raise ValueError(
            f"Invalid sanitization mode: {mode!r}. Must be 'sanitize', 'omit', or 'metadata_only'."
        )

    result: Dict[str, Any] = {}
    for key, value in tool_call.items():
        if key == "arguments_json":
            if mode == "omit":
                result[key] = "[OMITTED]"
            elif mode == "metadata_only":
                result[key] = f"[REDACTED len={len(str(value))}]"
            elif isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    scrubbed = _scrub_value(parsed, workspace_root)
                    result[key] = json.dumps(scrubbed)
                except (json.JSONDecodeError, ValueError):
                    result[key] = anonymize_paths(
                        strip_secrets(value), workspace_root=workspace_root
                    )
            elif isinstance(value, (dict, list)):
                result[key] = _scrub_value(value, workspace_root)
            else:
                result[key] = value

        elif key in ("arguments_snippet", "command_line", "error_snippet"):
            if mode == "omit":
                result[key] = "[OMITTED]"
            elif mode == "metadata_only":
                result[key] = f"[REDACTED len={len(str(value))}]"
            elif isinstance(value, str):
                result[key] = anonymize_paths(
                    strip_secrets(value), workspace_root=workspace_root
                )
            else:
                result[key] = value

        elif key == "target_path":
            if mode == "omit":
                result[key] = "[OMITTED]"
            elif mode == "metadata_only":
                result[key] = f"[REDACTED len={len(str(value))}]"
            elif isinstance(value, str):
                result[key] = anonymize_paths(value, workspace_root=workspace_root)
            else:
                result[key] = value

        elif isinstance(value, dict):
            result[key] = sanitize_tool_call(
                value, workspace_root=workspace_root, mode=mode
            )

        elif isinstance(value, list):
            result[key] = [
                sanitize_tool_call(item, workspace_root=workspace_root, mode=mode)
                if isinstance(item, dict)
                else item
                for item in value
            ]

        else:
            result[key] = (
                copy.deepcopy(value)
                if isinstance(value, (list, dict, set))
                else value
            )

    return result
