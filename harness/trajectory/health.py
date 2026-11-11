# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Canonical context window calibration, health grading, and breakdown models (ADR-035).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

CONTEXT_WINDOW_TOKENS: int = 256_000
DEFAULT_CONTEXT_WINDOW_TOKENS: int = CONTEXT_WINDOW_TOKENS
CHECKPOINT_STEP_TYPE: int = 23
CHECKPOINT_STEP_TYPES: frozenset[int] = frozenset({23})

AMBER_THRESHOLD: int = 180_000
RED_THRESHOLD: int = 230_000
COMPACTION_THRESHOLD: int = RED_THRESHOLD

SUBAGENT_ELEVATED_PCT: float = 0.65
SUBAGENT_HIGH_PCT: float = 0.80
SOFT_EPOCH_STEP_ADVISORY: int = 80

MAX_SAFE_BURN_RATE_PER_MIN: float = 2000.0
CRITICAL_BURN_RATE_PER_MIN: float = 4000.0

ROLE_FLIGHT_DIRECTOR: str = "flight_director"
ROLE_SWARM_ORCHESTRATOR: str = "swarm_orchestrator"
ROLE_DEEP_EXECUTION: str = "deep_execution"
ROLE_FORENSIC_AUDITOR: str = "forensic_auditor"

_EXACT_ROLE_ALIASES: Dict[str, Tuple[str, ...]] = {
    ROLE_DEEP_EXECUTION: (
        ROLE_DEEP_EXECUTION, "agyis_builder", "agyis_custodian", "agyis_architect",
        "architect", "implementer", "master_implementer", "executioner", "builder",
        "custodian", "harness_custodian", "git_custodian", "harness_builder",
        "deep_coding", "deep_coder", "coder", "execution",
        "monolithic_swe_pairing", "monolithic", "monolith", "swe_pairing", "pairing", "swe",
    ),
    ROLE_FORENSIC_AUDITOR: (
        ROLE_FORENSIC_AUDITOR, "agyis_reviewer", "agyis_auditor", "agyis_investigator",
        "reviewer", "harness_reviewer", "harness_auditor", "investigator", "detective",
        "forensic", "verifier", "auditor", "hammer", "forensics", "inspector",
    ),
    ROLE_SWARM_ORCHESTRATOR: (
        ROLE_SWARM_ORCHESTRATOR, "orchestrator", "swarm", "mesh_coordinator", "mesh",
    ),
    ROLE_FLIGHT_DIRECTOR: (
        ROLE_FLIGHT_DIRECTOR, "agyis_coordinator", "agyis_planner", "planner",
        "coordinator", "cockpit_director", "flight", "director", "cockpit", "root",
    ),
}

_SUBSTRING_ROLE_TOKENS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (ROLE_DEEP_EXECUTION, ("executioner", "builder", "custodian", "deep_execution", "deep_coding", "monolith", "swe_pairing", "architect")),
    (ROLE_FORENSIC_AUDITOR, ("hammer", "auditor", "forensic", "reviewer", "investigator", "detective", "verifier")),
    (ROLE_SWARM_ORCHESTRATOR, ("orchestrator", "swarm")),
    (ROLE_FLIGHT_DIRECTOR, ("flight", "cockpit", "planner")),
)


def normalize_role_str(val: Optional[str]) -> Optional[str]:
    """Normalizes a free-form role, agent name, or path into one of the four canonical roles."""
    if not val or not isinstance(val, str):
        return None
    norm = val.strip().lower().replace("-", "_")
    for role, aliases in _EXACT_ROLE_ALIASES.items():
        if norm in aliases:
            return role
    for role, needles in _SUBSTRING_ROLE_TOKENS:
        if any(needle in norm for needle in needles):
            return role
    return None


@dataclass(frozen=True)
class SubagentContextStatus:
    """Typed context pressure evaluation for an active subagent conversation."""

    conversation_id: str
    role: str
    step_count: int
    token_count: int
    health_zone: str  # "HEALTHY" | "AMBER" | "RED_ALERT"
    recommendation: str  # "REUSE" | "COMPACT_SOON" | "HANDOFF_OR_COMPACT"
    latency_ms: float
    parent_conversation_id: Optional[str] = None
    max_context_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS
    epoch_step_count: int = 0
    is_provisional: bool = False
    transcript_path: str = ""
    last_updated: Optional[str] = None


@dataclass(frozen=True)
class TokenBreakdown:
    """Honest per-epoch context breakdown: measured buckets + explicit unattributed gap."""

    user: int = 0
    model: int = 0
    thought: int = 0
    tool: int = 0
    checkpoint: int = 0
    system: int = 0
    unattributed: int = 0

    def to_dict(self) -> Dict[str, int]:
        """Serializes breakdown to canonical dict keeping legacy sum invariant."""
        return {
            "user": self.user,
            "model": self.model,
            "thought": self.thought,
            "tool": self.tool,
            "checkpoint": self.checkpoint,
            "system": self.system,
            "unattributed": self.unattributed,
        }


