# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Shared Orbital Aegis CLI theme, color detection, and display-width primitives (Stream B3).

Pure standard-library leaf module with zero internal harness imports so every
CLI command, runtime check, and hook can render consistent, NO_COLOR-safe,
display-width-aligned terminal output.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import unicodedata
from typing import Any, Dict, Optional, Sequence, Tuple

# Orbital Aegis token registry: (hex, (r, g, b), xterm256, bold_default)
TOKENS: Dict[str, Tuple[str, Tuple[int, int, int], int, bool]] = {
    "bg": ("#080E1A", (8, 14, 26), 232, False),
    "surface": ("#10192B", (16, 25, 43), 234, False),
    "elevated": ("#162238", (22, 34, 56), 235, False),
    "border": ("#4A5D7A", (74, 93, 122), 240, False),
    "ink": ("#F4F6FA", (244, 246, 250), 255, True),
    "muted": ("#9AA8BE", (154, 168, 190), 103, False),
    "cobalt": ("#1B4DFF", (27, 77, 255), 27, False),
    "optical": ("#5C8AFF", (92, 138, 255), 69, False),
    "cyan": ("#26D0CE", (38, 208, 206), 44, False),
    "pass": ("#2AD089", (42, 208, 137), 42, False),
    "warn": ("#F5B74F", (245, 183, 79), 214, False),
    "fail": ("#FF6B6B", (255, 107, 107), 203, False),
}

GLYPHS: Dict[str, str] = {
    "BRAND": "◆",
    "PASS": "●",
    "WARN": "▲",
    "FAIL": "✕",
    "INFO": "○",
    "ARROW": "▸",
    "RULE_HEAVY": "━",
    "RULE_LIGHT": "─",
}

_ROLE_MAP: Dict[str, Tuple[str, str]] = {
    "PASS": ("●", "pass"),
    "OK": ("●", "pass"),
    "HEALTHY": ("●", "pass"),
    "ACTIVE": ("●", "pass"),
    "CLEAN": ("●", "pass"),
    "SAFE": ("●", "pass"),
    "SUCCESS": ("●", "pass"),
    "COMPLETED": ("◆", "pass"),
    "DONE": ("◆", "pass"),
    "WARN": ("▲", "warn"),
    "WARNING": ("▲", "warn"),
    "AMBER": ("▲", "warn"),
    "STALE": ("▲", "warn"),
    "DIRTY": ("▲", "warn"),
    "ELEVATED": ("▲", "warn"),
    "UNKN": ("▲", "warn"),
    "UNKNOWN_VERSION": ("▲", "warn"),
    "NOTICE": ("▲", "warn"),
    "FAIL": ("✕", "fail"),
    "ERROR": ("✕", "fail"),
    "CRITICAL": ("✕", "fail"),
    "DEAD": ("✕", "fail"),
    "OUTDATED": ("✕", "fail"),
    "MISSING": ("✕", "fail"),
    "MISS": ("✕", "fail"),
    "RED_ALERT": ("✕", "fail"),
    "INFO": ("○", "optical"),
    "OPTICAL": ("○", "optical"),
    "SKIP": ("○", "muted"),
    "PARKED": ("○", "muted"),
    "STOPPED": ("○", "muted"),
    "PENDING": ("○", "muted"),
    "MUTED": ("○", "muted"),
    "DIM": ("○", "muted"),
    "BRAND": ("◆", "cobalt"),
    "COBALT": ("◆", "cobalt"),
    "CYAN": ("◆", "cyan"),
    "INK": ("◆", "ink"),
    "BORDER": ("─", "border"),
}

_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;?]*[A-Za-z]|\][^\x07\x1b]*(?:\x07|\x1b\\))")
_ZERO_WIDTH_CODEPOINTS = frozenset(("\u200d", "\ufe0e", "\ufe0f"))


def use_color(stream: Any = None) -> bool:
    """Return True when ANSI SGR color should be emitted for the target stream."""
    if os.environ.get("NO_COLOR", "") != "":
        return False
    if os.environ.get("TERM", "").strip().lower() == "dumb":
        return False
    for env_key in ("FORCE_COLOR", "CLICOLOR_FORCE"):
        val = os.environ.get(env_key)
        if val is not None and val.strip().lower() not in ("", "0", "false", "no"):
            return True
    target = sys.stdout if stream is None else stream
    isatty = getattr(target, "isatty", None)
    return bool(callable(isatty) and isatty())


def supports_truecolor() -> bool:
    """Return True when the active terminal advertises 24-bit TrueColor support."""
    return os.environ.get("COLORTERM", "").strip().lower() in ("truecolor", "24bit")


def strip_ansi(text: str) -> str:
    """Remove ANSI CSI/OSC escape sequences from text."""
    return _ANSI_RE.sub("", str(text))


def display_width(text: str) -> int:
    """Compute visible terminal column width after stripping ANSI and zero-width marks."""
    clean = strip_ansi(text)
    total = 0
    for ch in clean:
        if ch in _ZERO_WIDTH_CODEPOINTS or unicodedata.combining(ch):
            continue
        if unicodedata.category(ch) in ("Cc", "Cf", "Mn", "Me"):
            continue
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def pad_display(text: str, width: int, align: str = "left") -> str:
    """Pad text to visible terminal column width regardless of ANSI or wide glyphs."""
    raw = str(text)
    pad = max(0, width - display_width(raw))
    if align == "right":
        return (" " * pad) + raw
    if align == "center":
        left = pad // 2
        return (" " * left) + raw + (" " * (pad - left))
    return raw + (" " * pad)


