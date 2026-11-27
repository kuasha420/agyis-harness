// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

const LOCAL_BUNDLE_CACHE = new Map();

function getSiteHelper(name) {
  return window.AgyisSite && typeof window.AgyisSite[name] === "function"
    ? window.AgyisSite[name]
    : null;
}

async function fetchBundle(filename) {
  const sharedFetch = getSiteHelper("fetchBundle");
  if (sharedFetch) return sharedFetch(filename);
  if (LOCAL_BUNDLE_CACHE.has(filename)) return LOCAL_BUNDLE_CACHE.get(filename);
  const dataRoot = document.body?.dataset?.dataRoot || "../data/";
  const url = new URL(`${dataRoot}${filename}`, document.baseURI);
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status} loading ${filename}`);
  const payload = await resp.json();
  LOCAL_BUNDLE_CACHE.set(filename, payload);
  return payload;
}

function escapeHtml(raw) {
  const shared = getSiteHelper("escapeHtml");
  if (shared) return shared(raw);
  return String(raw ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

// Ground-truth PSL Invariant Codex v2 (verified from rules/AGENTS.md)
const CODEX_INVARIANTS = [
  {
    id: "PSL-INV-001",
    title: "Empirical verification and clean-room testing",
    category: "verification",
    layer: "Stop verification fence + Behavioral",
    summary: "Execute the repository's native verification command and observe exit code 0 before declaring completion. Keep tests fast, hermetic (tempfile/in-memory), and purge stale build caches prior to verification gates.",
  },
  {
    id: "PSL-INV-002",
    title: "Epistemic honesty and observed evidence",
    category: "verification",
    layer: "Behavioral + Obligation ledger",
    summary: "State as fact only file paths, symbols, behavior, and command outputs directly observed in the active session. Mark inferences explicitly, report exact test scopes/skips, and track residual unknowns.",
  },
  {
    id: "PSL-INV-003",
    title: "Tool determinism, failure transparency, and minimal diffs",
    category: "runtime",
    layer: "Command safety hook + Behavioral",
    summary: "Zero error swallowing or bare exit masking (append || [ $? -eq 1 ] on standalone grep/diff probes). Verify binaries before use, apply contiguous surgical edits, and auto-rebind DB port collisions.",
  },
  {
    id: "PSL-INV-004",
    title: "Context signal hygiene and runway discipline",
    category: "runtime",
    layer: "Compactor + Anti-loop + Token gauge + PreInvocation",
    summary: "Scale checkpoints proportionally across 512k/840k/1M windows (70% amber, 90% red, 80-step horizon). Never poll manage_task in loops, maintain single-source .agents/ symlinks, and delegate broad sweeps.",
  },
  {
    id: "PSL-INV-005",
    title: "Risk-scaled planning and human steering",
    category: "governance",
    layer: "Anti-drift hook + Behavioral",
    summary: "Create implementation_plan.md for high-blast-radius tasks; skip ceremony for localized fixes. Require explicit operator confirmation before destructive actions and escalate after two consecutive failures.",
  },
  {
    id: "PSL-INV-006",
    title: "Independent verification and subagent governance",
    category: "governance",
    layer: "Anti-drift + Gate 2 certification + spec.py",
    summary: "Enforce Author != Verifier via Dual-Auditor Gate 2, zero coordinator code thrash, <= 20 canonical v2.34+ tools per subagent spec, and on-disk delegate liveness inspection.",
  },
  {
    id: "PSL-INV-007",
    title: "Live reality over static fakes",
    category: "runtime",
    layer: "Trajectory HUD + Verification suites",
    summary: "Bind diagnostic HUDs to live query APIs or ConnectRPC streams rather than baked fixtures. Track SPA /c/:id routes dynamically and purge stale DOM nodes, stylesheets, and singletons on re-injection.",
  },
  {
    id: "PSL-INV-008",
    title: "Architectural fitness and sovereign boundaries",
    category: "governance",
    layer: "agyis audit aff (100.0/100)",
    summary: "Continuously verify strict layer boundaries (harness/ vs pipeline/), acyclic import DAG, externalized assets via importlib.resources, and bounded LRU/TTL state caches.",
  },
  {
    id: "PSL-RE-001",
    title: "Cleanroom RE and pre-analyzed Ghidra cache",
    category: "re",
    layer: "On-demand re-ops skill + agyis verify",
    summary: "Quarantine binary disassembly and Ghidra projects inside .dirtyroom/, run headless pre-analysis once, mount read-only with -noanalysis -readOnly, and validate 18-key typed obligation ledgers.",
  },
];

// Ground-truth tool taxonomy from harness/subagents/spec.py
const TOOL_TAXONOMY = {
  canonical: {
    description: "CANONICAL_PLATFORM_TOOLS (19 tools): Standard Antigravity v2.34+ built-in platform tools permitted in specialist agent frontmatter subject to MAX_AGENT_TOOLS = 20.",
    items: [
      "read_file", "write_file", "edit_file", "run_command", "manage_task",
      "invoke_subagent", "manage_subagents", "send_message", "define_subagent",
      "schedule", "generate_image", "search_web", "ask_question", "finish",
      "run_workflow", "update_focus", "update_steps", "search_marketplace",
      "list_plugin_accounts",
    ].map((name) => ({ name, note: "Canonical v2.34+" })),
  },
  swarm: {
    description: "SWARM_RUNTIME_TOOLS (4 tools): Injected dynamically by Antigravity Swarm sessions. Listing these statically in agent frontmatter breaks invoke_subagent executor resolution.",
    items: [
      { name: "swarm", note: "Runtime-injected board initializer" },
      { name: "post_message", note: "Runtime-injected blackboard post" },
      { name: "read_board", note: "Runtime-injected blackboard reader" },
      { name: "swarm_wait", note: "Runtime-injected reactive wait barrier" },
    ],
  },
  plan: {
    description: "ROOT_PLAN_MODE_TOOLS (2 tools): Root-session Antigravity 2.35.2 plan-mode controls. Disallowed inside subagent frontmatter specifications.",
    items: [
      { name: "enter_plan_mode", note: "Root session only" },
      { name: "exit_plan_mode", note: "Root session only" },
    ],
  },
  legacy: {
    description: "LEGACY_PLATFORM_TOOL_ALIASES (9 aliases): Automatically flagged and normalized to canonical v2.34+ equivalents across the 30 ANTIGRAVITY_PLATFORM_TOOLS registry.",
    items: [
      { name: "view_file", note: "Normalized -> read_file" },
      { name: "write_to_file", note: "Normalized -> write_file" },
      { name: "replace_file_content", note: "Normalized -> edit_file" },
      { name: "multi_replace_file_content", note: "Normalized -> edit_file" },
      { name: "list_dir", note: "Normalized -> run_command" },
      { name: "grep_search", note: "Normalized -> run_command" },
      { name: "find_by_name", note: "Normalized -> run_command" },
      { name: "read_url_content", note: "Normalized -> search_web" },
      { name: "list_permissions", note: "Normalized -> list_plugin_accounts" },
    ],
  },
};

// Ground-truth 8 specialist personas verified directly from harness/agents/*.md
const SPECIALIST_PERSONAS = [
  {
    name: "agyis_architect",
    archetype: "main",
    role: "Agyis Lead Architect & Deep Systems Implementer",
    description: "Lead architect, systems engineer, master implementer, and cross-repo harmonizer with full tool capabilities, complete customization inheritance, and verified operational discipline.",
    writePosture: "Read/Write (Full)",
    execute: true,
    subagents: true,
    inheritMcp: true,
    tools: [
      "read_file", "write_file", "edit_file", "run_command", "manage_task",
      "invoke_subagent", "send_message", "define_subagent", "schedule",
      "generate_image", "search_web", "ask_question", "finish",
      "run_workflow", "search_marketplace",
    ],
  },
  {
    name: "agyis_auditor",
    archetype: "auditor",
    role: "Agyis Victory Auditor & Benchmark Verifier",
    description: "Hermetic verification, architectural fitness gate, doctor audit, sub-second component benchmarking, and Victory Auditor certification.",
    writePosture: "Read-only",
    execute: true,
    subagents: false,
    inheritMcp: false,
    tools: ["read_file", "run_command", "manage_task", "schedule", "send_message", "search_web"],
  },
  {
    name: "agyis_builder",
    archetype: "executioner",
    role: "Agyis Executioner & Implementation Engineer",
    description: "Surgical single-phase task execution following an approved implementation plan with zero speculative scope creep.",
    writePosture: "Read/Write (Plan-scoped)",
    execute: true,
    subagents: false,
    inheritMcp: false,
    tools: ["read_file", "write_file", "edit_file", "run_command", "manage_task", "send_message", "search_web", "finish"],
  },
  {
    name: "agyis_coordinator",
    archetype: "coordinator",
    role: "Agyis Swarm Coordinator & Multi-Agent Lead",
    description: "Multi-agent swarm orchestration, milestone decomposition, and project ledger governance across /swarm, /boost, and /subagent-router.",
    writePosture: "Read/Write (Ledgers & Plans)",
    execute: true,
    subagents: true,
    inheritMcp: false,
    tools: [
      "read_file", "write_file", "edit_file", "run_command", "invoke_subagent",
      "define_subagent", "send_message", "manage_task", "ask_question",
      "schedule", "run_workflow",
    ],
  },
  {
    name: "agyis_custodian",
    archetype: "custodian",
    role: "Agyis Workspace Custodian & Git Commit Gate",
    description: "Macro architectural review, 4-pillar architectural fitness gate, DRY deduplication audit, workspace hygiene, and atomic git commit gate.",
    writePosture: "Read-only (Git custody)",
    execute: true,
    subagents: false,
    inheritMcp: false,
    tools: ["read_file", "run_command", "manage_task", "send_message"],
  },
  {
    name: "agyis_investigator",
    archetype: "investigator",
    role: "Agyis Root Cause Analyst & Forensic Investigator",
    description: "Hypothesis testing, minimal reproduction scripts in scratch, and root cause analysis. Strictly read-only on product code.",
    writePosture: "Scratch & RCA only",
    execute: true,
    subagents: false,
    inheritMcp: true,
    tools: ["read_file", "write_file", "edit_file", "run_command", "manage_task", "send_message", "search_web"],
  },
  {
    name: "agyis_planner",
    archetype: "planner",
    role: "Agyis Solutions Architect & Plan Synthesizer",
    description: "Architectural research, aperture 1 topology probes, dependency analysis, and artifact-first implementation plan synthesis.",
    writePosture: "Artifact-only (Anti-drift)",
    execute: true,
    subagents: true,
    inheritMcp: true,
    tools: [
      "read_file", "write_file", "edit_file", "run_command", "search_web",
      "manage_task", "ask_question", "invoke_subagent", "define_subagent",
      "send_message",
    ],
  },
  {
    name: "agyis_reviewer",
    archetype: "hammer",
    role: "Agyis Code Reviewer & Empirical Standards Auditor",
    description: "Delta-focused code review and architectural smell sensing against canonical empirical rules and stack invariants.",
    writePosture: "Read-only (Delta diff)",
    execute: true,
    subagents: false,
    inheritMcp: false,
    tools: ["read_file", "run_command", "manage_task", "send_message", "search_web"],
  },
];

// Ground-truth 12 Canonical Routing Workflows verified verbatim from harness/subagents/routing.py
const CANONICAL_ROUTES = [
  {
    letter: "A",
    alias: "rca",
    mnemonic_aliases: ["rca", "bugfix", "bug", "defect", "patch", "investigate", "fix"],
    title: "Bug Report / Test Regression / Silent Failure",
    starting_specialist: "agyis_investigator",
    pipeline_route: "Investigator -> Planner -> Builder -> Reviewer -> Custodian -> Auditor",
    mode: "LADDER",
    critical_invariants: "Strict Read-Only on Code: Author scratch/reproduce_*.py before writing any fix.",
    primary_deliverable: "rca_report.md + reproduce_bug.py",
    empirical_precedent: "Live debugging of /compact interceptor bug (Steps 3580-3634)",
    stage_sequence: ["INVESTIGATION", "PLANNING", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"],
    default_artifacts: { plan_path: "implementation_plan.md", reproduction_script: "scratch/reproduce_bug.py", report_path: "rca_report.md" },
  },
  {
    letter: "B",
    alias: "feature",
    mnemonic_aliases: ["feature", "plan", "spec", "milestone", "design"],
    title: "New Feature / Multi-File Milestone",
    starting_specialist: "agyis_planner",
    pipeline_route: "Planner -> Coordinator Lock-In -> Builder -> Reviewer -> Custodian -> Auditor",
    mode: "LADDER",
    critical_invariants: "Zero Speculative Code: Evaluates contracts and imports without touching source code.",
    primary_deliverable: "implementation_plan.md",
    empirical_precedent: "Epic #51 Phase 3.1 & Phase 3.3 planning",
    stage_sequence: ["PLANNING", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"],
    default_artifacts: { plan_path: "implementation_plan.md", reproduction_script: null, report_path: "plan_summary.md" },
  },
  {
    letter: "C",
    alias: "laser",
    mnemonic_aliases: ["laser", "builder", "single", "hotfix", "task"],
    title: "Well-Defined Single-Phase Task",
    starting_specialist: "agyis_builder",
    pipeline_route: "Builder -> Reviewer -> Custodian -> Auditor",
    mode: "LADDER",
    critical_invariants: "Laser Executioner: Single contiguous replacements (edit_file). Zero scope creep.",
    primary_deliverable: "In-flight diff + local test pass",
    empirical_precedent: "Native slash command bypass patch (f13e63f)",
    stage_sequence: ["EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"],
    default_artifacts: { plan_path: null, reproduction_script: null, report_path: "diff_summary.md" },
  },
  {
    letter: "D",
    alias: "overhaul",
    mnemonic_aliases: ["overhaul", "architect", "refactor", "macro", "cross-module"],
    title: "Cross-Module Architectural Overhaul",
    starting_specialist: "agyis_architect",
    pipeline_route: "Architect (delegates sub-parts) -> Reviewer -> Custodian -> Auditor",
    mode: "LADDER",
    critical_invariants: "Deep Hybrid Orchestration: Combines implementation with delegation to prevent context bloating past 50k tokens.",
    primary_deliverable: "Clean multi-module pull request / diff",
    empirical_precedent: "Issue #87 Subagent Ladder domain decoupling (a71c104)",
    stage_sequence: ["PLANNING", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"],
    default_artifacts: { plan_path: "implementation_plan.md", reproduction_script: null, report_path: "architecture_overhaul.md" },
  },
  {
    letter: "E",
    alias: "heisenbug",
    mnemonic_aliases: ["heisenbug", "flaky", "flake", "concurrency", "intermittent"],
    title: "Heisenbug during Auditor QA Gate",
    starting_specialist: "agyis_investigator",
    pipeline_route: "Auditor (FAIL) -> Investigator (RCA) -> Builder (Fix) -> Reviewer -> Custodian -> Auditor",
    mode: "LADDER",
    critical_invariants: "Anti-Bypass Invariant: Remediations must re-traverse Hammer review and Custodian commit gate.",
    primary_deliverable: "heisenbug_rca.md",
    empirical_precedent: "SQLite WAL concurrency contention debugging",
    stage_sequence: ["INVESTIGATION", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"],
    default_artifacts: { plan_path: null, reproduction_script: "scratch/reproduce_heisenbug.py", report_path: "heisenbug_rca.md" },
  },
  {
    letter: "F",
    alias: "regression",
    mnemonic_aliases: ["regression", "side-effect", "breakage"],
    title: "Obscure Regression during Macro Build",
    starting_specialist: "agyis_architect",
    pipeline_route: "Architect -> Investigator (RCA) -> Architect -> Reviewer -> Custodian -> Auditor",
    mode: "LADDER",
    critical_invariants: "Architect-to-Investigator Delegation: On mysterious test breakages, pause and delegate RCA instead of guess-editing.",
    primary_deliverable: "scratch/reproduce_*.py + rca_report.md",
    empirical_precedent: "PreInvocation locked DB handling",
    stage_sequence: ["INVESTIGATION", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"],
    default_artifacts: { plan_path: "implementation_plan.md", reproduction_script: "scratch/reproduce_regression.py", report_path: "regression_rca.md" },
  },
  {
    letter: "G",
    alias: "research",
    mnemonic_aliases: ["research", "fanout", "explore", "survey", "landscape", "discovery"],
    title: "Multi-Track Parallel Research / Landscape Mapping",
    starting_specialist: "agyis_coordinator",
    pipeline_route: "Coordinator -> Fan-out parallel Planners / Investigators -> Coordinator Synthesis",
    mode: "PARALLEL_FANOUT",
    critical_invariants: "Context Preservation (ADR-025): Independent research tracks run in parallel contexts without cross-contamination.",
    primary_deliverable: "research_synthesis.md / track_*.md",
    empirical_precedent: "Epic Research Kickoff (Steps 5-17: 4 parallel research tracks)",
    stage_sequence: ["PLANNING", "INVESTIGATION", "PROMOTION"],
    default_artifacts: { plan_path: null, reproduction_script: null, report_path: "research_synthesis.md" },
  },
  {
    letter: "H",
    alias: "cleanroom",
    mnemonic_aliases: ["cleanroom", "spec-audit", "gap-ledger", "reverse-engineer"],
    title: "Cleanroom Specification Audit & Gap Ledger",
    starting_specialist: "agyis_investigator",
    pipeline_route: "Investigator (Cleanroom Auditor) -> Coordinator -> Builder / Swarm",
    mode: "LADDER",
    critical_invariants: "Zero Production Mutation: Evaluates baseline line-by-line against formal ACs. Documents gaps in COMPLETION_LEDGER.md.",
    primary_deliverable: "COMPLETION_LEDGER.md",
    empirical_precedent: "Issue #83 Route C Baseline Audit (Step 2488)",
    stage_sequence: ["INVESTIGATION", "PLANNING", "PROMOTION"],
    default_artifacts: { plan_path: null, reproduction_script: null, report_path: "COMPLETION_LEDGER.md" },
  },
  {
    letter: "I",
    alias: "merge",
    mnemonic_aliases: ["merge", "reconcile", "golden-merge", "cross-branch"],
    title: "Cross-Branch Golden Merge & Reconciliation",
    starting_specialist: "agyis_architect",
    pipeline_route: "Architect (Synthesizer) -> Reviewer -> Custodian -> Auditor",
    mode: "LADDER",
    critical_invariants: "Hermetic Worktree Isolation: Reconciles divergent branches in dedicated worktree. Runs cross-test matrix.",
    primary_deliverable: "Golden commit on unified feature branch",
    empirical_precedent: "Epic #51 Phase 3.1 Route A vs Route B Golden Merge (Steps 1505 & 1603)",
    stage_sequence: ["EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"],
    default_artifacts: { plan_path: "merge_plan.md", reproduction_script: null, report_path: "merge_reconciliation.md" },
  },
  {
    letter: "J",
    alias: "victory",
    mnemonic_aliases: ["victory", "certification", "dual-audit", "release-gate"],
    title: "Out-of-Band Victory Certification Council",
    starting_specialist: "agyis_auditor",
    pipeline_route: "Auditor (Hermetic Benchmarks) + Reviewer (8 Rules) -> Dual Sign-Off",
    mode: "LADDER",
    critical_invariants: "Dual-Auditor Gate: Never trust in-band self-certification. Independent auditors evaluate clean committed revision on HEAD.",
    primary_deliverable: "victory_audit_report.md",
    empirical_precedent: "Route A, B, and C Victory Audits (Steps 993, 2106, 3634, 3781)",
    stage_sequence: ["CODE_REVIEW", "QA_AUDIT", "PROMOTION"],
    default_artifacts: { plan_path: null, reproduction_script: null, report_path: "victory_audit_report.md" },
  },
  {
    letter: "K",
    alias: "governance",
    mnemonic_aliases: ["governance", "issues", "curation", "epic", "github", "custodian"],
    title: "Milestone Governance & GitHub Issue Curation",
    starting_specialist: "agyis_custodian",
    pipeline_route: "Flight Director / Coordinator -> Custodian (Issue Formulation & Epic Sync via gh CLI)",
    mode: "LADDER",
    critical_invariants: "Zero Repository Document Pollution (AC5): Strictly zero scratch notes in git tree; deterministic CLI execution via gh.",
    primary_deliverable: "GitHub Issues + Parent Epic Tracking Comment",
    empirical_precedent: "Phase 3.3 GitHub Issue Harmonizer (Step 2095: Created #83, #84, #85 and synced Epic #51)",
    stage_sequence: ["PLANNING", "PROMOTION"],
    default_artifacts: { plan_path: null, reproduction_script: null, report_path: "milestone_governance_report.md" },
  },
  {
    letter: "L",
    alias: "fuzz",
    mnemonic_aliases: ["fuzz", "adversarial", "stress", "hardening"],
    title: "Adversarial Fuzzing & Stress Hardening Battery",
    starting_specialist: "agyis_builder",
    pipeline_route: "Investigator (Fuzzing Vectors) -> Builder (Adversarial Tests) -> Reviewer -> Custodian -> Auditor",
    mode: "LADDER",
    critical_invariants: "Zero Error Swallowing & Sub-Second SLA: Concurrency lock timeout <=0.5s, schema corruption tests must fail-open cleanly.",
    primary_deliverable: "tests/test_*_adversarial.py",
    empirical_precedent: "Route C Carrier-Grade Hardening (Step 2990: 4 adversarial hardening vectors)",
    stage_sequence: ["INVESTIGATION", "EXECUTION", "CODE_REVIEW", "GIT_CUSTODY", "QA_AUDIT", "PROMOTION"],
    default_artifacts: { plan_path: null, reproduction_script: "scratch/fuzz_vector.py", report_path: "hardening_report.md" },
  },
];

// Ground-truth presets from harness/skills/presets.py
const LANGUAGE_RUNTIME_PRESETS = {
  typescript: ["psl-stack-typescript", "psl-test-node"],
  node: ["psl-stack-typescript", "psl-test-node"],
  javascript: ["psl-stack-typescript", "psl-test-node"],
  python: ["psl-stack-python", "psl-test-python"],
  rust: ["psl-test-cargo", "psl-stack-systems", "psl-stack-shell"],
  cargo: ["psl-test-cargo", "psl-stack-systems", "psl-stack-shell"],
  go: ["psl-test-go"],
  systems: ["psl-stack-systems", "psl-stack-shell"],
  shell: ["psl-stack-shell"],
};

const ARCHITECTURAL_ROLE_PRESETS = {
  backend: ["psl-stack-backend", "db-ops"],
  frontend: [],
  fullstack: ["psl-stack-backend", "db-ops"],
  mobile: [],
  desktop_gui: ["display-ops"],
  cli: [],
  library: [],
  media: ["media-ops"],
  audio: ["audio-ops"],
  infra: ["remote-ops", "sec-forensics", "storage-ops"],
  re: ["re-ops"],
  cleanroom: ["re-ops"],
};

// Ground-truth 32 workspace skills verified against overview.json.workspace_inventory.skills.names
const SKILL_CATALOG = {
  "agent-builder": { category: "workflow", desc: "Interactive creation, scaffolding, and validation of custom codebase-aware specialist subagents under <= 20 tool ceiling." },
  "audio-ops": { category: "ops", desc: "PipeWire, WirePlumber, Bluetooth audio codecs, wpctl sink diagnostics, and EBU R128 loudnorm normalization." },
  "cockpit-director": { category: "workflow", desc: "Root flight deck pairing protocol, milestone decomposition, 12-route dispatch, and compaction runway governance." },
  "code-review": { category: "workflow", desc: "Delta-focused code review and PR comment resolution protocol preventing full-repository re-reading loops." },
  "db-ops": { category: "ops", desc: "PostgreSQL, SQLite, and Docker DB diagnostics, lock inspection, WAL maintenance, and port 5432 collision auto-rebind." },
  "display-ops": { category: "ops", desc: "Wayland connector probing (kscreen-doctor), graceful XDG portal recovery, Electron Ozone flags, and Sunshine KMS." },
  "git-worktree-ops": { category: "ops", desc: "Isolated multi-branch Git worktree creation, cleanup, orphan pruning, stash hygiene, and index.lock recovery." },
  "graceful-parking": { category: "workflow", desc: "Zero-kill multi-agent swarm parking, context checkpoint handoff, and deterministic resumption under token pressure." },
  "media-ops": { category: "ops", desc: "Native stream acquisition (yt-dlp impersonation ladder) and lossless ffmpeg transforms with hardware acceleration probes." },
  "milestone-handoff": { category: "workflow", desc: "Milestone completion protocol, ledger compaction (<50 lines), roadmap alignment, and fresh session reset criteria." },
  "pause": { category: "workflow", desc: "Zero-kill /pause execution suspension runbook enforcing pause_gate.json, subagent quiescence handshakes, PARKED_STATE.md, and checkpoints." },
  "powerloss-resume": { category: "workflow", desc: "Non-destructive disaster recovery runbook for resuming workspaces after power outages or workstation crashes." },
  "psl-audit-toolkit": { category: "telemetry", desc: "Empirical telemetry analysis toolkit for session performance, failure classification, loop detection, and harness tuning." },
  "psl-harmonize": { category: "workflow", desc: "Inspect, diagnose, and migrate legacy .agent/ directories and workflows into modular .agents/ single-source layouts." },
  "psl-stack-backend": { category: "stack", desc: "Backend architectural patterns, multi-tenant isolation, API contract discipline, and database migration safety." },
  "psl-stack-python": { category: "stack", desc: "Hermetic CPython >= 3.12 (3.14 recommended) development standards, runtime execution hygiene, and stdlib-first CLI engineering." },
  "psl-stack-shell": { category: "stack", desc: "Strict bash scripting standards, exit-code safety (grep/diff || [ $? -eq 1 ]), and non-interactive pipeline patterns." },
  "psl-stack-systems": { category: "stack", desc: "Systems engineering, Linux/Wayland automation, systemd user services, and network/workstation diagnostics." },
  "psl-stack-typescript": { category: "stack", desc: "Strict TypeScript contracts, bounded module boundaries, and zero-any architectural invariants." },
  "psl-test-cargo": { category: "testing", desc: "Modular Rust test runner contract with isolated targets, sub-second targeted cargo test, and clippy hygiene." },
  "psl-test-go": { category: "testing", desc: "Modular Go test runner contract with race detection (-race), hermetic package runs, and explicit error assertions." },
  "psl-test-harmonize": { category: "testing", desc: "Diff-aware test script harmonization (test:diff, test:affected, test:full) and anti-synthetic DOM/pixel test upgrades." },
  "psl-test-node": { category: "testing", desc: "Modular Node.js and TypeScript test runner contracts for vitest/jest with hermetic ESM/CJS isolation." },
  "psl-test-python": { category: "testing", desc: "Hermetic pytest and unittest discovery with TemporaryDirectory isolation and sub-second latency benchmarks." },
  "re-ops": { category: "re", desc: "Cleanroom reverse engineering (PSL-RE-001), quarantined .dirtyroom/ scaffolding, direct-mount Ghidra, and 18-key ledgers." },
  "remote-ops": { category: "ops", desc: "OpenSSH ControlMaster multiplexing, zero-footprint stdin script streaming, and <2KB compact remote server triage." },
  "resume": { category: "workflow", desc: "Live-first /resume runbook auditing live subagents and checkpoints before 3-branch triage (reattach, in-place revival, recovery) and gate removal." },
  "sec-forensics": { category: "ops", desc: "Ephemeral read-only Docker container triage, cloud credential revocation, remote diagnostics, and forensics reports." },
  "storage-ops": { category: "ops", desc: "Bounded disk triage (du -h -d 1), pacman cache hygiene, journal vacuuming, Docker pruning, Btrfs, and ntfs3 mounts." },
  "subagent-ladder": { category: "workflow", desc: "Backwards-compatible alias for subagent-router routing specialist pipelines across 12 canonical workflows." },
  "subagent-router": { category: "workflow", desc: "Dynamic multi-agent SWE execution router across Ladder, Parallel Fan-Out, Teamwork DAG, and Tournament Boost." },
  "telemetry-sync": { category: "telemetry", desc: "Cross-device telemetry delta replication, dry-run previews, systemd watch daemon setup, and self-hosted hub auth." },
};

function initCodex() {
  const group = document.getElementById("codex-filter-group");
  const grid = document.getElementById("codex-cards-grid");
  if (!group || !grid) return;

  let activeCat = "all";

  function render() {
    const items = activeCat === "all"
      ? CODEX_INVARIANTS
      : CODEX_INVARIANTS.filter((inv) => inv.category === activeCat);

    grid.innerHTML = items.map((inv) => `
      <article class="codex-card">
        <span class="codex-id">${escapeHtml(inv.id)}</span>
        <h3>${escapeHtml(inv.title)}</h3>
        <p>${escapeHtml(inv.summary)}</p>
        <span class="codex-layer">Enforcement: ${escapeHtml(inv.layer)}</span>
      </article>
    `).join("");

    for (const btn of group.querySelectorAll("button")) {
      const selected = btn.dataset.codexCat === activeCat;
      btn.setAttribute("aria-pressed", String(selected));
      btn.classList.toggle("is-active", selected);
    }
  }

  group.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-codex-cat]");
    if (!btn) return;
    activeCat = btn.dataset.codexCat;
    render();
  });

  render();
}

function initToolTaxonomy() {
  const controls = document.getElementById("tool-group-controls");
  const descEl = document.getElementById("tool-group-description");
  const gridEl = document.getElementById("tool-group-grid");
  if (!controls || !descEl || !gridEl) return;

  let activeGroup = "canonical";

  function render() {
    const bucket = TOOL_TAXONOMY[activeGroup] || TOOL_TAXONOMY.canonical;
    descEl.textContent = bucket.description;
    gridEl.innerHTML = bucket.items.map((item) => `
      <div class="tool-cell">
        <code>${escapeHtml(item.name)}</code>
        <span class="tool-cell-sub">${escapeHtml(item.note)}</span>
      </div>
    `).join("");

    for (const btn of controls.querySelectorAll("button")) {
      const selected = btn.dataset.toolGroup === activeGroup;
      btn.setAttribute("aria-checked", String(selected));
      btn.classList.toggle("is-active", selected);
    }
  }

  controls.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-tool-group]");
    if (!btn) return;
    activeGroup = btn.dataset.toolGroup;
    render();
  });

  render();
}

function initPersonaInspector() {
  const listEl = document.getElementById("persona-selector-list");
  const panelEl = document.getElementById("persona-detail-panel");
  const tbodyEl = document.getElementById("persona-summary-tbody");
  if (!listEl || !panelEl) return;

  let selectedName = SPECIALIST_PERSONAS[0].name;

  function renderDetail() {
    const spec = SPECIALIST_PERSONAS.find((p) => p.name === selectedName) || SPECIALIST_PERSONAS[0];

    for (const btn of listEl.querySelectorAll("button")) {
      const isSelected = btn.dataset.persona === spec.name;
      btn.classList.toggle("is-active", isSelected);
      btn.setAttribute("aria-selected", String(isSelected));
    }

    panelEl.innerHTML = `
      <div>
        <h3><code>${escapeHtml(spec.name)}</code> (${escapeHtml(spec.role)})</h3>
        <p style="margin-block-start: 0.375rem;">${escapeHtml(spec.description)}</p>
      </div>
      <div class="detail-kv-grid">
        <div class="detail-kv">
          <span class="detail-kv-label">Archetype</span>
          <span class="detail-kv-val">${escapeHtml(spec.archetype)}</span>
        </div>
        <div class="detail-kv">
          <span class="detail-kv-label">Declared tools</span>
          <span class="detail-kv-val">${spec.tools.length} / 20 max</span>
        </div>
        <div class="detail-kv">
          <span class="detail-kv-label">Write posture</span>
          <span class="detail-kv-val">${escapeHtml(spec.writePosture)}</span>
        </div>
        <div class="detail-kv">
          <span class="detail-kv-label">Subagents / inheritMcp</span>
          <span class="detail-kv-val">${spec.subagents ? "yes" : "no"} / ${spec.inheritMcp ? "true" : "false"}</span>
        </div>
      </div>
      <div>
        <span class="detail-kv-label" style="margin-block-end: 0.5rem;">Declared canonical tools (<code>harness/agents/${escapeHtml(spec.name)}.md</code>)</span>
        <div class="tool-list-grid" style="margin-block-start: 0;">
          ${spec.tools.map((t) => `<div class="tool-cell"><code>${escapeHtml(t)}</code></div>`).join("")}
        </div>
      </div>
    `;
  }

  listEl.innerHTML = SPECIALIST_PERSONAS.map((p) => `
    <button type="button" class="selector-item" role="option" data-persona="${escapeHtml(p.name)}">
      <code>${escapeHtml(p.name)}</code>
      <span style="font-family: var(--font-mono); font-size: 0.8125rem;">${p.tools.length} tools</span>
    </button>
  `).join("");

  listEl.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-persona]");
    if (!btn) return;
    selectedName = btn.dataset.persona;
    renderDetail();
  });

  if (tbodyEl) {
    tbodyEl.innerHTML = SPECIALIST_PERSONAS.map((p) => `
      <tr>
        <td data-label="Persona"><code>${escapeHtml(p.name)}</code></td>
        <td data-label="Archetype"><code>${escapeHtml(p.archetype)}</code></td>
        <td data-label="Tools">${p.tools.length} / 20</td>
        <td data-label="Write posture">${escapeHtml(p.writePosture)}</td>
        <td data-label="Subagents">${p.subagents ? '<span class="status-pill status-pill--info">allowed</span>' : '<span class="status-pill status-pill--warn">disabled</span>'}</td>
        <td data-label="inheritMcp">${p.inheritMcp ? '<span class="status-pill status-pill--pass">true</span>' : 'false'}</td>
      </tr>
    `).join("");
  }

  renderDetail();
}

function initWorkflowRouter() {
  const searchInput = document.getElementById("route-search-input");
  const modeSelect = document.getElementById("route-mode-select");
  const gridEl = document.getElementById("route-selector-grid");
  const panelEl = document.getElementById("route-detail-panel");
  const tbodyEl = document.getElementById("routes-table-tbody");
  if (!gridEl || !panelEl) return;

  let activeLetter = "A";

  function getFiltered() {
    const q = (searchInput?.value || "").trim().toLowerCase();
    const mode = modeSelect?.value || "all";
    return CANONICAL_ROUTES.filter((r) => {
      if (mode !== "all" && r.mode !== mode) return false;
      if (!q) return true;
      const hay = `${r.letter} ${r.alias} ${r.mnemonic_aliases.join(" ")} ${r.title} ${r.starting_specialist}`.toLowerCase();
      return hay.includes(q);
    });
  }

  function renderDetail(route) {
    if (!route) {
      panelEl.innerHTML = "<p>No routing workflow matches the current search filter.</p>";
      return;
    }

    const payloadTemplate = {
      protocol_version: "2026.1",
      task_id: `ROUTE-${route.letter}-001`,
      phase: `Phase: ${route.title}`,
      stage: route.stage_sequence[0],
      status: "PASS",
      sender_role: "cockpit_director",
      next_recommended_stage: route.stage_sequence[1] || route.stage_sequence[0],
      git_commit_hash: "HEAD",
      diff_summary: {
        modified_files: [],
        added_lines: 0,
        deleted_lines: 0,
        contiguous_chunks_count: 0,
      },
      verification: {
        command: "./agyis test",
        exit_code: 0,
        total_tests: 0,
        passed_tests: 0,
        failed_tests: 0,
        benchmark_latency_s: 0.0,
      },
      artifacts: route.default_artifacts,
      defect_ledger: [],
    };

    const jsonPreview = JSON.stringify(payloadTemplate, null, 2);

    panelEl.innerHTML = `
      <div>
        <h3>Route ${escapeHtml(route.letter)}: ${escapeHtml(route.title)}</h3>
        <p style="margin-block-start: 0.375rem;">CLI dispatch: <code>agyis cockpit route ${escapeHtml(route.letter)}</code> or <code>agyis router ${escapeHtml(route.alias)}</code></p>
      </div>
      <div class="detail-kv-grid">
        <div class="detail-kv">
          <span class="detail-kv-label">Mode</span>
          <span class="detail-kv-val">${escapeHtml(route.mode)}</span>
        </div>
        <div class="detail-kv">
          <span class="detail-kv-label">Starting specialist</span>
          <span class="detail-kv-val">${escapeHtml(route.starting_specialist)}</span>
        </div>
        <div class="detail-kv">
          <span class="detail-kv-label">Primary deliverable</span>
          <span class="detail-kv-val">${escapeHtml(route.primary_deliverable)}</span>
        </div>
        <div class="detail-kv">
          <span class="detail-kv-label">Mnemonic aliases</span>
          <span class="detail-kv-val">${escapeHtml(route.mnemonic_aliases.join(", "))}</span>
        </div>
      </div>
      <div class="detail-kv">
        <span class="detail-kv-label">Pipeline sequence</span>
        <span class="detail-kv-val">${escapeHtml(route.pipeline_route)}</span>
      </div>
      <div class="detail-kv">
        <span class="detail-kv-label">Critical invariant boundary</span>
        <span class="detail-kv-val">${escapeHtml(route.critical_invariants)}</span>
      </div>
      <div class="detail-kv">
        <span class="detail-kv-label">Empirical precedent</span>
        <span class="detail-kv-val">${escapeHtml(route.empirical_precedent)}</span>
      </div>
      <div>
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; flex-wrap: wrap; margin-block-end: 0.5rem;">
          <span class="detail-kv-label">Stage transition template (<code>psl_stage_transition_payload.json</code>)</span>
          <button type="button" class="copy-btn" data-copy-text="${escapeHtml(jsonPreview)}">Copy JSON</button>
        </div>
        <pre class="code-panel"><code>${escapeHtml(jsonPreview)}</code></pre>
      </div>
    `;

    const bindCopy = getSiteHelper("bindCopyButtons");
    if (bindCopy) {
      bindCopy(panelEl);
    } else {
      const btn = panelEl.querySelector("[data-copy-text]");
      if (btn && navigator.clipboard) {
        btn.addEventListener("click", () => {
          navigator.clipboard.writeText(jsonPreview).then(() => {
            btn.textContent = "Copied";
            setTimeout(() => { btn.textContent = "Copy JSON"; }, 1800);
          }).catch(() => {});
        });
      }
    }
  }

  function render() {
    const filtered = getFiltered();
    if (filtered.length > 0 && !filtered.some((r) => r.letter === activeLetter)) {
      activeLetter = filtered[0].letter;
    }

    gridEl.innerHTML = filtered.map((r) => `
      <button type="button" class="selector-item ${r.letter === activeLetter ? "is-active" : ""}" aria-pressed="${r.letter === activeLetter ? "true" : "false"}" data-route-letter="${escapeHtml(r.letter)}">
        <span><strong>${escapeHtml(r.letter)}</strong>: ${escapeHtml(r.alias)}</span>
      </button>
    `).join("");

    const selected = filtered.find((r) => r.letter === activeLetter) || filtered[0] || null;
    renderDetail(selected);

    if (tbodyEl) {
      tbodyEl.innerHTML = filtered.map((r) => `
        <tr>
          <td data-label="Route"><code>${escapeHtml(r.letter)}</code></td>
          <td data-label="Alias"><code>${escapeHtml(r.alias)}</code></td>
          <td data-label="Entry specialist"><code>${escapeHtml(r.starting_specialist)}</code></td>
          <td data-label="Mode"><span class="status-pill status-pill--info">${escapeHtml(r.mode)}</span></td>
          <td data-label="Pipeline sequence">${escapeHtml(r.pipeline_route)}</td>
          <td data-label="Primary deliverable">${escapeHtml(r.primary_deliverable)}</td>
        </tr>
      `).join("");
    }
  }

  gridEl.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-route-letter]");
    if (!btn) return;
    activeLetter = btn.dataset.routeLetter;
    render();
  });

  if (searchInput) searchInput.addEventListener("input", render);
  if (modeSelect) modeSelect.addEventListener("change", render);
  render();
}

function initSkillsAndPresets(liveSkillNames) {
  const langSelect = document.getElementById("preset-lang-select");
  const roleSelect = document.getElementById("preset-role-select");
  const presetOut = document.getElementById("preset-output-line");

  function renderPreset() {
    if (!langSelect || !roleSelect || !presetOut) return;
    const lang = langSelect.value;
    const role = roleSelect.value;
    const combined = Array.from(new Set([
      ...(LANGUAGE_RUNTIME_PRESETS[lang] || []),
      ...(ARCHITECTURAL_ROLE_PRESETS[role] || []),
    ]));
    const skillsList = combined.length > 0 ? combined.join(", ") : "none (base core skills only)";
    presetOut.innerHTML = `Resolved skills: <strong>${escapeHtml(skillsList)}</strong><br>Command: <code>agyis init . -s ${escapeHtml(lang)} -r ${escapeHtml(role)}</code>`;
  }

  if (langSelect) langSelect.addEventListener("change", renderPreset);
  if (roleSelect) roleSelect.addEventListener("change", renderPreset);
  renderPreset();

  const searchInput = document.getElementById("skill-search-input");
  const catGroup = document.getElementById("skill-category-group");
  const statusEl = document.getElementById("skills-count-status");
  const gridEl = document.getElementById("skills-grid");
  if (!gridEl) return;

  const skillNames = Array.isArray(liveSkillNames) && liveSkillNames.length > 0
    ? liveSkillNames
    : Object.keys(SKILL_CATALOG).sort();

  const skills = skillNames.map((name) => {
    const info = SKILL_CATALOG[name] || { category: "workflow", desc: "Verified workspace modular skill." };
    return { name, category: info.category, desc: info.desc };
  });

  let activeCat = "all";

  function renderSkills() {
    const q = (searchInput?.value || "").trim().toLowerCase();
    const filtered = skills.filter((s) => {
      if (activeCat !== "all" && s.category !== activeCat) return false;
      if (!q) return true;
      return `${s.name} ${s.category} ${s.desc}`.toLowerCase().includes(q);
    });

    if (statusEl) {
      statusEl.textContent = `Showing ${filtered.length} of ${skills.length} verified workspace skills`;
    }

    if (filtered.length === 0) {
      gridEl.innerHTML = "<p>No skills match the active filter.</p>";
      return;
    }

    gridEl.innerHTML = filtered.map((s) => `
      <article class="skill-card">
        <code>${escapeHtml(s.name)}</code>
        <p>${escapeHtml(s.desc)}</p>
        <span class="skill-meta">Category: ${escapeHtml(s.category)}</span>
      </article>
    `).join("");

    if (catGroup) {
      for (const btn of catGroup.querySelectorAll("button")) {
        const selected = btn.dataset.skillCat === activeCat;
        btn.setAttribute("aria-pressed", String(selected));
        btn.classList.toggle("is-active", selected);
      }
    }
  }

  if (catGroup) {
    catGroup.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-skill-cat]");
      if (!btn) return;
      activeCat = btn.dataset.skillCat;
      renderSkills();
    });
  }
  if (searchInput) searchInput.addEventListener("input", renderSkills);
  renderSkills();
}

async function bootCognitivePage() {
  initCodex();
  initToolTaxonomy();
  initPersonaInspector();
  initWorkflowRouter();

  let liveSkillNames = null;
  try {
    const overview = await fetchBundle("overview.json");
    const inv = overview?.workspace_inventory || {};
    const agentsEl = document.getElementById("cog-kpi-agents");
    const skillsEl = document.getElementById("cog-kpi-skills");
    if (agentsEl && inv.agents?.count) agentsEl.textContent = String(inv.agents.count);
    if (skillsEl && inv.skills?.count) skillsEl.textContent = String(inv.skills.count);
    if (Array.isArray(inv.skills?.names)) {
      liveSkillNames = inv.skills.names;
    }
  } catch {
    // Static verified fallback already rendered cleanly
  }

  initSkillsAndPresets(liveSkillNames);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootCognitivePage, { once: true });
} else {
  bootCognitivePage();
}
