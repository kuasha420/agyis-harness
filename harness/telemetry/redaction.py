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
from typing import Any, Dict, List, Optional, Tuple, Union

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

# CLI password/API key/token flags (--password <val>, --api-key=<val>, --token=<val>, --csrf-token=<val>)
CLI_FLAG_PATTERN = re.compile(
    r"(--(?:password|passwd|api[_-]?key|(?:(?:access|auth|csrf)[_-]?)?token)(?:=|\s+))([\"']?)(?!\[REDACTED)([^\"'\s\r\n]+)\2",
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

# Assignments: password=..., api_key=..., aws_secret_access_key=..., secret_key=..., client_secret=...,
# token=..., access_token=..., auth_token=..., refresh_token=..., session_token=..., private_key=...,
# CSRF tokens (ANTIGRAVITY_CSRF_TOKEN=..., CODEIUM_CSRF_TOKEN=..., x-antigravity-csrf-token: ..., "csrfToken": "...")
ASSIGNMENT_PATTERN = re.compile(
    r"\b(?P<key>"
    r"p(?:ass(?:word|wd)|rivate[_-]?key)"
    r"|a(?:pi[_-]?key|ccess[_-]?token|uth[_-]?token|ws[-_]?secret[-_]?access[-_]?key|ntigravity[_-]?(?:csrf|xsrf)[_-]?token)"
    r"|c(?:lient[_-]?secret|srf[_-]?token|odeium[_-]?(?:csrf|xsrf)[_-]?token)"
    r"|x(?:[-_](?:(?:antigravity|codeium)[_-])?(?:csrf|xsrf)[_-]?token|srf[_-]?token)"
    r"|s(?:ecret[_-]?key|ession[_-]?token)"
    r"|(?:refresh|id)[_-]?token"
    r"|token"
    r")"
    r"(?P<sep>[\"']?\s*[:=]\s*)(?P<q>[\"']?)(?!\[REDACTED|none\b|null\b|false\b|true\b)(?P<val>[^\"'\s\r\n]+)(?P=q)",
    flags=re.IGNORECASE,
)

# Extra literal-gated pattern for arbitrary *_CSRF_TOKEN env vars when "csrf"/"xsrf" is present
_PREF_CSRF_PATTERN = re.compile(
    r"\b(?P<key>[A-Za-z0-9_-]*[_-](?:csrf|xsrf)[_-]?token)"
    r"(?P<sep>[\"']?\s*[:=]\s*)(?P<q>[\"']?)(?!\[REDACTED|none\b|null\b|false\b|true\b)(?P<val>[^\"'\s\r\n]+)(?P=q)",
    flags=re.IGNORECASE,
)

# Generic Unix/macOS user home directory pattern
HOME_DIR_PATTERN = re.compile(r"/(?:home|Users)/[A-Za-z0-9_\.\-]+")

# Crosstalk sensitive file blocks and references (.dirtyroom/, .env, *.pem, *.key)
_SENSITIVE_FENCE_PATTERN = re.compile(
    r"(?P<fence>`{3,}|~{3,})[ \t]*(?P<info>[^\r\n]*?(?:\.dirtyroom(?:[/\\][^\r\n]*)?|(?:^|[/\\\s])\.env(?:\.[A-Za-z0-9_.-]+)?|\bdotenv\b|\benv\b|[\w.\-/\\]+\.(?:pem|key)))\r?\n[\s\S]*?\r?\n(?P=fence)",
    flags=re.IGNORECASE,
)
_DIRTYROOM_REF_PATTERN = re.compile(
    r"(?:[A-Za-z0-9_.\-~[\]/\\]*\.dirtyroom(?:[/\\][^\s\"'<>)}\],;]*)?)",
    flags=re.IGNORECASE,
)
_ENV_FILE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z0-9_.\-~[\]/\\]*[/\\])?(?:\.env(?:\.[A-Za-z0-9_.-]+)?|[A-Za-z0-9_-]+\.env(?:\.[A-Za-z0-9_.-]+)?)(?=$|[\s\"'`),;:\]}])",
    flags=re.IGNORECASE,
)
_KEY_FILE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:(?:[A-Za-z0-9_.\-~[\]/\\]+[/\\])[A-Za-z0-9_.\-]+\.(?:pem|key)|(?!(?:e|ev|evt|event|obj|item|row|node|entry|record|field|prop|primary|foreign|sort|dict)\.)[A-Za-z0-9_.\-]+\.(?:pem|key))(?=$|[\s\"'`),;:\]}])",
    flags=re.IGNORECASE,
)
_STRICT_EXTRA_ASSIGNMENT_PATTERN = re.compile(
    r"\b(?P<key>[A-Za-z0-9_-]*(?:secret|cookie|credential|jwt)[A-Za-z0-9_-]*)"
    r"(?P<sep>[\"']?\s*[:=]\s*)(?P<q>[\"']?)(?!\[REDACTED|none\b|null\b|false\b|true\b)(?P<val>[^\"'\s\r\n]+)(?P=q)",
    flags=re.IGNORECASE,
)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")


def _cli_flag_replacer(match: re.Match) -> str:
    flag = match.group(1)
    quote = match.group(2) or ""
    flag_lower = flag.lower()
    if "pass" in flag_lower:
        marker = "[REDACTED_PASSWORD]"
    elif "token" in flag_lower:
        marker = "[REDACTED_SECRET]"
    else:
        marker = "[REDACTED_API_KEY]"
    return f"{flag}{quote}{marker}{quote}"


def _assignment_replacer(match: re.Match) -> str:
    key = match.group("key")
    sep = match.group("sep")
    quote = match.group("q") or ""
    val = match.group("val")
    key_lower = key.lower()
    if "secret" in key_lower and len(val) < 8:
        return match.group(0)
    if "pass" in key_lower:
        marker = "[REDACTED_PASSWORD]"
    elif "api" in key_lower:
        marker = "[REDACTED_API_KEY]"
    elif "private" in key_lower:
        marker = "[REDACTED_PRIVATE_KEY]"
    else:
        marker = "[REDACTED_SECRET]"
    return f"{key}{sep}{quote}{marker}{quote}"


def _strip_secrets_with_count(text: str) -> Tuple[str, int]:
    """Strips credentials/tokens from text and returns (sanitized_text, exact_redaction_count)."""
    if not text:
        return text, 0

    redactions = 0

    # 1. Private keys
    if "-----BEGIN " in text:
        text, n = PRIVATE_KEY_PATTERN.subn("[REDACTED_PRIVATE_KEY]", text)
        redactions += n

    # 2. URLs with passwords
    if "://" in text and "@" in text:
        text, n = URL_PASSWORD_PATTERN.subn(r"\g<1>[REDACTED_PASSWORD]\g<3>", text)
        redactions += n

    text_lower = text.lower()

    # 3. CLI password, API key, and token flags
    if (
        "--password" in text_lower
        or "--passwd" in text_lower
        or "--api" in text_lower
        or "--token" in text_lower
        or "--access" in text_lower
        or "--auth" in text_lower
        or "--csrf" in text_lower
    ):
        text, n = CLI_FLAG_PATTERN.subn(_cli_flag_replacer, text)
        if n:
            redactions += n
            text_lower = text.lower()

    # 4. Bearer tokens
    if "bearer" in text_lower:
        text, n = BEARER_PATTERN.subn("Bearer [REDACTED_SECRET]", text)
        if n:
            redactions += n
            text_lower = text.lower()

    # 5. Authorization headers
    if "authoriz" in text_lower:
        text, n = AUTH_HEADER_PATTERN.subn(r"\g<1>[REDACTED_SECRET]", text)
        if n:
            redactions += n
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
        text, n = GITHUB_PATTERN.subn("[REDACTED_GITHUB_TOKEN]", text)
        redactions += n

    if "AKIA" in text or "ASIA" in text:
        text, n = AWS_KEY_PATTERN.subn("[REDACTED_AWS_KEY]", text)
        redactions += n

    if "sk-" in text:
        text, n = OPENAI_KEY_PATTERN.subn("[REDACTED_API_KEY]", text)
        redactions += n

    if "AIza" in text:
        text, n = GOOGLE_AI_PATTERN.subn("[REDACTED_API_KEY]", text)
        redactions += n

    if "xox" in text:
        text, n = SLACK_KEY_PATTERN.subn("[REDACTED_API_KEY]", text)
        redactions += n

    if "key-" in text:
        text, n = MAILGUN_KEY_PATTERN.subn("[REDACTED_API_KEY]", text)
        redactions += n

    # 7. Assignments (password=..., api_key=..., secret_key=..., token=..., private_key=..., csrf_token=...)
    if ("=" in text or ":" in text) and (
        "password" in text_lower
        or "passwd" in text_lower
        or "api" in text_lower
        or "secret" in text_lower
        or "token" in text_lower
        or "private" in text_lower
    ):
        assign_hits = [0]

        def _counted_assign(match: re.Match) -> str:
            replaced = _assignment_replacer(match)
            if replaced != match.group(0):
                assign_hits[0] += 1
            return replaced

        text = ASSIGNMENT_PATTERN.sub(_counted_assign, text)
        redactions += assign_hits[0]

        if "csrf" in text_lower or "xsrf" in text_lower:
            text, n = _PREF_CSRF_PATTERN.subn(
                r"\g<key>\g<sep>\g<q>[REDACTED_SECRET]\g<q>",
                text,
            )
            redactions += n

    return text, redactions


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
    - Authorization headers & CSRF tokens -> [REDACTED_SECRET]

    Maintains <1ms latency on 10KB payloads through pre-compiled regexes
    and literal-prefix skipping.
    """
    cleaned, _ = _strip_secrets_with_count(text)
    return cleaned


def _anonymize_paths_with_count(
    text: str,
    workspace_root: Optional[Union[Path, str]] = None,
    home_dir: Optional[Union[Path, str]] = None,
    home_replacement: str = "[USER_HOME]",
    extra_roots: Optional[List[Tuple[Union[Path, str], str]]] = None,
) -> Tuple[str, int]:
    """Anonymizes workspace/home filesystem paths and returns (text, exact_replacement_count)."""
    if not text:
        return text, 0

    replaced_count = 0
    ws_pairs: List[Tuple[str, str]] = []
    seen_cands: set[str] = set()

    def _collect_root(root_val: Optional[Union[Path, str]], placeholder: str) -> None:
        if not root_val:
            return
        raw_s = str(root_val).rstrip("/")
        try:
            res_s = str(Path(root_val).expanduser().resolve()).rstrip("/")
        except OSError:
            res_s = raw_s
        for cand in sorted({res_s, raw_s}, key=len, reverse=True):
            if cand and cand != "/" and cand not in seen_cands:
                seen_cands.add(cand)
                ws_pairs.append((cand, placeholder))

    _collect_root(workspace_root, "[WORKSPACE_ROOT]")
    if extra_roots:
        for root_val, placeholder in extra_roots:
            _collect_root(root_val, placeholder)

    for cand, placeholder in sorted(ws_pairs, key=lambda item: len(item[0]), reverse=True):
        cnt = text.count(cand)
        if cnt:
            text = text.replace(cand, placeholder)
            replaced_count += cnt

    # Specific home_dir replacement (if provided)
    if home_dir:
        hd_str = str(Path(home_dir).resolve()).rstrip("/")
        hd_raw = str(home_dir).rstrip("/")
        for cand in sorted({hd_str, hd_raw}, key=len, reverse=True):
            if cand and cand != "/":
                cnt = text.count(cand)
                if cnt:
                    text = text.replace(cand, home_replacement)
                    replaced_count += cnt

    # System home directory replacement
    try:
        sys_home = str(Path.home().resolve()).rstrip("/")
        if sys_home and sys_home != "/":
            cnt = text.count(sys_home)
            if cnt:
                text = text.replace(sys_home, home_replacement)
                replaced_count += cnt
    except (RuntimeError, KeyError):
        pass

    # Generic /home/<user> or /Users/<user> pattern
    text, n = HOME_DIR_PATTERN.subn(home_replacement, text)
    replaced_count += n

    return text, replaced_count


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
    cleaned, _ = _anonymize_paths_with_count(
        text,
        workspace_root=workspace_root,
        home_dir=home_dir,
        home_replacement=home_replacement,
    )
    return cleaned


def _redact_sensitive_blocks_and_refs(
    text: str,
    *,
    strict: bool = False,
) -> Tuple[str, int, int, List[str], bool]:
    """Scans/redacts .dirtyroom/, .env, *.pem, *.key blocks & refs and optional strict PII/secrets."""
    if not text:
        return text, 0, 0, [], False

    blocked_refs = 0
    extra_secrets = 0
    categories: List[str] = []
    dirtyroom_detected = False

    def _add_cat(name: str) -> None:
        if name not in categories:
            categories.append(name)

    # 1. Fenced sensitive file blocks (```.env, ```.dirtyroom/..., ```server.key, ```cert.pem)
    if "```" in text or "~~~" in text:
        def _fence_repl(match: re.Match) -> str:
            nonlocal blocked_refs, dirtyroom_detected
            blocked_refs += 1
            info_l = (match.group("info") or "").lower()
            if ".dirtyroom" in info_l:
                dirtyroom_detected = True
                _add_cat("dirtyroom")
            elif ".env" in info_l or "dotenv" in info_l or info_l.strip() == "env":
                _add_cat("env_file")
            elif ".pem" in info_l:
                _add_cat("pem_file")
            elif ".key" in info_l:
                _add_cat("key_file")
            return f"{match.group('fence')}\n[REDACTED_SENSITIVE_BLOCK]\n{match.group('fence')}"

        text = _SENSITIVE_FENCE_PATTERN.sub(_fence_repl, text)

    # 2. .dirtyroom/ path references
    if ".dirtyroom" in text.lower():
        text, n = _DIRTYROOM_REF_PATTERN.subn("[REDACTED_DIRTYROOM_REF]", text)
        if n:
            blocked_refs += n
            dirtyroom_detected = True
            _add_cat("dirtyroom")

    # 3. .env file references
    if ".env" in text.lower():
        text, n = _ENV_FILE_PATTERN.subn("[REDACTED_ENV_REF]", text)
        if n:
            blocked_refs += n
            _add_cat("env_file")

    # 4. *.pem / *.key references
    text_l = text.lower()
    if ".pem" in text_l or ".key" in text_l:
        def _key_repl(match: re.Match) -> str:
            nonlocal blocked_refs
            blocked_refs += 1
            raw = match.group(0).lower()
            _add_cat("pem_file" if raw.endswith(".pem") else "key_file")
            return "[REDACTED_KEY_REF]"

        text = _KEY_FILE_PATTERN.sub(_key_repl, text)

    # 5. Strict cross-project scrubbing (extra secret assignments + email addresses)
    if strict:
        extra_hits = [0]

        def _strict_repl(match: re.Match) -> str:
            extra_hits[0] += 1
            return f"{match.group('key')}{match.group('sep')}{match.group('q')}[REDACTED_SECRET]{match.group('q')}"

        text = _STRICT_EXTRA_ASSIGNMENT_PATTERN.sub(_strict_repl, text)
        extra_secrets += extra_hits[0]
        if "@" in text:
            text, n_email = _EMAIL_PATTERN.subn("[REDACTED_EMAIL]", text)
            extra_secrets += n_email

    return text, blocked_refs, extra_secrets, categories, dirtyroom_detected


def sanitize_crosstalk_payload(
    text: str,
    *,
    source_ws: Optional[Union[Path, str]] = None,
    target_ws: Optional[Union[Path, str]] = None,
    strict: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    """
    Sanitizes cross-conversation / cross-project crosstalk payloads cleanly.

    Runs strip_secrets(), anonymizes source/target workspace & user home paths,
    and scrubs sensitive file blocks/references (.dirtyroom/, .env, *.pem, *.key).
    Returns (sanitized_text, audit_summary) with exact counts:
    secrets_redacted, paths_anonymized, blocked_refs.
    """
    if not text:
        return text, {
            "secrets_redacted": 0,
            "paths_anonymized": 0,
            "blocked_refs": 0,
            "blocked_categories": [],
            "has_blocked_refs": False,
            "dirtyroom_detected": False,
            "strict": bool(strict),
        }

    cleaned, secrets_count = _strip_secrets_with_count(text)

    extra_roots: List[Tuple[Union[Path, str], str]] = []
    if target_ws:
        same_ws = False
        if source_ws:
            try:
                same_ws = Path(source_ws).expanduser().resolve() == Path(target_ws).expanduser().resolve()
            except OSError:
                same_ws = str(source_ws).rstrip("/") == str(target_ws).rstrip("/")
        if not same_ws:
            extra_roots.append((target_ws, "[TARGET_WORKSPACE]"))

    cleaned, paths_count = _anonymize_paths_with_count(
        cleaned,
        workspace_root=source_ws,
        extra_roots=extra_roots or None,
    )

    cleaned, blocked_refs, extra_secrets, categories, dirtyroom_detected = _redact_sensitive_blocks_and_refs(
        cleaned,
        strict=strict,
    )
    secrets_count += extra_secrets

    audit_summary: Dict[str, Any] = {
        "secrets_redacted": secrets_count,
        "paths_anonymized": paths_count,
        "blocked_refs": blocked_refs,
        "blocked_categories": categories,
        "has_blocked_refs": blocked_refs > 0,
        "dirtyroom_detected": dirtyroom_detected,
        "strict": bool(strict),
    }
    return cleaned, audit_summary


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
                result[key] = anonymize_paths(
                    strip_secrets(value), workspace_root=workspace_root
                )
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