def is_checkpoint_step(step_type: object) -> bool:
    """Returns True if step_type denotes a compaction checkpoint (23 live)."""
    try:
        return int(step_type) in CHECKPOINT_STEP_TYPES  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return False


def infer_model_context_window(model_name: Optional[str]) -> int:
    """Infers model context capacity from model name when explicit metadata is absent."""
    if not model_name:
        return DEFAULT_CONTEXT_WINDOW_TOKENS
    lower = model_name.lower()
    if "1m" in lower or "1000k" in lower or "1048576" in lower:
        return 1_000_000
    if "512k" in lower:
        return 512_000
    if "200k" in lower:
        return 200_000
    if "128k" in lower:
        return 128_000
    return DEFAULT_CONTEXT_WINDOW_TOKENS


def get_scaled_thresholds(max_context_tokens: Optional[int] = None) -> Tuple[int, int]:
    """Returns proportionally scaled (amber_threshold, red_threshold) for the active window."""
    if max_context_tokens is None or max_context_tokens <= 0 or max_context_tokens == CONTEXT_WINDOW_TOKENS:
        return AMBER_THRESHOLD, RED_THRESHOLD
    amber = int(round(max_context_tokens * AMBER_THRESHOLD / CONTEXT_WINDOW_TOKENS))
    red = int(round(max_context_tokens * RED_THRESHOLD / CONTEXT_WINDOW_TOKENS))
    return amber, red


def get_urgency_tier(
    tokens: int,
    threshold: Optional[int] = None,
    max_context_tokens: Optional[int] = None,
) -> str:
    """Classifies active conversation token count into SAFE, ELEVATED, or CRITICAL."""
    effective_max = max_context_tokens if (max_context_tokens and max_context_tokens > 0) else CONTEXT_WINDOW_TOKENS
    amber_t, red_t = get_scaled_thresholds(effective_max)
    if threshold is not None and threshold > 0:
        if max_context_tokens is not None and max_context_tokens > 0:
            red_t = min(red_t, threshold)
        else:
            red_t = threshold
    if tokens >= red_t:
        return "CRITICAL"
    if tokens >= amber_t:
        return "ELEVATED"
    return "SAFE"


def classify_context_health(
    estimated_tokens: int,
    step_count: int,
    max_context_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS,
) -> Tuple[str, str]:
    """
    Grades conversation health from active-epoch window percentage and epoch step depth.
    Replaces fixed 40k/80k premature retirement cutoffs with model-scaled ratios:
      - HEALTHY / REUSE: < 65% fill AND < 80 epoch steps
      - AMBER / COMPACT_SOON: 65%..80% fill OR >= 80 epoch steps
      - RED_ALERT / HANDOFF_OR_COMPACT: >= 80% fill
    """
    window = max(1, int(max_context_tokens or DEFAULT_CONTEXT_WINDOW_TOKENS))
    ratio = max(0, int(estimated_tokens)) / float(window)
    if ratio >= SUBAGENT_HIGH_PCT:
        return "RED_ALERT", "HANDOFF_OR_COMPACT"
    if ratio >= SUBAGENT_ELEVATED_PCT or step_count >= SOFT_EPOCH_STEP_ADVISORY:
        return "AMBER", "COMPACT_SOON"
    return "HEALTHY", "REUSE"


@dataclass
class TrajectoryMetrics:
    """Unified SSOT state snapshot returned by DB + transcript readers."""

    conversation_id: str
    tokens: int = 0
    raw_estimated_tokens: int = 0
    is_provisional: bool = False
    cache_read_tokens: int = 0
    max_context_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS
    has_explicit_max_context: bool = False
    total_steps: int = 0
    epoch_steps: int = 0
    epoch_index: int = 0
    epoch_start_idx: int = 0
    checkpoint_count: int = 0
    compaction_summary: str = ""
    turn0_prompt: str = ""
    latest_user_prompt: str = ""
    model_name: str = ""
    burn_rate_tokens_per_min: float = 0.0
    mins_to_compaction: Optional[float] = None
    velocity_tier: str = "SAFE"
    sample_count: int = 0
    amber_threshold: int = AMBER_THRESHOLD
    red_threshold: int = RED_THRESHOLD
    compaction_threshold: int = COMPACTION_THRESHOLD
    recent_tools: Tuple[Tuple[str, str], ...] = ()
    extras: Dict[str, int] = field(default_factory=dict)
