# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Zero-Token Subagent Context Estimator & Health Gauge (ADR-025).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import time
from typing import List, Optional, Tuple

from harness.utils.tokens import estimate_tokens


@dataclass(frozen=True)
class SubagentContextStatus:
    """Zero-token context status and health gauge for a subagent."""

    conversation_id: str
    role: str
    step_count: int
    token_count: int
    health_zone: str  # "HEALTHY" | "AMBER" | "RED_ALERT"
    recommendation: str  # "REUSE" | "COMPACT_RECREATE" | "RETIRE"
    latency_ms: float


def classify_context_health(token_count: int, step_count: int) -> Tuple[str, str]:
    """Classify context health into (health_zone, recommendation) based on ADR-025 thresholds."""
    if token_count > 80_000 or step_count > 80:
        return "RED_ALERT", "RETIRE"
    elif token_count >= 40_000 or step_count >= 40:
        return "AMBER", "COMPACT_RECREATE"
    else:
        return "HEALTHY", "REUSE"


def extract_role_from_text(text: str) -> Optional[str]:
    """Extract subagent role from prompt text or content."""
    if not text or not isinstance(text, str):
        return None
    if "continuing work" in text or "resuming work" in text:
        return None
    m_bracket = re.search(r"<([A-Za-z0-9_\s\-]+)\s*\([A-Za-z0-9_\s\-]+\)>", text)
    if m_bracket:
        return m_bracket.group(1).strip()
    m_stage = re.search(r"You are\s+(?:the\s+)?(Stage\s+\d+\s+[A-Za-z0-9_]+)", text)
    if m_stage:
        return m_stage.group(1).strip()
    m = re.search(
        r"You are\s+(?:a\s+|an\s+|the\s+)?['`\"]?([A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*)['`\"]?", text
    )
    if m:
        cand = m.group(1).strip()
        if cand.lower() not in ("a", "an", "the", "now", "here"):
            return cand
    return None


