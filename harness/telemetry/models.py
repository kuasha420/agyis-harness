# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Canonical Telemetry Models, Timestamp Normalization, and Model Taxonomy (ADR-030 / G0.1).
Pure stdlib module with zero pipeline dependencies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Any, Dict, Optional, Tuple

from harness.trajectory.health import DEFAULT_CONTEXT_WINDOW_TOKENS, infer_model_context_window

_UNKNOWN_SENTINELS = frozenset({"", "unknown", "none", "null", "n/a", "na", "default"})

_EFFORT_RE = re.compile(
    r"(?:^|[\s\-_(/])(extra[\s\-_]?high|xhigh|high|medium|med|low|minimal)(?:$|[\s\-_)/])",
    re.IGNORECASE,
)

_MODEL_RULES: Tuple[Tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"\bgemini[\s\-_]+4[\s\-_]+neon\b", re.IGNORECASE), "gemini-4", "gemini-4-neon"),
    (re.compile(r"\bgemini[\s\-_]+4[\s\-_]+hydrogen\b", re.IGNORECASE), "gemini-4", "gemini-4-hydrogen"),
    (re.compile(r"\bgemini[\s\-_]+4[\s\-_]+argon\b", re.IGNORECASE), "gemini-4", "gemini-4-argon"),
    (re.compile(r"\bgemini[\s\-_]+4[\s\-_]+1m\b", re.IGNORECASE), "gemini-4", "gemini-4-1m"),
    (re.compile(r"\bgemini[\s\-_]+4\b", re.IGNORECASE), "gemini-4", "gemini-4"),
    (re.compile(r"\bgemini[\s\-_]+3[._\-]8[\s\-_]+flash\b", re.IGNORECASE), "gemini-3.8", "gemini-3.8-flash"),
    (re.compile(r"\bgemini[\s\-_]+3[._\-]8\b", re.IGNORECASE), "gemini-3.8", "gemini-3.8"),
    (re.compile(r"\bgemini[\s\-_]+3[._\-]7\b", re.IGNORECASE), "gemini-3.7", "gemini-3.7"),
    (re.compile(r"\bgemini[\s\-_]+3[._\-]6\b", re.IGNORECASE), "gemini-3.6", "gemini-3.6"),
    (re.compile(r"\bgemini[\s\-_]+3[._\-]5\b", re.IGNORECASE), "gemini-3.5", "gemini-3.5"),
    (re.compile(r"\bgemini[\s\-_]+3[._\-]1\b", re.IGNORECASE), "gemini-3.1", "gemini-3.1"),
    (re.compile(r"\bgemini[\s\-_]+3\b", re.IGNORECASE), "gemini-3", "gemini-3"),
    (re.compile(r"\bgemini[\s\-_]+2[._\-]5\b", re.IGNORECASE), "gemini-2.5", "gemini-2.5"),
    (
        re.compile(r"\bclaude[\s\-_]+(?:sonnet[\s\-_]+5[._\-]5|5[._\-]5[\s\-_]+sonnet)\b", re.IGNORECASE),
        "claude-5.5",
        "claude-sonnet-5-5",
    ),
    (
        re.compile(r"\bclaude[\s\-_]+(?:opus[\s\-_]+4[._\-]6|4[._\-]6[\s\-_]+opus)\b", re.IGNORECASE),
        "claude-4.6",
        "claude-opus-4-6",
    ),
    (
        re.compile(r"\bclaude[\s\-_]+(?:sonnet[\s\-_]+4[._\-]6|4[._\-]6[\s\-_]+sonnet)\b", re.IGNORECASE),
        "claude-4.6",
        "claude-sonnet-4-6",
    ),
    (
        re.compile(r"\bclaude[\s\-_]+(?:opus[\s\-_]+4[._\-]5|4[._\-]5[\s\-_]+opus)\b", re.IGNORECASE),
        "claude-4.5",
        "claude-opus-4-5",
    ),
    (
        re.compile(r"\bclaude[\s\-_]+(?:sonnet[\s\-_]+4[._\-]5|4[._\-]5[\s\-_]+sonnet)\b", re.IGNORECASE),
        "claude-4.5",
        "claude-sonnet-4-5",
    ),
    (
        re.compile(r"\bclaude[\s\-_]+(?:opus[\s\-_]+4|4[\s\-_]+opus)(?![._\-]\d)\b", re.IGNORECASE),
        "claude-4",
        "claude-opus-4",
    ),
    (
        re.compile(r"\bclaude[\s\-_]+(?:sonnet[\s\-_]+4|4[\s\-_]+sonnet)(?![._\-]\d)\b", re.IGNORECASE),
        "claude-4",
        "claude-sonnet-4",
    ),
    (
        re.compile(r"\bclaude[\s\-_]+(?:3[._\-]7[\s\-_]+sonnet|sonnet[\s\-_]+3[._\-]7)\b", re.IGNORECASE),
        "claude-3.7",
        "claude-3-7-sonnet",
    ),
    (
        re.compile(r"\bclaude[\s\-_]+(?:3[._\-]5[\s\-_]+sonnet|sonnet[\s\-_]+3[._\-]5)\b", re.IGNORECASE),
        "claude-3.5",
        "claude-3-5-sonnet",
    ),
    (re.compile(r"\bgpt[\s\-_]+oss[\s\-_]+120b\b", re.IGNORECASE), "gpt-oss", "gpt-oss-120b"),
)


@dataclass(frozen=True)
class CanonicalModelInfo:
    """Normalized model taxonomy and context attribution metadata."""

    family: str
    canonical_model: str
    reasoning_effort: Optional[str]
    context_window_tokens: int
    attribution_status: str  # "attributed" | "unattributed_legacy" | "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """Serializes model attribution metadata to a plain dictionary."""
        return asdict(self)


