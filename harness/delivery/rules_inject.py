# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workspace AGENTS.md rendering, YAML frontmatter stripping, stack-aware CLI filtering,
Prettier-clean Markdown normalization, and custom section relocation (WS1).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import List, Optional, Tuple

TAG_START = "<!-- Added by AGYIS-HARNESS -->"
TAG_END = "<!-- End AGYIS-HARNESS -->"
LEGACY_TAG_START = "<!-- Added by PSL-HARNESS -->"
LEGACY_TAG_END = "<!-- End PSL-HARNESS -->"

TAGGED_BLOCK_PATTERN = re.compile(
    r"<!-- Added by (?:AGYIS-HARNESS|PSL-HARNESS) -->[\s\S]*?<!-- End (?:AGYIS-HARNESS|PSL-HARNESS) -->"
)

PLUGIN_INHERITANCE_POINTER = (
    "> Inherits universal invariants PSL-INV-001 through PSL-INV-008 "
    "from the active global Agyis plugin rules."
)

_PYTHON_SKIP_DIRS = frozenset({
    "node_modules",
    ".git",
    "venv",
    ".venv",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".dirtyroom",
})

_STANDARD_HEADING_KEYWORDS = (
    "explicit project command dictionary",
    "project command dictionary",
    "empirical verification",
    "epistemic honesty",
    "tool determinism",
    "context signal hygiene",
    "risk-scaled planning",
    "independent verification",
    "live reality over static fakes",
    "architectural fitness",
    "sovereign boundaries",
    "product vs. project bifurcation",
    "clean-room testing",
    "cleanroom re & pre-analyzed ghidra",
    "universal automated verification standard",
    "terminal invariants",
    "surgical contiguous edits",
    "context preservation",
    "artifact-first planning",
    "human-in-the-loop",
    "cleanroom reverse engineering",
    "cockpit flight direction",
    "pre-analyzed decompiler cache",
    "anti-vibe-coding",
    "universal architectural fitness invariant",
    "agyis harness workspace rules",
    "agyis harness command dictionary",
)

_STRAY_MARKER_HEADING_RE = re.compile(
    r"(?m)^#{1,6}[ \t]*(<!--\s*(?:Added by|End)\s+(?:AGYIS|PSL)-HARNESS\s*-->)[ \t]*$"
)
_MARKER_NORMALIZE_RE = re.compile(
    r"(?m)^[ \t]*<!--\s*(Added by|End)\s+(AGYIS|PSL)-HARNESS\s*-->[ \t]*$"
)
_UNCLOSED_MARKER_RE = re.compile(
    r"(?m)^[ \t]*<!--\s*(?:Added by|End)\s+(?:AGYIS|PSL)-HARNESS\s*-->[ \t]*\n?"
)
_VERIFY_CMD_RE = re.compile(r"^[ \t]*agyis\s+verify(?:\s+--spec)?(?:\s+#|\s*$)")
_AFF_CMD_RE = re.compile(r"^[ \t]*agyis\s+audit\s+aff(?:\s+#|\s*$)")
_FENCE_OPEN_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_YAML_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+\s*:")
_ITALICS_SEGMENT_RE = re.compile(r"(?<![*\\])\*([^\s*][^*\n]*?[^\s*]|[^\s*])\*(?!\*)")


def strip_yaml_frontmatter(text: str) -> str:
    """Strips leading YAML frontmatter (`---\\n...\\n---`) without touching Markdown horizontal rules."""
    if not text:
        return ""
    norm = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    match = re.match(
        r"^[ \t]*(?:\n[ \t]*)*---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)",
        norm,
        flags=re.DOTALL,
    )
    if not match:
        return norm
    fm_lines = match.group(1).splitlines()
    if not any(_YAML_KEY_RE.match(line) for line in fm_lines):
        return norm
    return norm[match.end() :].lstrip("\n")