def style(
    text: str,
    role: str = "ink",
    *,
    bold: Optional[bool] = None,
    stream: Any = None,
    color: Optional[bool] = None,
) -> str:
    """Apply Orbital Aegis SGR foreground styling if color output is active."""
    raw = str(text)
    enabled = use_color(stream) if color is None else bool(color)
    if not enabled or not raw:
        return raw

    token_key = role.strip().lower()
    if token_key not in TOKENS:
        token_key = _ROLE_MAP.get(role.strip().upper(), ("◆", "ink"))[1]
    _, (r, g, b), idx256, default_bold = TOKENS[token_key]
    use_bold = default_bold if bold is None else bold
    prefix = "1;" if use_bold else ""
    if supports_truecolor():
        return f"\033[{prefix}38;2;{r};{g};{b}m{raw}\033[0m"
    if token_key == "ink" and use_bold:
        return f"\033[1;37m{raw}\033[0m"
    return f"\033[{prefix}38;5;{idx256}m{raw}\033[0m"


def term_width(min_w: int = 64, max_w: int = 88) -> int:
    """Return clamped responsive terminal column width in [min_w, max_w]."""
    cols = shutil.get_terminal_size((76, 24)).columns
    return max(min_w, min(max_w, cols))


def rule(
    char: str = "─",
    width: Optional[int] = None,
    stream: Any = None,
    role: str = "muted",
) -> str:
    """Render a muted divider rule sized to the clamped terminal width."""
    resolved_w = width if width is not None else term_width()
    line = (char or "─") * max(1, resolved_w)
    return style(line, role, bold=False, stream=stream)


def badge(
    kind: str,
    text: Optional[str] = None,
    *,
    stream: Any = None,
    bracketed: bool = False,
) -> str:
    """Render a single-width geometric status badge or bracketed machine label."""
    key = str(kind).strip().upper()
    glyph, role = _ROLE_MAP.get(key, ("○", "optical"))
    if bracketed:
        label = str(key if text is None else text)
        return f"[{style(label, role, bold=True, stream=stream)}]"
    mark = style(glyph, role, bold=False, stream=stream)
    if text is None or text == "":
        return mark
    return f"{mark} {style(str(text), role, bold=False, stream=stream)}"


def banner(
    title: str,
    subtitle: Optional[str] = None,
    badge_label: Optional[str] = None,
    status: str = "brand",
    *,
    stream: Any = None,
    width: Optional[int] = None,
) -> str:
    """Render a double-weight Orbital Aegis header banner block."""
    w = width if width is not None else term_width()
    heavy = rule("━", width=w, stream=stream, role="muted")
    _, role = _ROLE_MAP.get(status.strip().upper(), ("◆", "cobalt"))
    mark = style(GLYPHS["BRAND"], "optical" if role == "cobalt" else role, bold=True, stream=stream)
    title_str = style(title, "ink", bold=True, stream=stream)
    head = f" {mark} {title_str}"
    if badge_label:
        clean_lbl = badge_label.strip("[]")
        head = f"{head} {badge(status, clean_lbl, stream=stream, bracketed=True)}"
    lines = [heavy, head]
    if subtitle:
        lines.append(f"   {style(subtitle, 'muted', bold=False, stream=stream)}")
    lines.append(heavy)
    return "\n".join(lines)


def status_line(
    label: str,
    detail: str = "",
    status: str = "INFO",
    *,
    stream: Any = None,
    label_width: int = 0,
    bracketed: bool = False,
) -> str:
    """Render a single-line status row with an aligned geometric or bracketed badge."""
    mark = badge(status, status.upper() if bracketed else None, stream=stream, bracketed=bracketed)
    lbl = pad_display(label, label_width) if label_width > 0 else str(label)
    return f"  {mark} {lbl} {detail}".rstrip() if detail else f"  {mark} {lbl}"


def format_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    stream: Any = None,
    alignments: Optional[Sequence[str]] = None,
) -> str:
    """Render an aligned box table whose visual line widths match under color and Unicode."""
    col_count = len(headers)
    col_widths = [display_width(str(h)) for h in headers]
    str_rows = [[str(cell) for cell in row] for row in rows]
    for row in str_rows:
        for i in range(min(col_count, len(row))):
            col_widths[i] = max(col_widths[i], display_width(row[i]))

    def _align_for(idx: int) -> str:
        if alignments and idx < len(alignments):
            return alignments[idx]
        return "left"

    sep_raw = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    sep = style(sep_raw, "border", bold=False, stream=stream)
    bar = style("│", "border", bold=False, stream=stream)

    header_cells = [
        style(pad_display(str(h), col_widths[i], _align_for(i)), "ink", bold=True, stream=stream)
        for i, h in enumerate(headers)
    ]
    header_line = f"{bar} " + f" {bar} ".join(header_cells) + f" {bar}"

    lines = [sep, header_line, sep]
    for row in str_rows:
        padded = [
            pad_display(row[i] if i < len(row) else "", col_widths[i], _align_for(i))
            for i in range(col_count)
        ]
        lines.append(f"{bar} " + f" {bar} ".join(padded) + f" {bar}")
    lines.append(sep)
    return "\n".join(lines)
