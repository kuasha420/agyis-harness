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

function formatInt(value) {
  const shared = getSiteHelper("formatInt");
  if (shared) return shared(value);
  return new Intl.NumberFormat("en-US").format(Math.round(Number(value) || 0));
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

// Illustrative schematic state for Option B disjoint checkpoint switcher & SPA route focus (PSL-INV-007)
const HUD_SCHEMATIC_PROFILES = {
  root: {
    pill: "Wtc: agyis-harness (512k)",
    status: "Active route: /c/9bbbcf1e (Root coordinator, 2 child subagents attached)",
    capacity: 512000,
    checkpoints: {
      cp1: {
        rows: 2,
        inflationPct: 4.1,
        segments: [
          { label: "System & Rules", tokens: 24800, color: "#1B4DFF" },
          { label: "Platform & MCP Tools", tokens: 38200, color: "#5C8AFF" },
          { label: "User & Assistant Turns", tokens: 164400, color: "#26D0CE" },
          { label: "Compacted Tool Outputs", tokens: 82600, color: "#2AD089" },
          { label: "Thinking & Reasoning", tokens: 32400, color: "#F5B74F" },
        ],
      },
      cp2: {
        rows: 1,
        inflationPct: 2.3,
        segments: [
          { label: "System & Rules", tokens: 24800, color: "#1B4DFF" },
          { label: "Platform & MCP Tools", tokens: 38200, color: "#5C8AFF" },
          { label: "CID Checkpoint Summary", tokens: 18400, color: "#26D0CE" },
          { label: "Post-Compaction Tool Turns", tokens: 44100, color: "#2AD089" },
          { label: "Thinking & Reasoning", tokens: 14900, color: "#F5B74F" },
        ],
      },
      all: {
        rows: 2,
        inflationPct: 5.8,
        segments: [
          { label: "System & Rules", tokens: 49600, color: "#1B4DFF" },
          { label: "Platform & MCP Tools", tokens: 76400, color: "#5C8AFF" },
          { label: "Conversation & Checkpoint", tokens: 182800, color: "#26D0CE" },
          { label: "Tool Outputs (Compacted)", tokens: 126700, color: "#2AD089" },
          { label: "Thinking & Reasoning", tokens: 47300, color: "#F5B74F" },
        ],
      },
    },
  },
  child: {
    pill: "Wtc: agyis_builder (512k | <- Parent)",
    status: "Active route: /c/ffa96935 (Split pane child subagent, 8 canonical tools, parent jump enabled)",
    capacity: 512000,
    checkpoints: {
      cp1: {
        rows: 1,
        inflationPct: 1.9,
        segments: [
          { label: "System & Builder Spec", tokens: 16200, color: "#1B4DFF" },
          { label: "Scoped Tools (8/20)", tokens: 14100, color: "#5C8AFF" },
          { label: "Plan & File Reads", tokens: 96400, color: "#26D0CE" },
          { label: "Edit & Test Traces", tokens: 41800, color: "#2AD089" },
          { label: "Thinking & Reasoning", tokens: 21500, color: "#F5B74F" },
        ],
      },
      cp2: {
        rows: 1,
        inflationPct: 1.4,
        segments: [
          { label: "System & Builder Spec", tokens: 16200, color: "#1B4DFF" },
          { label: "Scoped Tools (8/20)", tokens: 14100, color: "#5C8AFF" },
          { label: "CID Checkpoint Summary", tokens: 12100, color: "#26D0CE" },
          { label: "Final Verification Output", tokens: 18200, color: "#2AD089" },
          { label: "Thinking & Reasoning", tokens: 9400, color: "#F5B74F" },
        ],
      },
      all: {
        rows: 2,
        inflationPct: 3.1,
        segments: [
          { label: "System & Builder Spec", tokens: 32400, color: "#1B4DFF" },
          { label: "Scoped Tools (8/20)", tokens: 28200, color: "#5C8AFF" },
          { label: "Plan & File Reads", tokens: 108500, color: "#26D0CE" },
          { label: "Edit & Test Traces", tokens: 60000, color: "#2AD089" },
          { label: "Thinking & Reasoning", tokens: 30900, color: "#F5B74F" },
        ],
      },
    },
  },
  auditor: {
    pill: "Wtc: agyis_auditor (512k | Read-Only)",
    status: "Active route: /c/4285221e (Split pane Gate 2 verifier, 6 canonical tools, zero write permissions)",
    capacity: 512000,
    checkpoints: {
      cp1: {
        rows: 1,
        inflationPct: 1.6,
        segments: [
          { label: "System & Auditor Spec", tokens: 14800, color: "#1B4DFF" },
          { label: "Verifier Tools (6/20)", tokens: 11200, color: "#5C8AFF" },
          { label: "Git Diff & Artifact Reads", tokens: 58600, color: "#26D0CE" },
          { label: "Hermetic Test & AFF Logs", tokens: 34200, color: "#2AD089" },
          { label: "Thinking & Reasoning", tokens: 17400, color: "#F5B74F" },
        ],
      },
      cp2: {
        rows: 1,
        inflationPct: 1.2,
        segments: [
          { label: "System & Auditor Spec", tokens: 14800, color: "#1B4DFF" },
          { label: "Verifier Tools (6/20)", tokens: 11200, color: "#5C8AFF" },
          { label: "Verdict Evidence Digest", tokens: 9800, color: "#26D0CE" },
          { label: "Signed Verdict Output", tokens: 6400, color: "#2AD089" },
          { label: "Thinking & Reasoning", tokens: 7100, color: "#F5B74F" },
        ],
      },
      all: {
        rows: 1,
        inflationPct: 2.5,
        segments: [
          { label: "System & Auditor Spec", tokens: 29600, color: "#1B4DFF" },
          { label: "Verifier Tools (6/20)", tokens: 22400, color: "#5C8AFF" },
          { label: "Diff & Evidence Digest", tokens: 68400, color: "#26D0CE" },
          { label: "Test, AFF & Verdict Logs", tokens: 40600, color: "#2AD089" },
          { label: "Thinking & Reasoning", tokens: 24500, color: "#F5B74F" },
        ],
      },
    },
  },
};

// All 15 agyis re subcommands verified verbatim from harness/commands/re.py
const RE_SUBCOMMANDS = [
  {
    name: "status",
    category: "workspace",
    flags: "--json",
    example: "agyis re status --json",
    purpose: "Inspect dirtyroom root, Ghidra .gpr/.rep projects, indexed SQLite symbol counts, and REA acceleration patch status.",
  },
  {
    name: "init",
    category: "workspace",
    flags: "[path] --project <name> --json",
    example: "agyis re init . --project TargetBinary",
    purpose: "Scaffold turnkey quarantined .dirtyroom/ workspace with SQLite database, environment file, and Ghidra directory.",
  },
  {
    name: "patch-rea",
    category: "workspace",
    flags: "--apply | --revert | --check --json",
    example: "agyis re patch-rea --apply",
    purpose: "Check, apply, or revert the REA MCP direct-mount Ghidra acceleration patch (-noanalysis -readOnly zero-copy bypass).",
  },
  {
    name: "pre-analyze",
    category: "workspace",
    flags: "<binary> --project <name> --overwrite --json (alias: preanalyze)",
    example: "agyis re pre-analyze .dirtyroom/binaries/target.bin --project TargetBinary",
    purpose: "Run one-time headless Ghidra pre-analysis on a PE/ELF/Mach-O binary and index functions, strings, and RTTI classes into SQLite.",
  },
  {
    name: "find",
    category: "query",
    flags: "<pattern> --type all|func|str|rtti --limit 50 --json",
    example: "agyis re find \"AuthSession\" --type all --limit 25",
    purpose: "Query indexed functions, strings, and RTTI vtable classes from the dirtyroom SQLite cache in under 2ms.",
  },
  {
    name: "addr",
    category: "query",
    flags: "<address> --binary <bin> --json",
    example: "agyis re addr 0x140042a10 --json",
    purpose: "Inspect and translate Virtual Address (VA), Relative Virtual Address (RVA), and File Offset with symbol resolution.",
  },
  {
    name: "xrefs",
    category: "query",
    flags: "<target> --type all|code|data --binary <bin> --json",
    example: "agyis re xrefs 0x140042a10 --type code --json",
    purpose: "Dual-mode cross-reference scan combining SQLite pre-analyzed xref cache and binary scanning.",
  },
  {
    name: "disasm",
    category: "query",
    flags: "<target> --binary <bin> --bytes 128 --limit 50",
    example: "agyis re disasm 0x140042a10 --bytes 128",
    purpose: "Disassemble instructions at a symbol or virtual address via native Intel-syntax objdump.",
  },
  {
    name: "decompile",
    category: "decompile",
    flags: "<procedure|addr> --binary <bin> --timeout 180 --no-cache",
    example: "agyis re decompile 0x140042a10 --timeout 180",
    purpose: "Decompile a procedure or interior address via the active REA bridge daemon or CLI with project cache acceleration.",
  },
  {
    name: "cache",
    category: "decompile",
    flags: "status|clear --type all|decompile --dry-run --json",
    example: "agyis re cache status --json",
    purpose: "Inspect hit statistics or safely clear the sub-5ms SQLite decompiler query cache (Issue #113).",
  },
  {
    name: "daemon",
    category: "decompile",
    flags: "status|start|stop --foreground --json",
    example: "agyis re daemon start",
    purpose: "Manage the persistent background REA MCP bridge supervisor daemon to avoid repeated JVM/Ghidra startup overhead.",
  },
  {
    name: "prime",
    category: "decompile",
    flags: "--top 20 --file <symbols> --binary <bin> --timeout 60 --dry-run --json",
    example: "agyis re prime --top 20 --dry-run",
    purpose: "Pre-warm the decompiler query cache across top-priority symbols or an explicit symbol list.",
  },
  {
    name: "pcap",
    category: "maintenance",
    flags: "<file> --limit 50 --filter <expr>",
    example: "agyis re pcap capture.pcapng --filter \"tls.handshake\" --limit 50",
    purpose: "Inspect packet capture frames via tshark with optional Wireshark display filters.",
  },
  {
    name: "seed",
    category: "maintenance",
    flags: "--pcap <file> --binary <bin> --limit <N> --json",
    example: "agyis re seed --pcap capture.pcapng --binary target.bin",
    purpose: "Ingest PCAP protocol frames into the dirtyroom SQLite database and link them to binary analysis runs.",
  },
  {
    name: "clean",
    category: "maintenance",
    flags: "--locks --logs --vacuum --force --dry-run --json",
    example: "agyis re clean --locks --logs --vacuum --dry-run",
    purpose: "Maintain dirtyroom hygiene by removing stale Ghidra .lock files, pruning old logs, and vacuuming the SQLite symbol database.",
  },
];

// All 18 ReviewedObligation strictObject keys verified verbatim from harness/cleanroom/obligation.py
const OBLIGATION_SCHEMA_KEYS = [
  { key: "obligation_id", group: "identity", type: "string (stable ID)", constraint: "Regex ^[A-Za-z][A-Za-z0-9._:/-]*$; unique across reviewed_obligations.", desc: "Canonical stable identifier referencing the behavioral requirement in manifest bindings and dependencies." },
  { key: "obligation_version", group: "identity", type: "integer >= 1", constraint: "Non-boolean integer >= 1 (REA 6.9.0).", desc: "Monotonic specification revision number tracking schema updates to this obligation." },
  { key: "title", group: "identity", type: "string (non-empty)", constraint: "NUL-free non-empty text.", desc: "Concise human-readable title summarizing the cleanroom behavior under verification." },
  { key: "application_layer", group: "identity", type: "enum string", constraint: "One of: cli, protocol, electron, persistence, process, runtime, packaging, native-abi, application, other.", desc: "Architectural layer classifying where the reconstructed obligation executes." },
  { key: "family", group: "identity", type: "string (non-empty)", constraint: "NUL-free non-empty text (default: cleanroom).", desc: "Subsystem or capability family grouping related cleanroom obligations." },
  { key: "target", group: "authority", type: "strictObject (4 keys)", constraint: "Exact keys: artifact_sha256 (null or 64-hex), application_node_id (null or jag_node_<64-hex>), semantic_node_id (null or jsrg_node_<64-hex>), location (non-empty string).", desc: "Cryptographically anchored target locator binding the obligation to shipped artifact digests or graph nodes." },
  { key: "required", group: "authority", type: "boolean", constraint: "Strict JSON boolean.", desc: "Marks whether closure of this obligation is mandatory for cleanroom certification." },
  { key: "required_case_kinds", group: "authority", type: "array[enum] (non-empty)", constraint: "Values from: positive, negative, malformed, cancellation, teardown.", desc: "Test vector classes required in manifest.bindings[].fixtures before active required obligations pass." },
  { key: "required_original_authority", group: "authority", type: "enum string", constraint: "One of: static, runtime, process, external.", desc: "Minimum evidence authority required from analysis of the original reference target." },
  { key: "required_fixture_authority", group: "authority", type: "enum string", constraint: "One of: unit, integration, protocol, renderer, packaged-process, native-abi, live-observation, external.", desc: "Proof authority level required for cleanroom test fixtures reproducing the contract." },
  { key: "required_verifier_authority", group: "authority", type: "enum string", constraint: "One of: unit, integration, protocol, renderer, packaged-process, native-abi, live-observation, external.", desc: "Proof authority level required for the independent verifier command executing in manifest.bindings[].verifier." },
  { key: "requires_parser_type", group: "authority", type: "boolean", constraint: "When true on an active required obligation, manifest.bindings[].parser_type ({parser, schema, domain_type}) cannot be null.", desc: "Declares whether wire/binary input decoding requires a formal parser, schema, and domain type binding." },
  { key: "dependency_obligation_ids", group: "gaps", type: "array[stable ID]", constraint: "Must reference existing obligation_ids in reviewed_obligations; self-dependency forbidden.", desc: "Upstream obligations that must hold before this behavior can be certified." },
  { key: "residual_unknown_ids", group: "gaps", type: "array[unk_<64-hex>]", constraint: "Must exist in evidence_bundle.unknowns; must be empty on active required obligations.", desc: "Tracks unresolved questions linked to append-only revision-chained unknown records." },
  { key: "unavailable_authority", group: "gaps", type: "array[string]", constraint: "Non-empty strings; must be empty on active required obligations.", desc: "Lists verification authorities currently unavailable in the execution environment (e.g. hardware-gated paths)." },
  { key: "required_next_evidence", group: "gaps", type: "array[string]", constraint: "Non-empty strings; must be empty on active required obligations.", desc: "Concrete next empirical observations required to close a blocked obligation." },
  { key: "disposition", group: "proof", type: "enum string", constraint: "One of: active, blocked, out-of-scope.", desc: "Current governance state; active + required enforces full owner binding, fixture case kinds, and passing verifier." },
  { key: "review_evidence_ids", group: "proof", type: "array[ev_<64-hex>] (non-empty)", constraint: "At least 1 retained evidence_id present in evidence_bundle.records.", desc: "Cryptographic SHA-256 evidence records backing the analyst review of this obligation." },
];

function initHudSchematic() {
  const routeSelect = document.getElementById("hud-route-select");
  const cpControls = document.getElementById("hud-checkpoint-controls");
  const pillEl = document.getElementById("hud-wtc-workspace-pill");
  const statusEl = document.getElementById("hud-route-status");
  const capEl = document.getElementById("hud-wtc-capacity");
  const packEl = document.getElementById("hud-wtc-packing");
  const rowsEl = document.getElementById("hud-wtc-rows");
  const legendEl = document.getElementById("hud-wtc-legend");
  if (!routeSelect || !cpControls || !rowsEl) return;

  let activeRoute = "root";
  let activeCp = "cp1";

  function render() {
    const profile = HUD_SCHEMATIC_PROFILES[activeRoute] || HUD_SCHEMATIC_PROFILES.root;
    const cp = profile.checkpoints[activeCp] || profile.checkpoints.cp1;

    if (pillEl) pillEl.textContent = profile.pill;
    if (statusEl) statusEl.textContent = profile.status;

    const usedTokens = cp.segments.reduce((sum, seg) => sum + seg.tokens, 0);
    const pct = (usedTokens / profile.capacity) * 100;

    if (capEl) {
      capEl.textContent = `Window: ${formatInt(profile.capacity)} tokens | Used: ${formatInt(usedTokens)} (${pct.toFixed(1)}%)`;
    }
    if (packEl) {
      packEl.textContent = `Atc layout: ${cp.rows} row${cp.rows === 1 ? "" : "s"} | ztc inflation: ${cp.inflationPct.toFixed(1)}% (<= 10% gate)`;
    }

    for (const btn of cpControls.querySelectorAll("button")) {
      const selected = btn.dataset.cp === activeCp;
      btn.setAttribute("aria-checked", String(selected));
      btn.classList.toggle("is-active", selected);
    }

    // Split segments proportionally across Atc row count
    const rowCapacity = profile.capacity / cp.rows;
    const rowBuckets = Array.from({ length: cp.rows }, () => []);
    let currentRow = 0;
    let currentFill = 0;

    for (const seg of cp.segments) {
      let remaining = seg.tokens;
      while (remaining > 0 && currentRow < cp.rows) {
        const space = rowCapacity - currentFill;
        const take = Math.min(remaining, space > 0 ? space : remaining);
        rowBuckets[currentRow].push({ ...seg, sliceTokens: take });
        currentFill += take;
        remaining -= take;
        if (currentFill >= rowCapacity - 1 && currentRow < cp.rows - 1) {
          currentRow += 1;
          currentFill = 0;
        }
      }
    }

    rowsEl.innerHTML = rowBuckets.map((rowSegs) => `
      <div class="hud-wtc-row">
        ${rowSegs.map((seg) => {
          const widthPct = Math.max(0.6, (seg.sliceTokens / rowCapacity) * 100);
          return `<span class="hud-wtc-seg" style="width: ${widthPct.toFixed(2)}%; background-color: ${seg.color};" title="${escapeHtml(seg.label)}: ${formatInt(seg.sliceTokens)} tokens"></span>`;
        }).join("")}
      </div>
    `).join("");

    if (legendEl) {
      legendEl.innerHTML = cp.segments.map((seg) => `
        <span class="hud-wtc-legend-item">
          <span class="hud-swatch" style="background-color: ${seg.color};"></span>
          <span>${escapeHtml(seg.label)}: ${formatInt(seg.tokens)}</span>
        </span>
      `).join("");
    }
  }

  routeSelect.addEventListener("change", () => {
    activeRoute = routeSelect.value;
    render();
  });

  cpControls.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-cp]");
    if (!btn) return;
    activeCp = btn.dataset.cp;
    render();
  });

  render();
}