def _workspace_has_python_source(workspace_dir: Path) -> bool:
    """Returns True if workspace_dir contains pyproject.toml or non-ignored .py files."""
    if not workspace_dir.is_dir():
        return False
    if (workspace_dir / "pyproject.toml").is_file():
        return True
    try:
        for _, dirs, files in os.walk(workspace_dir):
            dirs[:] = [
                d for d in dirs if d not in _PYTHON_SKIP_DIRS and not d.startswith(".")
            ]
            if any(fname.endswith(".py") for fname in files):
                return True
    except OSError:
        return False
    return False


def _workspace_has_rea_or_specs(workspace_dir: Path, rea_enabled: bool = False) -> bool:
    """Returns True when docs/specs, .agents/ledger, explicit flag, or workspace REA config is active."""
    if rea_enabled:
        return True
    if (workspace_dir / "docs" / "specs").is_dir() or (
        workspace_dir / ".agents" / "ledger"
    ).is_dir():
        return True
    for rel in (".agyis/config.json", ".psl/config.json"):
        cfg = workspace_dir / rel
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, dict) and bool(
                    data.get("rea") or data.get("experimental_rea")
                ):
                    return True
            except (OSError, ValueError, TypeError):
                pass
    return False


def _is_standard_heading(heading_line: str) -> bool:
    """Returns True if a level-2 Markdown heading matches canonical PSL/AGYIS sections."""
    lower = heading_line.lstrip("#").strip().lower()
    if "(psl-inv-" in lower or "(psl-re-" in lower:
        return True
    if "psl harness guidelines" in lower or "agyis harness guidelines" in lower:
        return True
    return any(kw in lower for kw in _STANDARD_HEADING_KEYWORDS)