def estimate_subagent_context(transcript_path: Path | str) -> SubagentContextStatus:
    """
    Estimate subagent context window consumption and health gauge with zero LLM tokens.

    Uses exact JSON streaming (<1ms) for transcripts <=2MB.
    Falls back to fast size-stat heuristic (<0.05ms) for titan files >2MB.

    Thresholds:
    - <40k tokens & <40 steps: HEALTHY / REUSE
    - 40k-80k tokens or 40-80 steps: AMBER / COMPACT_RECREATE
    - >80k tokens or >80 steps: RED_ALERT / RETIRE
    """
    t0 = time.perf_counter()
    p = Path(transcript_path)

    if not p.is_file():
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return SubagentContextStatus(
            conversation_id="unknown",
            role="unknown",
            step_count=0,
            token_count=0,
            health_zone="HEALTHY",
            recommendation="REUSE",
            latency_ms=latency_ms,
        )

    try:
        file_size = p.stat().st_size
    except OSError:
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return SubagentContextStatus(
            conversation_id="unknown",
            role="unknown",
            step_count=0,
            token_count=0,
            health_zone="HEALTHY",
            recommendation="REUSE",
            latency_ms=latency_ms,
        )

    # Derive candidate conversation_id from path
    candidate_id = "unknown"
    parts = p.parts
    if ".system_generated" in parts:
        idx = parts.index(".system_generated")
        if idx > 0:
            candidate_id = parts[idx - 1]
    elif p.parent.name and p.stem in ("transcript", "transcript_full"):
        candidate_id = p.parent.name
    elif p.stem not in ("transcript", "transcript_full"):
        candidate_id = p.stem

    detected_role = ""
    detected_id = ""

    # Size-heuristic fallback for runaway / titan files (>2MB)
    if file_size > 2 * 1024 * 1024:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                sample = f.read(8192)
                line1 = sample.split("\n", 1)[0]
                try:
                    obj1 = json.loads(line1)
                    if isinstance(obj1, dict):
                        detected_id = (
                            obj1.get("conversation_id")
                            or obj1.get("conversationId")
                            or ""
                        )
                        raw_role = obj1.get("role") or obj1.get("Role") or ""
                        if str(raw_role).strip().lower() in ("user", "assistant", "system", "tool", "model"):
                            raw_role = ""
                        detected_role = (
                            raw_role
                            or extract_role_from_text(str(obj1.get("content") or ""))
                            or ""
                        )
                except (json.JSONDecodeError, ValueError, KeyError, TypeError):
                    pass

                if not detected_id:
                    m_id = re.search(r'"conversation(?:_i|I)d":\s*"([^"]+)"', sample)
                    if m_id:
                        detected_id = m_id.group(1).strip()
                if not detected_role:
                    detected_role = extract_role_from_text(sample) or ""
        except OSError:
            pass

        token_count = max(1, file_size // 4)
        step_count = max(1, file_size // 1400)
        final_id = detected_id or candidate_id
        final_role = detected_role or "subagent"
        health_zone, rec = classify_context_health(token_count, step_count)
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return SubagentContextStatus(
            conversation_id=final_id,
            role=final_role,
            step_count=step_count,
            token_count=token_count,
            health_zone=health_zone,
            recommendation=rec,
            latency_ms=latency_ms,
        )

    # Exact JSON streaming for <= 2MB
    step_count = 0
    total_chars = 0
    explicit_tokens = 0

    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                step_count += 1
                try:
                    obj = json.loads(line_str)
                    if isinstance(obj, dict):
                        if not detected_id:
                            detected_id = (
                                obj.get("conversation_id")
                                or obj.get("conversationId")
                                or ""
                            )
                        if not detected_role:
                            raw_role = obj.get("role") or obj.get("Role") or ""
                            if str(raw_role).strip().lower() in ("user", "assistant", "system", "tool", "model"):
                                raw_role = ""
                            detected_role = (
                                raw_role
                                or extract_role_from_text(str(obj.get("content") or ""))
                                or ""
                            )

                        if "token_count" in obj or "tokens" in obj:
                            val = obj.get("token_count") or obj.get("tokens") or 0
                            if isinstance(val, (int, float)):
                                explicit_tokens += int(val)

                        content = obj.get("content") or ""
                        thinking = obj.get("thinking") or ""
                        chars = len(content) + len(thinking)
                        if chars == 0:
                            chars = len(line_str)
                        total_chars += chars
                except (json.JSONDecodeError, ValueError):
                    total_chars += len(line_str)
    except OSError:
        pass

    if explicit_tokens > 0:
        token_count = explicit_tokens
    else:
        token_count = estimate_tokens(total_chars)

    final_id = detected_id or candidate_id
    final_role = detected_role or "subagent"
    health_zone, rec = classify_context_health(token_count, step_count)
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)

    return SubagentContextStatus(
        conversation_id=final_id,
        role=final_role,
        step_count=step_count,
        token_count=token_count,
        health_zone=health_zone,
        recommendation=rec,
        latency_ms=latency_ms,
    )


def list_active_subagent_statuses(
    brain_dir: Optional[Path] = None,
) -> List[SubagentContextStatus]:
    """
    Discover active subagents in brain directory and report their context health statuses.
    """
    b_dir = brain_dir or Path(
        os.environ.get(
            "ANTIGRAVITY_BRAIN_DIR",
            os.environ.get(
                "GEMINI_BRAIN_DIR", Path.home() / ".gemini" / "antigravity" / "brain"
            ),
        )
    )
    if not b_dir.exists() or not b_dir.is_dir():
        return []

    subagent_statuses: List[SubagentContextStatus] = []
    seen_ids: set[str] = set()

    # When brain_dir is provided (e.g. test fixtures), check all session directories
    if brain_dir is not None:
        for item in sorted(b_dir.iterdir()):
            if not item.is_dir() or item.name.startswith("."):
                continue
            t_path = item / ".system_generated" / "logs" / "transcript.jsonl"
            if not t_path.is_file():
                t_path = item / "transcript.jsonl"
            if not t_path.is_file():
                continue

            status = estimate_subagent_context(t_path)
            if status.conversation_id not in seen_ids:
                seen_ids.add(status.conversation_id)
                subagent_statuses.append(status)
        return subagent_statuses

    # In production/default brain_dir, scan recent sessions active in the last 4 hours
    try:
        entries = [
            e
            for e in os.scandir(b_dir)
            if e.is_dir() and not e.name.startswith(".")
        ]
        entries.sort(key=lambda e: e.stat().st_mtime, reverse=True)
    except OSError:
        return []

    now = time.time()
    for entry in entries:
        try:
            # Sorted by mtime descending: stop scanning once older than 4 hours
            if now - entry.stat().st_mtime > 14400:
                break

            s_path = Path(entry.path)
            t_path = s_path / ".system_generated" / "logs" / "transcript.jsonl"
            if not t_path.is_file():
                t_path = s_path / "transcript.jsonl"
            if not t_path.is_file():
                continue

            with open(t_path, "r", encoding="utf-8", errors="replace") as f:
                line0 = f.readline()
                if (
                    "You are " in line0
                    or "<subagent_reminder>" in line0
                    or '"role"' in line0
                    or '"Role"' in line0
                ):
                    status = estimate_subagent_context(t_path)
                    if status.conversation_id not in seen_ids:
                        seen_ids.add(status.conversation_id)
                        subagent_statuses.append(status)
        except OSError:
            pass

    return subagent_statuses