def normalize_utc_iso(ts: Optional[str]) -> Optional[str]:
    """Deterministically normalizes ISO-8601 strings to UTC 'YYYY-MM-DDTHH:MM:SSZ'.

    Returns None on None or empty/whitespace-only strings. Preserves unparseable
    non-empty strings verbatim (stripped) rather than discarding data silently.
    """
    if ts is None:
        return None
    if not isinstance(ts, str):
        ts = str(ts)
    cleaned = ts.strip()
    if not cleaned:
        return None

    iso_cand = cleaned[:-1] + "+00:00" if cleaned[-1] in ("Z", "z") else cleaned
    try:
        dt = datetime.fromisoformat(iso_cand)
    except ValueError:
        return cleaned

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_reasoning_effort(*candidates: Optional[str]) -> Optional[str]:
    for cand in candidates:
        if not cand:
            continue
        m = _EFFORT_RE.search(cand)
        if m:
            tok = re.sub(r"[\s\-_]+", "", m.group(1).lower())
            if tok in ("extrahigh", "xhigh"):
                return "xhigh"
            if tok == "med":
                return "medium"
            return tok
        if re.search(r"-h$", cand.strip(), re.IGNORECASE):
            return "high"
    return None


def _is_legacy_placeholder(text: str) -> bool:
    lower = text.strip().lower()
    if not lower:
        return False
    return "flash/pro" in lower or "(default)" in lower or "3.5/flash" in lower


def _refine_variant_suffix(base_canonical: str, text: str) -> str:
    lower = text.lower()
    if base_canonical in ("gemini-3.7", "gemini-3.6", "gemini-3.5", "gemini-3.1", "gemini-3", "gemini-2.5"):
        if "flash" in lower:
            return f"{base_canonical}-flash"
        if "pro" in lower:
            return f"{base_canonical}-pro"
        if "ultra" in lower:
            return f"{base_canonical}-ultra"
    return base_canonical


def normalize_model(
    raw_model: Optional[str],
    model_slug: Optional[str] = None,
    model_display_name: Optional[str] = None,
) -> CanonicalModelInfo:
    """Maps raw model strings, slugs, and display names into canonical model taxonomy."""
    cleaned = [
        val.strip()
        for val in (model_slug, raw_model, model_display_name)
        if isinstance(val, str) and val.strip()
    ]
    effort = _extract_reasoning_effort(model_slug, model_display_name, raw_model)

    if not cleaned:
        return CanonicalModelInfo(
            family="unknown",
            canonical_model="unknown",
            reasoning_effort=None,
            context_window_tokens=DEFAULT_CONTEXT_WINDOW_TOKENS,
            attribution_status="unknown",
        )

    non_placeholder = [
        c for c in cleaned
        if c.lower() not in _UNKNOWN_SENTINELS and not _is_legacy_placeholder(c)
    ]

    if not non_placeholder:
        if any(_is_legacy_placeholder(c) for c in cleaned):
            return CanonicalModelInfo(
                family="legacy",
                canonical_model="unattributed_legacy",
                reasoning_effort=None,
                context_window_tokens=DEFAULT_CONTEXT_WINDOW_TOKENS,
                attribution_status="unattributed_legacy",
            )
        return CanonicalModelInfo(
            family="unknown",
            canonical_model="unknown",
            reasoning_effort=None,
            context_window_tokens=DEFAULT_CONTEXT_WINDOW_TOKENS,
            attribution_status="unknown",
        )

    for cand in non_placeholder:
        for pat, family, canonical in _MODEL_RULES:
            if pat.search(cand):
                refined = _refine_variant_suffix(canonical, cand)
                ctx_win = infer_model_context_window(cand)
                if ctx_win == DEFAULT_CONTEXT_WINDOW_TOKENS:
                    for other in non_placeholder:
                        alt_win = infer_model_context_window(other)
                        if alt_win != DEFAULT_CONTEXT_WINDOW_TOKENS:
                            ctx_win = alt_win
                            break
                return CanonicalModelInfo(
                    family=family,
                    canonical_model=refined,
                    reasoning_effort=effort,
                    context_window_tokens=ctx_win,
                    attribution_status="attributed",
                )

    primary = non_placeholder[0]
    lower_primary = primary.lower()
    if lower_primary.startswith("claude"):
        slug = re.sub(r"[^a-z0-9._-]+", "-", lower_primary).strip("-")
        return CanonicalModelInfo(
            family="claude",
            canonical_model=slug or "claude",
            reasoning_effort=effort,
            context_window_tokens=infer_model_context_window(primary),
            attribution_status="attributed",
        )
    if re.match(r"^gpt-[45]\b", lower_primary):
        slug = re.sub(r"[^a-z0-9._-]+", "-", lower_primary).strip("-")
        fam = "gpt-5" if lower_primary.startswith("gpt-5") else "gpt-4"
        return CanonicalModelInfo(
            family=fam,
            canonical_model=slug or fam,
            reasoning_effort=effort,
            context_window_tokens=infer_model_context_window(primary),
            attribution_status="attributed",
        )

    fallback_slug = re.sub(r"[^a-z0-9._-]+", "-", lower_primary).strip("-")
    return CanonicalModelInfo(
        family="unknown",
        canonical_model=fallback_slug or "unknown",
        reasoning_effort=effort,
        context_window_tokens=infer_model_context_window(primary),
        attribution_status="unknown",
    )


__all__ = [
    "CanonicalModelInfo",
    "normalize_model",
    "normalize_utc_iso",
]