def _split_level2_sections(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Splits Markdown into (preamble, [(heading_line, section_text), ...]) ignoring code fences."""
    lines = text.splitlines()
    preamble_lines: List[str] = []
    sections: List[Tuple[str, List[str]]] = []
    in_fence_char: Optional[str] = None
    fence_len = 0

    for line in lines:
        fence_m = _FENCE_OPEN_RE.match(line)
        if fence_m:
            marker = fence_m.group(1)
            if in_fence_char is None:
                in_fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == in_fence_char and len(marker) >= fence_len and line.strip() == marker:
                in_fence_char = None
                fence_len = 0
        elif in_fence_char is None and re.match(r"^##(?!#)\s+\S", line):
            sections.append((line.strip(), [line]))
            continue

        if sections:
            sections[-1][1].append(line)
        else:
            preamble_lines.append(line)

    return "\n".join(preamble_lines), [
        (heading, "\n".join(sec_lines)) for heading, sec_lines in sections
    ]


def _convert_inline_italics(line: str) -> str:
    """Converts *text* italics to _text_ outside inline code spans and bullet markers."""
    list_prefix = ""
    rest = line
    bullet_m = re.match(r"^([ \t]*\*[ \t]+)(.*)$", line)
    if bullet_m:
        list_prefix = bullet_m.group(1)
        rest = bullet_m.group(2)

    parts = re.split(r"(`+[^`]*`+)", rest)
    for idx in range(0, len(parts), 2):
        parts[idx] = _ITALICS_SEGMENT_RE.sub(r"_\1_", parts[idx])
    return list_prefix + "".join(parts)


def normalize_prettier_markdown(text: str) -> str:
    """Normalizes Markdown into Prettier-clean format (blank lines around blocks, _italics_, LF)."""
    if not text or not text.strip():
        return ""
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    norm = _STRAY_MARKER_HEADING_RE.sub(r"\1", norm)

    raw_lines = [line.rstrip(" \t") for line in norm.split("\n")]
    out: List[str] = []
    in_fence_char: Optional[str] = None
    fence_len = 0
    in_comment = False

    def ensure_blank_before() -> None:
        if out and out[-1] != "":
            out.append("")

    for idx, line in enumerate(raw_lines):
        stripped = line.strip()

        if in_fence_char is not None:
            out.append(line)
            fence_m = _FENCE_OPEN_RE.match(line)
            if (
                fence_m
                and fence_m.group(1)[0] == in_fence_char
                and len(fence_m.group(1)) >= fence_len
                and stripped == fence_m.group(1)
            ):
                in_fence_char = None
                fence_len = 0
                if idx + 1 < len(raw_lines) and raw_lines[idx + 1].strip():
                    out.append("")
            continue

        if in_comment:
            out.append(line)
            if "-->" in line:
                in_comment = False
                if idx + 1 < len(raw_lines) and raw_lines[idx + 1].strip():
                    out.append("")
            continue

        fence_m = _FENCE_OPEN_RE.match(line)
        if fence_m:
            ensure_blank_before()
            in_fence_char = fence_m.group(1)[0]
            fence_len = len(fence_m.group(1))
            out.append(line)
            continue

        if stripped.startswith("<!--"):
            ensure_blank_before()
            out.append(line)
            if "-->" in stripped:
                if idx + 1 < len(raw_lines) and raw_lines[idx + 1].strip():
                    out.append("")
            else:
                in_comment = True
            continue

        if re.match(r"^#{1,6}[ \t]+\S", line):
            ensure_blank_before()
            out.append(_convert_inline_italics(line))
            if idx + 1 < len(raw_lines) and raw_lines[idx + 1].strip():
                out.append("")
            continue

        if re.match(r"^---+$", stripped):
            ensure_blank_before()
            out.append("---")
            if idx + 1 < len(raw_lines) and raw_lines[idx + 1].strip():
                out.append("")
            continue

        if stripped.startswith(">"):
            prev_non_quote = bool(out and out[-1] != "" and not out[-1].lstrip().startswith(">"))
            if prev_non_quote:
                out.append("")
            out.append(_convert_inline_italics(line))
            next_line = raw_lines[idx + 1].strip() if idx + 1 < len(raw_lines) else ""
            if next_line and not next_line.startswith(">"):
                out.append("")
            continue

        if stripped == "":
            if out and out[-1] != "":
                out.append("")
            continue

        out.append(_convert_inline_italics(line))

    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    if not out:
        return ""
    return "\n".join(out) + "\n"


def filter_universal_rules_for_workspace(
    template_text: str,
    workspace_dir: Path | str,
    stacks: list[str] | None = None,
    rea_enabled: bool = False,
) -> str:
    """Filters universal rule template for a target workspace (no frontmatter, stack-gated CLIs)."""
    ws = Path(workspace_dir).resolve()
    cleaned = strip_yaml_frontmatter(template_text)
    if not cleaned.strip():
        return ""

    include_verify = _workspace_has_rea_or_specs(ws, rea_enabled=rea_enabled)
    has_py_stack = stacks is not None and any(
        str(s).strip().lower() == "python" for s in stacks
    )
    include_aff = has_py_stack or _workspace_has_python_source(ws)

    # Strip any legacy duplicated universal rule sections if an un-slimmed template was supplied
    preamble, sections = _split_level2_sections(cleaned)
    stripped_universal = False
    if sections:
        kept_sections: List[str] = []
        for heading, sec_text in sections:
            lower_h = heading.lower()
            is_cmd_dict = "command dictionary" in lower_h
            if not is_cmd_dict and _is_standard_heading(heading):
                stripped_universal = True
                continue
            kept_sections.append(sec_text)

        if stripped_universal:
            preamble_lines = [
                ln
                for ln in preamble.splitlines()
                if "Universal Empirical Agent Rules: PSL Invariant Codex v2" not in ln
                and "These operational rules govern cognitive behavior" not in ln
                and not re.match(r"^---+$", ln.strip())
            ]
            preamble_clean = "\n".join(preamble_lines).strip()
            if PLUGIN_INHERITANCE_POINTER not in preamble_clean and not any(
                PLUGIN_INHERITANCE_POINTER in s for s in kept_sections
            ):
                preamble_clean = (
                    f"{preamble_clean}\n\n{PLUGIN_INHERITANCE_POINTER}".strip()
                )
            parts = [p for p in [preamble_clean, *kept_sections] if p.strip()]
            cleaned = "\n\n".join(parts)

    # Filter conditional CLI commands & remove duplicate PSL-RE-001 global footer echoes
    filtered_lines: List[str] = []
    in_fence_char: Optional[str] = None
    fence_len = 0

    for line in cleaned.splitlines():
        fence_m = _FENCE_OPEN_RE.match(line)
        if fence_m:
            marker = fence_m.group(1)
            if in_fence_char is None:
                in_fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == in_fence_char and len(marker) >= fence_len and line.strip() == marker:
                in_fence_char = None
                fence_len = 0
                while filtered_lines and filtered_lines[-1].strip() == "":
                    filtered_lines.pop()
            filtered_lines.append(line)
            continue

        if in_fence_char is None:
            if "On-Demand Domain Pack" in line and "PSL-RE-001" in line:
                continue
            if stripped_universal and re.match(r"^---+$", line.strip()):
                continue
        if not include_verify and _VERIFY_CMD_RE.match(line):
            continue
        if not include_aff and _AFF_CMD_RE.match(line):
            continue

        filtered_lines.append(line)

    return normalize_prettier_markdown("\n".join(filtered_lines))


def relocate_custom_tagged_sections(tagged_inner_body: str) -> tuple[str, list[str]]:
    """Extracts non-standard level-2 (## ...) sections from legacy tagged blocks for relocation."""
    cleaned = strip_yaml_frontmatter(
        tagged_inner_body.replace("\r\n", "\n").replace("\r", "\n")
    )
    preamble, sections = _split_level2_sections(cleaned)

    standard_parts: List[str] = []
    if preamble.strip():
        standard_parts.append(preamble.strip())

    relocated_sections: List[str] = []
    for heading, sec_text in sections:
        if _is_standard_heading(heading):
            standard_parts.append(sec_text.strip())
            continue

        sec_lines = sec_text.splitlines()
        while sec_lines and (
            not sec_lines[-1].strip() or re.match(r"^---+$", sec_lines[-1].strip())
        ):
            sec_lines.pop()
        while sec_lines and not sec_lines[0].strip():
            sec_lines.pop(0)
        formatted = normalize_prettier_markdown("\n".join(sec_lines)).rstrip("\n")
        if formatted:
            relocated_sections.append(formatted)

    return "\n\n".join(standard_parts).strip(), relocated_sections


def _clean_tag_markers(text: str) -> str:
    """Normalizes CRLF, strips heading prefixes on harness markers, and standardizes spacing."""
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    norm = _STRAY_MARKER_HEADING_RE.sub(r"\1", norm)
    return _MARKER_NORMALIZE_RE.sub(
        lambda m: f"<!-- {m.group(1)} {m.group(2)}-HARNESS -->", norm
    )


def _dedup_relocated_against_outside(
    relocated: List[str], outside_text: str
) -> List[str]:
    """Filters out relocated sections whose heading already exists outside the tagged block."""
    kept: List[str] = []
    seen_headings: set[str] = set()
    for sec in relocated:
        sec_clean = sec.strip()
        if not sec_clean:
            continue
        heading_line = sec_clean.splitlines()[0].strip()
        heading_key = heading_line.lower()
        if heading_key in seen_headings:
            continue
        if re.search(rf"(?mi)^{re.escape(heading_line)}[ \t]*$", outside_text):
            continue
        seen_headings.add(heading_key)
        kept.append(sec_clean)
    return kept


def inject_tagged_block_clean(
    existing_content: str,
    block_body: str,
    relocated_sections: list[str] | None = None,
) -> str:
    """Injects block_body inside isolated AGYIS-HARNESS fences and appends relocated sections."""
    normalized = _clean_tag_markers(existing_content or "")
    body_clean = normalize_prettier_markdown(strip_yaml_frontmatter(block_body)).strip()
    tagged_block = (
        f"{TAG_START}\n\n{body_clean}\n\n{TAG_END}"
        if body_clean
        else f"{TAG_START}\n{TAG_END}"
    )

    matches = list(TAGGED_BLOCK_PATTERN.finditer(normalized))

    if relocated_sections is not None:
        raw_relocated = [s.strip() for s in relocated_sections if s and s.strip()]
    else:
        raw_relocated = []
        for m in matches:
            inner = re.sub(
                r"^<!-- Added by (?:AGYIS|PSL)-HARNESS -->[ \t]*\n?", "", m.group(0)
            )
            inner = re.sub(
                r"\n?[ \t]*<!-- End (?:AGYIS|PSL)-HARNESS -->$", "", inner
            )
            _, rel = relocate_custom_tagged_sections(inner)
            raw_relocated.extend(rel)

    if matches:
        before = normalized[: matches[0].start()]
        after_parts: List[str] = []
        for idx, m in enumerate(matches):
            seg_start = m.end()
            seg_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
            segment = normalized[seg_start:seg_end]
            if segment.strip():
                after_parts.append(segment.strip("\n"))
        after = "\n\n".join(after_parts)

        outside_text = f"{before}\n{after}"
        dedup_relocated = _dedup_relocated_against_outside(raw_relocated, outside_text)
        replacement = tagged_block
        if dedup_relocated:
            replacement = f"{tagged_block}\n\n" + "\n\n".join(dedup_relocated)

        prefix = f"{before.rstrip(' \t\n')}\n\n" if before.strip() else ""
        suffix = (
            f"\n\n{after.lstrip(' \t\n').rstrip(' \t\n')}\n"
            if after.strip()
            else "\n"
        )
        return prefix + replacement + suffix

    # Strip orphan unclosed harness markers so legacy tags never remain behind
    without_orphans = _UNCLOSED_MARKER_RE.sub("", normalized)
    dedup_relocated = _dedup_relocated_against_outside(raw_relocated, without_orphans)
    replacement = tagged_block
    if dedup_relocated:
        replacement = f"{tagged_block}\n\n" + "\n\n".join(dedup_relocated)

    clean_existing = without_orphans.rstrip(" \t\n")
    if clean_existing:
        return f"{clean_existing}\n\n{replacement}\n"
    return f"{replacement}\n"


def resolve_universal_rules_template(source_dir: Path) -> Optional[Path]:
    """Resolves the universal rules template path from source checkout or plugin directory."""
    candidates = [
        source_dir / "harness" / "rules" / "universal_agents.md",
        source_dir / "rules" / "universal_agents.md",
        source_dir / "rules" / "AGENTS.md",
    ]
    return next((cand for cand in candidates if cand.is_file()), None)


def insert_formatted_commands(block_text: str, formatted_commands: str) -> str:
    """Inserts extracted project commands cleanly at the top of the bash dictionary block."""
    if not formatted_commands:
        return block_text
    if "```bash\n" in block_text:
        return block_text.replace("```bash\n", f"```bash\n{formatted_commands}\n\n", 1)
    if block_text.strip():
        return f"```bash\n{formatted_commands}\n```\n\n{block_text}"
    return f"```bash\n{formatted_commands}\n```\n"


def has_tagged_block(existing_content: str) -> bool:
    """Returns True when existing_content contains a complete AGYIS/PSL harness fence."""
    if not existing_content:
        return False
    return bool(TAGGED_BLOCK_PATTERN.search(_clean_tag_markers(existing_content)))


def build_workspace_rules_block(
    workspace_dir: Path | str,
    source_dir: Path | str,
    formatted_commands: str = "",
    stacks: Optional[List[str]] = None,
    rea_enabled: bool = False,
    fallback_text: Optional[str] = None,
) -> Optional[str]:
    """Resolves, filters, and formats the workspace rules block body."""
    ws = Path(workspace_dir).resolve()
    src = Path(source_dir).resolve()
    template_path = resolve_universal_rules_template(src)
    if template_path is not None:
        raw_text = template_path.read_text(encoding="utf-8")
        filtered = filter_universal_rules_for_workspace(
            raw_text,
            ws,
            stacks=stacks,
            rea_enabled=rea_enabled,
        )
    elif fallback_text is not None:
        filtered = filter_universal_rules_for_workspace(
            fallback_text,
            ws,
            stacks=stacks,
            rea_enabled=rea_enabled,
        )
    else:
        return None
    return insert_formatted_commands(filtered, formatted_commands)