function initReCommandPalette() {
  const searchInput = document.getElementById("re-search-input");
  const catGroup = document.getElementById("re-category-group");
  const cardEl = document.getElementById("re-selected-card");
  const tbodyEl = document.getElementById("re-commands-tbody");
  if (!tbodyEl || !cardEl) return;

  let activeCat = "all";
  let selectedName = "status";

  function renderSelected(cmd) {
    if (!cmd) {
      cardEl.innerHTML = "<p>No <code>agyis re</code> subcommand matches the current filter.</p>";
      return;
    }

    cardEl.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
        <h3><code>agyis re ${escapeHtml(cmd.name)}</code></h3>
        <button type="button" class="copy-btn" data-copy-text="${escapeHtml(cmd.example)}">Copy example</button>
      </div>
      <p>${escapeHtml(cmd.purpose)}</p>
      <pre class="code-panel"><code>$ ${escapeHtml(cmd.example)}
# Flags: ${escapeHtml(cmd.flags)}</code></pre>
    `;

    const bindCopy = getSiteHelper("bindCopyButtons");
    if (bindCopy) {
      bindCopy(cardEl);
    } else {
      const btn = cardEl.querySelector("[data-copy-text]");
      if (btn && navigator.clipboard) {
        btn.addEventListener("click", () => {
          navigator.clipboard.writeText(cmd.example).then(() => {
            btn.textContent = "Copied";
            setTimeout(() => { btn.textContent = "Copy example"; }, 1800);
          }).catch(() => {});
        });
      }
    }
  }

  function render() {
    const q = (searchInput?.value || "").trim().toLowerCase();
    const filtered = RE_SUBCOMMANDS.filter((c) => {
      if (activeCat !== "all" && c.category !== activeCat) return false;
      if (!q) return true;
      return `${c.name} ${c.category} ${c.flags} ${c.purpose}`.toLowerCase().includes(q);
    });

    if (filtered.length > 0 && !filtered.some((c) => c.name === selectedName)) {
      selectedName = filtered[0].name;
    }

    const active = filtered.find((c) => c.name === selectedName) || filtered[0] || null;
    renderSelected(active);

    if (catGroup) {
      for (const btn of catGroup.querySelectorAll("button")) {
        const selected = btn.dataset.reCat === activeCat;
        btn.setAttribute("aria-pressed", String(selected));
        btn.classList.toggle("is-active", selected);
      }
    }

    if (filtered.length === 0) {
      tbodyEl.innerHTML = '<tr><td data-label="Subcommand" colspan="4">No matching subcommands.</td></tr>';
      return;
    }

    tbodyEl.innerHTML = filtered.map((c) => `
      <tr data-re-row="${escapeHtml(c.name)}" style="cursor: pointer;">
        <td data-label="Subcommand"><code>agyis re ${escapeHtml(c.name)}</code></td>
        <td data-label="Category"><span class="status-pill status-pill--info">${escapeHtml(c.category)}</span></td>
        <td data-label="Key flags"><code>${escapeHtml(c.flags)}</code></td>
        <td data-label="Purpose">${escapeHtml(c.purpose)}</td>
      </tr>
    `).join("");
  }

  tbodyEl.addEventListener("click", (ev) => {
    const row = ev.target.closest("tr[data-re-row]");
    if (!row) return;
    selectedName = row.dataset.reRow;
    const match = RE_SUBCOMMANDS.find((c) => c.name === selectedName);
    if (match) renderSelected(match);
  });

  if (catGroup) {
    catGroup.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-re-cat]");
      if (!btn) return;
      activeCat = btn.dataset.reCat;
      render();
    });
  }
  if (searchInput) searchInput.addEventListener("input", render);
  render();
}

function initObligationLedgerExplorer() {
  const groupControls = document.getElementById("ledger-group-controls");
  const buttonsEl = document.getElementById("ledger-key-buttons");
  const detailEl = document.getElementById("ledger-key-detail");
  if (!buttonsEl || !detailEl) return;

  let activeGroup = "all";
  let activeKey = OBLIGATION_SCHEMA_KEYS[0].key;

  function render() {
    const filtered = activeGroup === "all"
      ? OBLIGATION_SCHEMA_KEYS
      : OBLIGATION_SCHEMA_KEYS.filter((k) => k.group === activeGroup);

    if (filtered.length > 0 && !filtered.some((k) => k.key === activeKey)) {
      activeKey = filtered[0].key;
    }

    if (groupControls) {
      for (const btn of groupControls.querySelectorAll("button")) {
        const selected = btn.dataset.ledgerCat === activeGroup;
        btn.setAttribute("aria-pressed", String(selected));
        btn.classList.toggle("is-active", selected);
      }
    }

    buttonsEl.innerHTML = filtered.map((item) => `
      <button type="button" class="key-selector-btn ${item.key === activeKey ? "is-active" : ""}" data-ledger-key="${escapeHtml(item.key)}">
        ${escapeHtml(item.key)}
      </button>
    `).join("");

    const selected = filtered.find((k) => k.key === activeKey) || filtered[0];
    if (selected) {
      const indexNum = OBLIGATION_SCHEMA_KEYS.findIndex((k) => k.key === selected.key) + 1;
      detailEl.innerHTML = `
        <h3><code>${escapeHtml(selected.key)}</code> (Key ${indexNum} of 18)</h3>
        <p>${escapeHtml(selected.desc)}</p>
        <pre class="code-panel"><code>Type:       ${escapeHtml(selected.type)}
Group:      ${escapeHtml(selected.group)}
Validation: ${escapeHtml(selected.constraint)}</code></pre>
      `;
    }
  }

  buttonsEl.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-ledger-key]");
    if (!btn) return;
    activeKey = btn.dataset.ledgerKey;
    render();
  });

  if (groupControls) {
    groupControls.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-ledger-cat]");
      if (!btn) return;
      activeGroup = btn.dataset.ledgerCat;
      render();
    });
  }

  render();
}

async function hydrateAffMetrics() {
  try {
    const overview = await fetchBundle("overview.json");
    const aff = overview?.workspace_inventory?.aff;
    if (!aff) return;

    const setText = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };
    setText("aff-score", `${Number(aff.score).toFixed(1)}/100`);
    setText("aff-status", `AFF status: ${aff.status}`);
    setText("aff-files", formatInt(aff.scanned_files));
    setText("aff-assets", formatInt(aff.scanned_assets));
    setText("aff-defects", formatInt(aff.defects_count));
  } catch {
    // Verified static defaults remain intact
  }
}

function bootHudRePage() {
  initHudSchematic();
  initReCommandPalette();
  initObligationLedgerExplorer();
  hydrateAffMetrics();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootHudRePage, { once: true });
} else {
  bootHudRePage();
}
