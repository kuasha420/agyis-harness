// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

const LOCAL_BUNDLE_CACHE = new Map();
const SVG_NS = "http://www.w3.org/2000/svg";

function getSiteHelper(name) {
  return window.AgyisSite && typeof window.AgyisSite[name] === "function"
    ? window.AgyisSite[name]
    : null;
}

async function fetchBundle(filename) {
  const sharedFetch = getSiteHelper("fetchBundle");
  if (sharedFetch) {
    return sharedFetch(filename);
  }
  if (LOCAL_BUNDLE_CACHE.has(filename)) {
    return LOCAL_BUNDLE_CACHE.get(filename);
  }
  const dataRoot = document.body?.dataset?.dataRoot || "../data/";
  const url = new URL(`${dataRoot}${filename}`, document.baseURI);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${filename}: HTTP ${response.status}`);
  }
  const payload = await response.json();
  LOCAL_BUNDLE_CACHE.set(filename, payload);
  return payload;
}

function formatInt(value) {
  const shared = getSiteHelper("formatInt");
  if (shared) return shared(value);
  return new Intl.NumberFormat("en-US").format(Math.round(Number(value) || 0));
}

function formatPct(value, digits = 2) {
  const shared = getSiteHelper("formatPct");
  if (shared) return shared(value, digits);
  return `${Number(value || 0).toFixed(digits)}%`;
}

function formatMillions(value) {
  const num = Number(value) || 0;
  if (num >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(2)}M`;
  }
  if (num >= 1_000) {
    return `${(num / 1_000).toFixed(1)}k`;
  }
  return formatInt(num);
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

function svgEl(tag, attrs = {}, textContent = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v !== null && v !== undefined) {
      node.setAttribute(k, String(v));
    }
  }
  if (textContent !== null) {
    node.textContent = textContent;
  }
  return node;
}

function shortEraTag(eraId) {
  const raw = String(eraId || "");
  if (raw.startsWith("0_")) return "Pre";
  if (raw.includes("Post_v1.0.0")) return "HEAD";
  const parts = raw.split("_");
  return parts.length > 1 ? parts.slice(1).join("_").replace("v1.0.0-", "") : raw;
}

function hydrateKpisAndProvenance(manifest, overview, fleet) {
  const totals = overview?.totals || {};
  const comp = overview?.compaction_highlights || {};
  const range = overview?.date_range || {};

  const spanLine = document.getElementById("corpus-span-line");
  if (spanLine) {
    const startDay = String(range.min_utc || "2026-05-24").slice(0, 10);
    const endDay = String(range.max_utc || "2026-11-25").slice(0, 10);
    spanLine.textContent = `Corpus span: ${startDay} to ${endDay} UTC | Export schema ${manifest?.schema_version || "1.1.0"} | Generated ${manifest?.generated_at || ""}`;
  }

  const setText = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };

  setText("kpi-sessions", formatInt(totals.total_sessions));
  setText("kpi-steps", formatInt(totals.total_steps));
  setText("kpi-tools", formatInt(totals.total_tool_calls));
  setText(
    "kpi-tools-sub",
    `Tool calls (${formatPct(totals.overall_tool_error_rate_pct, 2)} error rate)`
  );
  setText("kpi-compaction", formatPct(comp["2kb_savings_pct"], 1));
  setText(
    "kpi-compaction-sub",
    `2KB savings (${formatInt(comp.failure_preservation_violations)} lost failures)`
  );
  setText("kpi-titans", formatInt(totals.titan_sessions));
  setText(
    "kpi-titans-sub",
    `Titan runs (${formatPct(totals.titan_steps_share_pct, 1)} step share)`
  );

  // Provenance streams from fleet_and_team.json
  const devs = fleet?.developers || {};
  const kuasha = devs.kuasha420 || { sessions: 0, steps: 0 };
  const local = devs.local || { sessions: 0, steps: 0 };
  const contrib = devs["contributor-b7b2be88"] || { sessions: 0, steps: 0 };
  const totalSessions = Number(totals.total_sessions) || (kuasha.sessions + local.sessions + contrib.sessions) || 1;
  const founderSessions = (kuasha.sessions || 0) + (local.sessions || 0);
  const founderPct = (founderSessions / totalSessions) * 100;
  const teamPct = ((contrib.sessions || 0) / totalSessions) * 100;
  const machines = fleet?.machines || {};
  const primaryNode = Object.entries(machines)[0] || ["node-69e9e817", 0];

  const founderList = document.getElementById("stream-founder-list");
  if (founderList) {
    founderList.innerHTML = [
      `<li><span>Combined founder share</span><span class="stream-stat-val">${formatInt(founderSessions)} sessions (${formatPct(founderPct, 1)})</span></li>`,
      `<li><span><code>kuasha420</code> synced handle</span><span class="stream-stat-val">${formatInt(kuasha.sessions)} sessions (${formatInt(kuasha.steps)} steps)</span></li>`,
      `<li><span><code>local</code> workstation captures</span><span class="stream-stat-val">${formatInt(local.sessions)} sessions (${formatInt(local.steps)} steps)</span></li>`,
      `<li><span>Primary hashed host (<code>${escapeHtml(primaryNode[0])}</code>)</span><span class="stream-stat-val">${formatInt(primaryNode[1])} sessions</span></li>`,
    ].join("");
  }

  const ws = fleet?.workspaces || {};
  const remote = ws.redacted_remote_summary || {};
  const teamList = document.getElementById("stream-team-list");
  if (teamList) {
    teamList.innerHTML = [
      `<li><span>Team contributor share</span><span class="stream-stat-val">${formatInt(contrib.sessions)} sessions (${formatPct(teamPct, 1)})</span></li>`,
      `<li><span><code>contributor-b7b2be88</code></span><span class="stream-stat-val">${formatInt(contrib.sessions)} sessions (${formatInt(contrib.steps)} steps)</span></li>`,
      `<li><span>Redacted remote synced summary</span><span class="stream-stat-val">${formatInt(remote.session_count)} sessions across ${formatInt(remote.workspace_entries)} workspaces</span></li>`,
      `<li><span>Local workspace repos audited</span><span class="stream-stat-val">${formatInt(ws.local_workspace_count)} repositories (${formatInt(ws.unattributed_uuid_workspaces_count)} UUID-masked)</span></li>`,
    ].join("");
  }

  const surfaces = fleet?.client_surfaces || {};
  const ide = surfaces.ide || { sessions: 0, steps: 0 };
  const cli = surfaces.cli || { sessions: 0, steps: 0 };
  const kinds = fleet?.source_kinds || {};
  const surfaceList = document.getElementById("surface-kind-list");
  if (surfaceList) {
    surfaceList.innerHTML = [
      `<li><span>IDE surface (<code>client_surfaces.ide</code>)</span><span class="stream-stat-val">${formatInt(ide.sessions)} sessions (${formatInt(ide.steps)} steps)</span></li>`,
      `<li><span>CLI surface (<code>client_surfaces.cli</code>)</span><span class="stream-stat-val">${formatInt(cli.sessions)} sessions (${formatInt(cli.steps)} steps)</span></li>`,
      `<li><span><code>sqlite_db</code> source records</span><span class="stream-stat-val">${formatInt(kinds.sqlite_db)} sessions</span></li>`,
      `<li><span><code>transcript_full</code> source records</span><span class="stream-stat-val">${formatInt(kinds.transcript_full)} sessions</span></li>`,
      `<li><span><code>transcript</code> source records</span><span class="stream-stat-val">${formatInt(kinds.transcript)} sessions</span></li>`,
    ].join("");
  }

  // Live privacy audit 5-flag grid
  const audit = manifest?.privacy_audit || {};
  const auditNotes = {
    raw_prompts_included: "Prompt bodies stripped via _BLOCKED_KEYS",
    emails_redacted: "All email addresses scrubbed before export",
    secrets_stripped: "PEM, Bearer, ghp_, AKIA, sk-, AIza, xox*",
    home_paths_anonymized: "Home directories and private repo names SHA-256 masked",
    leak_checks_passed: "Verified by _assert_no_leaks() at export",
  };
  const auditGrid = document.getElementById("privacy-audit-grid");
  if (auditGrid && Object.keys(audit).length > 0) {
    auditGrid.innerHTML = Object.entries(audit).map(([key, val]) => {
      const expectedOk = key === "raw_prompts_included" ? val === false : val === true;
      const colorStyle = expectedOk ? "color: var(--semantic-pass);" : "color: var(--semantic-fail);";
      return `
        <div class="integrity-tile">
          <span class="integrity-key">${escapeHtml(key)}</span>
          <span class="integrity-val" style="${colorStyle}">${escapeHtml(String(val))}</span>
          <span class="integrity-note">${escapeHtml(auditNotes[key] || "Export integrity assertion")}</span>
        </div>
      `;
    }).join("");
  }

  // Bundle SHA-256 table
  const bundlesTbody = document.getElementById("manifest-bundles-tbody");
  const bundles = manifest?.bundles || {};
  if (bundlesTbody && Object.keys(bundles).length > 0) {
    bundlesTbody.innerHTML = Object.entries(bundles).map(([name, info]) => `
      <tr>
        <td data-label="Bundle file"><code>${escapeHtml(name)}</code></td>
        <td data-label="Size (bytes)">${formatInt(info.bytes)}</td>
        <td data-label="SHA-256 digest"><code class="hash-code">${escapeHtml(info.sha256)}</code></td>
      </tr>
    `).join("");
  }
}

function initEraChart(erasData) {
  const svg = document.getElementById("era-chart-svg");
  const readout = document.getElementById("era-chart-readout");
  const metricSelect = document.getElementById("era-metric-select");
  const cohortSelect = document.getElementById("era-cohort-select");
  const tbody = document.getElementById("era-table-tbody");
  if (!svg || !metricSelect || !cohortSelect) return;

  const mcc = erasData?.model_controlled_comparison || {};
  const modelKeys = Object.keys(mcc);
  for (const modelKey of modelKeys) {
    const entries = mcc[modelKey] || [];
    const totalN = entries.reduce((sum, item) => sum + (Number(item.sessions) || 0), 0);
    const opt = document.createElement("option");
    opt.value = modelKey;
    opt.textContent = `${modelKey} (${formatInt(totalN)} sessions, ${entries.length} eras)`;
    cohortSelect.appendChild(opt);
  }

  const metricMeta = {
    interventions_per_100_steps: {
      label: "Interventions / 100 steps",
      fmt: (v) => Number(v || 0).toFixed(2),
    },
    errors_per_1k_calls: {
      label: "Errors / 1k tool calls",
      fmt: (v) => Number(v || 0).toFixed(2),
    },
    loop_candidates_per_1k_calls: {
      label: "Loop candidates / 1k calls",
      fmt: (v) => Number(v || 0).toFixed(2),
    },
    compaction_savings_2kb_pct: {
      label: "2KB compaction savings %",
      fmt: (v) => formatPct(v, 2),
    },
  };

  function render() {
    const metricKey = metricSelect.value;
    const cohortKey = cohortSelect.value;
    const meta = metricMeta[metricKey] || metricMeta.interventions_per_100_steps;
    const series = cohortKey === "all"
      ? (erasData?.eras || [])
      : (mcc[cohortKey] || []);

    svg.innerHTML = "";
    if (series.length === 0) {
      svg.appendChild(svgEl("text", { x: 480, y: 180, fill: "#9AA8BE", "text-anchor": "middle" }, "No era records available for this cohort."));
      return;
    }

    const W = 960;
    const H = 360;
    const pad = { top: 28, right: 34, bottom: 72, left: 68 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    const values = series.map((d) => Number(d[metricKey]) || 0);
    const maxVal = Math.max(...values, 1) * 1.15;
    const maxSessions = Math.max(...series.map((d) => Number(d.sessions) || 0), 1);

    const xFor = (idx) => series.length === 1
      ? pad.left + plotW / 2
      : pad.left + (idx / (series.length - 1)) * plotW;
    const yFor = (val) => pad.top + plotH - (val / maxVal) * plotH;

    // Horizontal gridlines and Y axis labels
    const ticks = 4;
    for (let i = 0; i <= ticks; i++) {
      const val = (maxVal / ticks) * i;
      const y = yFor(val);
      svg.appendChild(svgEl("line", {
        x1: pad.left,
        y1: y,
        x2: W - pad.right,
        y2: y,
        stroke: "#1E2C47",
        "stroke-dasharray": i === 0 ? null : "4 4",
        "stroke-width": 1,
      }));
      svg.appendChild(svgEl("text", {
        x: pad.left - 10,
        y: y + 4,
        fill: "#9AA8BE",
        "text-anchor": "end",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 11,
      }, meta.fmt(val)));
    }

    // Session volume background bars
    const barW = Math.min(34, Math.max(12, plotW / Math.max(series.length * 1.8, 1)));
    series.forEach((item, idx) => {
      const sess = Number(item.sessions) || 0;
      const barH = (sess / maxSessions) * (plotH * 0.42);
      const cx = xFor(idx);
      svg.appendChild(svgEl("rect", {
        x: (cx - barW / 2).toFixed(1),
        y: (pad.top + plotH - barH).toFixed(1),
        width: barW.toFixed(1),
        height: barH.toFixed(1),
        rx: 3,
        fill: "#1B4DFF",
        opacity: "0.28",
      }));
    });

    // Polyline
    const pointsStr = series.map((item, idx) => `${xFor(idx).toFixed(1)},${yFor(Number(item[metricKey]) || 0).toFixed(1)}`).join(" ");
    svg.appendChild(svgEl("polyline", {
      points: pointsStr,
      fill: "none",
      stroke: "#26D0CE",
      "stroke-width": 2.75,
      "stroke-linejoin": "round",
      "stroke-linecap": "round",
    }));

    function updateReadout(item) {
      if (!readout) return;
      const cohortLabel = cohortKey === "all" ? "All sessions" : cohortKey;
      readout.textContent = `${cohortLabel} | ${item.label}: ${meta.label} = ${meta.fmt(item[metricKey])} | Sessions: ${formatInt(item.sessions)} | Steps: ${formatInt(item.steps)} | Errors/1k: ${Number(item.errors_per_1k_calls || 0).toFixed(2)} | Interventions/100: ${Number(item.interventions_per_100_steps || 0).toFixed(2)}`;
    }

    // Focusable data points and X labels
    series.forEach((item, idx) => {
      const cx = xFor(idx);
      const cy = yFor(Number(item[metricKey]) || 0);

      svg.appendChild(svgEl("text", {
        x: cx.toFixed(1),
        y: pad.top + plotH + 22,
        fill: "#9AA8BE",
        "text-anchor": "middle",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 11,
      }, shortEraTag(item.era_id)));

      svg.appendChild(svgEl("text", {
        x: cx.toFixed(1),
        y: pad.top + plotH + 38,
        fill: "#6E7F9B",
        "text-anchor": "middle",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 11,
      }, `n=${formatInt(item.sessions)}`));

      const circle = svgEl("circle", {
        cx: cx.toFixed(1),
        cy: cy.toFixed(1),
        r: 6,
        fill: "#080E1A",
        stroke: "#26D0CE",
        "stroke-width": 2.5,
        tabindex: "0",
        role: "button",
        class: "chart-point-target",
        "aria-label": `${item.label}: ${meta.label} ${meta.fmt(item[metricKey])}, ${formatInt(item.sessions)} sessions`,
      });
      circle.addEventListener("mouseenter", () => updateReadout(item));
      circle.addEventListener("focus", () => updateReadout(item));
      circle.addEventListener("click", () => updateReadout(item));
      svg.appendChild(circle);
    });

    // Set initial summary in readout
    if (series.length >= 2) {
      const first = series[0];
      const last = series[series.length - 1];
      const cohortLabel = cohortKey === "all" ? "All 3,856 sessions" : cohortKey;
      readout.textContent = `${cohortLabel} (${series.length} eras): ${shortEraTag(first.era_id)} ${meta.fmt(first[metricKey])} -> ${shortEraTag(last.era_id)} ${meta.fmt(last[metricKey])} (${meta.label}). Focus or hover any node for details.`;
    } else if (series.length === 1) {
      updateReadout(series[0]);
    }

    // Accessible fallback table
    if (tbody) {
      tbody.innerHTML = series.map((item) => `
        <tr>
          <td data-label="Era"><code>${escapeHtml(item.era_id)}</code> (${escapeHtml(item.label)})</td>
          <td data-label="Sessions">${formatInt(item.sessions)}</td>
          <td data-label="Steps">${formatInt(item.steps)}</td>
          <td data-label="Errors / 1k">${Number(item.errors_per_1k_calls || 0).toFixed(2)}</td>
          <td data-label="Interventions / 100">${Number(item.interventions_per_100_steps || 0).toFixed(2)}</td>
          <td data-label="Loops / 1k">${Number(item.loop_candidates_per_1k_calls || 0).toFixed(2)}</td>
          <td data-label="2KB savings">${formatPct(item.compaction_savings_2kb_pct, 2)}</td>
        </tr>
      `).join("");
    }
  }

  metricSelect.addEventListener("change", render);
  cohortSelect.addEventListener("change", render);
  render();
}

function initModelChart(modelsData) {
  const svg = document.getElementById("model-chart-svg");
  const readout = document.getElementById("model-chart-readout");
  const metricSelect = document.getElementById("model-metric-select");
  const legacyToggle = document.getElementById("include-legacy-toggle");
  const legacyLabel = document.getElementById("legacy-toggle-label");
  const tbody = document.getElementById("model-table-tbody");
  if (!svg || !metricSelect || !legacyToggle) return;

  // Explicitly ensure default OFF on load
  legacyToggle.checked = false;

  const rt = modelsData?.reasoning_tiers || {};
  const tiersObj = rt.tiers || {};
  const isolatedObj = rt.isolated_unattributed || {};

  const attributedRows = Object.values(tiersObj).filter((item) => {
    const id = String(item?.tier_id || "");
    return item
      && item.data_source !== "unattributed_legacy"
      && id !== "unattributed_legacy"
      && id !== "unknown"
      && Number(item.session_count || 0) > 0;
  }).map((item) => ({
    ...item,
    isLegacy: false,
  }));

  const legacyRows = Object.values(isolatedObj).map((item) => ({
    ...item,
    isLegacy: true,
  }));

  if (legacyLabel && legacyRows.length > 0) {
    const parts = legacyRows.map((r) => `${r.tier_id}: ${formatInt(r.session_count)}`);
    legacyLabel.textContent = `Include unattributed legacy buckets (${parts.join(", ")})`;
  }

  const metricConfig = {
    tool_error_rate_pct: {
      label: "Tool error rate %",
      fmt: (v) => formatPct(v, 2),
      sortAsc: true,
    },
    average_steps: {
      label: "Average steps",
      fmt: (v) => Number(v || 0).toFixed(1),
      sortAsc: false,
    },
    average_thinking_tokens: {
      label: "Average thinking tokens",
      fmt: (v) => formatInt(v),
      sortAsc: false,
    },
  };

  function render() {
    const metricKey = metricSelect.value;
    const includeLegacy = Boolean(legacyToggle.checked);
    const cfg = metricConfig[metricKey] || metricConfig.tool_error_rate_pct;

    const rows = (includeLegacy ? [...attributedRows, ...legacyRows] : [...attributedRows])
      .sort((a, b) => {
        const av = Number(a[metricKey]) || 0;
        const bv = Number(b[metricKey]) || 0;
        return cfg.sortAsc ? av - bv : bv - av;
      });

    const rowH = 30;
    const pad = { top: 20, right: 120, bottom: 24, left: 265 };
    const W = 960;
    const H = Math.max(240, pad.top + pad.bottom + rows.length * rowH);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = "";

    const plotW = W - pad.left - pad.right;
    const maxVal = Math.max(...rows.map((r) => Number(r[metricKey]) || 0), 1);

    function showRow(row) {
      if (!readout) return;
      const errRate = Number(row.tool_error_rate_pct || 0);
      const perCallRel = Math.max(0, 100 - errRate);
      const tag = row.isLegacy ? "Isolated unattributed legacy" : "Attributed empirical";
      readout.textContent = `${row.name} (${tag}, n=${formatInt(row.session_count)}): Tool error rate ${formatPct(errRate, 2)} (Per-call reliability ${formatPct(perCallRel, 2)}) | Zero-error sessions ${formatPct(row.accuracy_percent, 1)} | Avg steps ${Number(row.average_steps || 0).toFixed(1)} | Avg thinking ${formatInt(row.average_thinking_tokens)}`;
    }

    rows.forEach((row, idx) => {
      const y = pad.top + idx * rowH;
      const val = Number(row[metricKey]) || 0;
      const barW = Math.max(4, (val / maxVal) * plotW);
      const barColor = row.isLegacy ? "#F5B74F" : "#5C8AFF";
      const errRate = Number(row.tool_error_rate_pct || 0);
      const perCallRel = Math.max(0, 100 - errRate);

      const g = svgEl("g", {
        tabindex: "0",
        role: "button",
        class: "chart-point-target",
        "aria-label": `${row.name}: ${cfg.label} ${cfg.fmt(val)}, per-call reliability ${formatPct(perCallRel, 2)}, ${formatInt(row.session_count)} sessions`,
      });

      g.appendChild(svgEl("rect", {
        x: 0,
        y: y - 2,
        width: W,
        height: rowH - 2,
        fill: idx % 2 === 0 ? "rgba(255,255,255,0.02)" : "transparent",
      }));

      g.appendChild(svgEl("text", {
        x: pad.left - 12,
        y: y + 16,
        fill: row.isLegacy ? "#F5B74F" : "#F4F6FA",
        "text-anchor": "end",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 11.5,
      }, `${row.tier_id} (n=${formatInt(row.session_count)})`));

      g.appendChild(svgEl("rect", {
        x: pad.left,
        y: y + 5,
        width: barW.toFixed(1),
        height: 15,
        rx: 3,
        fill: barColor,
      }));

      const rightLabel = metricKey === "tool_error_rate_pct"
        ? `${cfg.fmt(val)} (${formatPct(perCallRel, 1)} ok)`
        : cfg.fmt(val);
      g.appendChild(svgEl("text", {
        x: (pad.left + barW + 8).toFixed(1),
        y: y + 16,
        fill: "#9AA8BE",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 11,
      }, rightLabel));

      g.addEventListener("mouseenter", () => showRow(row));
      g.addEventListener("focus", () => showRow(row));
      g.addEventListener("click", () => showRow(row));
      svg.appendChild(g);
    });

    if (readout) {
      const hiddenCount = includeLegacy ? 0 : legacyRows.reduce((s, r) => s + Number(r.session_count || 0), 0);
      readout.textContent = includeLegacy
        ? `Showing ${rows.length} tiers including isolated unattributed legacy buckets. Focus or hover any row for details.`
        : `Showing ${rows.length} attributed empirical tiers (${formatInt(hiddenCount)} unattributed legacy sessions excluded by default). Focus or hover any row for details.`;
    }

    if (tbody) {
      tbody.innerHTML = rows.map((row) => {
        const errRate = Number(row.tool_error_rate_pct || 0);
        const perCallRel = Math.max(0, 100 - errRate);
        const statusHtml = row.isLegacy
          ? '<span class="status-pill status-pill--warn">legacy</span>'
          : '<span class="status-pill status-pill--pass">attributed</span>';
        return `
          <tr>
            <td data-label="Tier"><code>${escapeHtml(row.tier_id)}</code></td>
            <td data-label="Attribution">${statusHtml}</td>
            <td data-label="Sessions">${formatInt(row.session_count)}</td>
            <td data-label="Tool error rate">${formatPct(errRate, 2)}</td>
            <td data-label="Per-call reliability">${formatPct(perCallRel, 2)}</td>
            <td data-label="Zero-error sessions">${formatPct(row.accuracy_percent, 1)}</td>
            <td data-label="Avg steps">${Number(row.average_steps || 0).toFixed(1)}</td>
            <td data-label="Avg thinking tokens">${formatInt(row.average_thinking_tokens)}</td>
          </tr>
        `;
      }).join("");
    }
  }

  metricSelect.addEventListener("change", render);
  legacyToggle.addEventListener("change", render);
  render();
}

function initCompactorSimulator(deepData) {
  const controls = document.getElementById("compactor-cap-controls");
  const compSvg = document.getElementById("compactor-chart-svg");
  const distSvg = document.getElementById("tool-dist-svg");
  const readout = document.getElementById("compactor-chart-readout");
  const compTbody = document.getElementById("compactor-table-tbody");
  const exitGrid = document.getElementById("exit1-breakdown-grid");
  if (!controls || !compSvg || !distSvg) return;

  const sims = deepData?.compactor_simulations || [];
  const tools = (deepData?.tool_distributions || []).slice(0, 8);
  const exit1 = deepData?.exit_code_1_breakdown || {};

  let activeThreshold = 2048;

  // Populate exit code 1 breakdown
  if (exitGrid && exit1.total) {
    exitGrid.innerHTML = `
      <div class="exit1-card">
        <div class="exit1-num">${formatInt(exit1.grep_diff_benign)} (${formatPct(exit1.grep_diff_pct, 2)})</div>
        <div class="exit1-desc">Benign <code>grep</code> / <code>diff</code> empty-match exits out of ${formatInt(exit1.total)}</div>
      </div>
      <div class="exit1-card">
        <div class="exit1-num">${formatInt(exit1.python_traceback)} (${formatPct(exit1.python_traceback_pct, 2)})</div>
        <div class="exit1-desc">Python runtime tracebacks preserved verbatim</div>
      </div>
      <div class="exit1-card">
        <div class="exit1-num">${formatInt(exit1.python_syntax_total)} (${formatPct(exit1.python_syntax_pct, 2)})</div>
        <div class="exit1-desc">Python syntax errors (${formatInt(exit1.fstring_backslash)} f-string backslashes)</div>
      </div>
      <div class="exit1-card">
        <div class="exit1-num">${formatInt(exit1.other_cli)} (${formatPct(exit1.other_cli_pct, 2)})</div>
        <div class="exit1-desc">Other CLI test, build, and runtime exits</div>
      </div>
    `;
  }

  // Render accessible table for compactor simulations
  if (compTbody) {
    compTbody.innerHTML = sims.map((s) => `
      <tr>
        <td data-label="Threshold"><code>${escapeHtml(s.threshold_label)}</code> (${formatInt(s.threshold_bytes)} B)</td>
        <td data-label="Impacted calls">${formatInt(s.impacted_calls)}</td>
        <td data-label="Saved tokens">${formatInt(s.saved_tokens)}</td>
        <td data-label="Volume reduction">${formatPct(s.pct_volume_reduction, 2)}</td>
        <td data-label="Failures preserved">${formatInt(s.failures_preserved)}</td>
        <td data-label="Violations">${formatInt(s.failure_preservation_violations)}</td>
      </tr>
    `).join("");
  }

  // Render 6-cap segmented buttons
  controls.innerHTML = "";
  sims.forEach((sim) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "segmented-btn";
    btn.setAttribute("role", "radio");
    btn.dataset.threshold = String(sim.threshold_bytes);
    const suffix = sim.threshold_bytes === 2048
      ? " (default)"
      : sim.threshold_bytes === 32768
        ? " (read_file)"
        : "";
    btn.textContent = `${sim.threshold_label}${suffix}`;
    btn.addEventListener("click", () => {
      activeThreshold = sim.threshold_bytes;
      renderCompactor();
    });
    controls.appendChild(btn);
  });

  function renderCompactor() {
    const active = sims.find((s) => s.threshold_bytes === activeThreshold) || sims[1] || sims[0];
    if (!active) return;

    for (const btn of controls.querySelectorAll("button")) {
      const isSelected = Number(btn.dataset.threshold) === active.threshold_bytes;
      btn.setAttribute("aria-checked", String(isSelected));
      btn.classList.toggle("is-active", isSelected);
    }

    const setText = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };
    setText("sim-pct-reduction", formatPct(active.pct_volume_reduction, 2));
    setText("sim-saved-tokens", formatMillions(active.saved_tokens));
    setText("sim-impacted-calls", formatInt(active.impacted_calls));
    setText("sim-violations", formatInt(active.failure_preservation_violations));
    setText("sim-failures-preserved", `Failure violations (${formatInt(active.failures_preserved)} preserved)`);

    // Render Compactor threshold bar SVG
    compSvg.innerHTML = "";
    const W = 540;
    const H = 280;
    const pad = { top: 24, right: 20, bottom: 44, left: 50 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;
    const maxPct = 70;

    for (let p = 0; p <= 60; p += 20) {
      const y = pad.top + plotH - (p / maxPct) * plotH;
      compSvg.appendChild(svgEl("line", {
        x1: pad.left,
        y1: y,
        x2: W - pad.right,
        y2: y,
        stroke: "#1E2C47",
        "stroke-dasharray": p === 0 ? null : "3 3",
      }));
      compSvg.appendChild(svgEl("text", {
        x: pad.left - 8,
        y: y + 4,
        fill: "#9AA8BE",
        "text-anchor": "end",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 11,
      }, `${p}%`));
    }

    const slotW = plotW / Math.max(sims.length, 1);
    const barW = Math.min(48, slotW * 0.62);

    sims.forEach((sim, idx) => {
      const cx = pad.left + idx * slotW + slotW / 2;
      const barH = (Number(sim.pct_volume_reduction) / maxPct) * plotH;
      const y = pad.top + plotH - barH;
      const isSelected = sim.threshold_bytes === active.threshold_bytes;

      const g = svgEl("g", {
        tabindex: "0",
        role: "button",
        class: "chart-point-target",
        "aria-label": `${sim.threshold_label} cap: ${formatPct(sim.pct_volume_reduction, 2)} volume reduction, ${formatInt(sim.saved_tokens)} saved tokens, ${formatInt(sim.failure_preservation_violations)} violations`,
      });

      g.appendChild(svgEl("rect", {
        x: (cx - barW / 2).toFixed(1),
        y: y.toFixed(1),
        width: barW.toFixed(1),
        height: barH.toFixed(1),
        rx: 4,
        fill: isSelected ? "#26D0CE" : "#1B4DFF",
        opacity: isSelected ? "1" : "0.55",
      }));

      g.appendChild(svgEl("text", {
        x: cx.toFixed(1),
        y: (y - 6).toFixed(1),
        fill: isSelected ? "#F4F6FA" : "#9AA8BE",
        "text-anchor": "middle",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 11,
      }, `${Number(sim.pct_volume_reduction).toFixed(1)}%`));

      g.appendChild(svgEl("text", {
        x: cx.toFixed(1),
        y: pad.top + plotH + 22,
        fill: isSelected ? "#26D0CE" : "#9AA8BE",
        "text-anchor": "middle",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 11,
      }, sim.threshold_label));

      const activate = () => {
        activeThreshold = sim.threshold_bytes;
        renderCompactor();
      };
      g.addEventListener("click", activate);
      g.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          activate();
        }
      });
      g.addEventListener("focus", () => {
        if (readout) {
          readout.textContent = `Cap ${sim.threshold_label}: ${formatPct(sim.pct_volume_reduction, 2)} reduction (${formatInt(sim.saved_tokens)} tokens saved across ${formatInt(sim.impacted_calls)} calls, ${formatInt(sim.failures_preserved)} failures preserved, ${formatInt(sim.failure_preservation_violations)} violations).`;
        }
      });
      compSvg.appendChild(g);
    });

    if (readout) {
      readout.textContent = `Active cap ${active.threshold_label} (${formatInt(active.threshold_bytes)} bytes): saves ${formatInt(active.saved_tokens)} tokens (${formatPct(active.pct_volume_reduction, 2)}) across ${formatInt(active.impacted_calls)} calls with ${formatInt(active.failure_preservation_violations)} failure preservation violations.`;
    }
  }

  // Render stacked tool output distribution SVG
  function renderToolDist() {
    distSvg.innerHTML = "";
    const W = 540;
    const H = 280;
    const pad = { top: 14, right: 64, bottom: 16, left: 136 };
    const plotW = W - pad.left - pad.right;
    const rowH = (H - pad.top - pad.bottom) / Math.max(tools.length, 1);

    const bucketSpecs = [
      { key: "lt_500", color: "#2AD089", label: "<500B" },
      { key: "500_to_2k", color: "#26D0CE", label: "500B-2KB" },
      { key: "2k_to_10k", color: "#5C8AFF", label: "2KB-10KB" },
      { key: "10k_to_50k", color: "#F5B74F", label: "10KB-50KB" },
      { key: "gt_50k", color: "#FF6B6B", label: ">50KB" },
    ];

    tools.forEach((tool, idx) => {
      const y = pad.top + idx * rowH;
      const buckets = tool.buckets || {};
      const total = Math.max(
        bucketSpecs.reduce((s, b) => s + Number(buckets[b.key] || 0), 0),
        1
      );

      const g = svgEl("g", {
        tabindex: "0",
        role: "button",
        class: "chart-point-target",
        "aria-label": `${tool.tool_name}: ${formatInt(tool.call_count)} calls, ${formatPct(tool.pct_exceeding_2kb, 2)} exceeding 2KB`,
      });

      g.appendChild(svgEl("text", {
        x: pad.left - 8,
        y: y + rowH * 0.62,
        fill: "#F4F6FA",
        "text-anchor": "end",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 11,
      }, tool.tool_name));

      let offsetX = pad.left;
      bucketSpecs.forEach((spec) => {
        const count = Number(buckets[spec.key] || 0);
        if (count <= 0) return;
        const segW = (count / total) * plotW;
        g.appendChild(svgEl("rect", {
          x: offsetX.toFixed(1),
          y: (y + 5).toFixed(1),
          width: Math.max(1.5, segW).toFixed(1),
          height: Math.max(12, rowH - 12).toFixed(1),
          fill: spec.color,
        }));
        offsetX += segW;
      });

      g.appendChild(svgEl("text", {
        x: W - pad.right + 6,
        y: y + rowH * 0.62,
        fill: "#9AA8BE",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 10.5,
      }, `${Number(tool.pct_exceeding_2kb || 0).toFixed(1)}% >2K`));

      const announceTool = () => {
        if (!readout) return;
        readout.textContent = `${tool.tool_name}: ${formatInt(tool.call_count)} calls | Avg ${formatInt(tool.avg_output_chars)} chars | p95 ${formatInt(tool.p95_output_chars)} chars | ${formatPct(tool.pct_exceeding_2kb, 2)} exceeding 2KB (${formatMillions(tool.estimated_output_tokens)} tokens).`;
      };
      g.addEventListener("mouseenter", announceTool);
      g.addEventListener("focus", announceTool);
      g.addEventListener("click", announceTool);
      distSvg.appendChild(g);
    });
  }

  renderCompactor();
  renderToolDist();
}

function initTitanAndSaturation(deepData) {
  const barEl = document.getElementById("titan-archetype-bar");
  const satSvg = document.getElementById("saturation-chart-svg");
  const satReadout = document.getElementById("saturation-chart-readout");
  const satTbody = document.getElementById("saturation-table-tbody");
  const ctxNote = document.getElementById("context-dynamics-note");
  const searchInput = document.getElementById("titan-search-input");
  const archSelect = document.getElementById("titan-archetype-select");
  const countEl = document.getElementById("titan-filter-count");
  const titanTbody = document.getElementById("titan-sessions-tbody");

  const titan = deepData?.titan_sessions || {};
  const macro = titan.macro_summary || {};
  const archDist = macro.archetype_distribution || {};
  const surv = Number(archDist.TYPE_A_SURVIVOR || 0);
  const brk = Number(archDist.TYPE_B_SYSTEMS_BREAKTHROUGH || 0);
  const trap = Number(archDist.TYPE_C_THRASHING_TRAP || 0);
  const totalT = Math.max(surv + brk + trap, 1);

  const barLegend = document.getElementById("titan-archetype-legend");
  if (barEl) {
    barEl.setAttribute(
      "aria-label",
      `Titan session archetype split: ${formatInt(surv)} survivors, ${formatInt(brk)} breakthroughs, ${formatInt(trap)} thrashing traps`
    );
    barEl.innerHTML = `
      <div class="archetype-seg archetype-seg--survivor" style="width: ${((surv / totalT) * 100).toFixed(2)}%;" title="Survivor: ${formatInt(surv)}" aria-label="Survivor: ${formatInt(surv)}"><span class="archetype-seg-label">Survivor:</span><span class="archetype-seg-count">${formatInt(surv)}</span></div>
      <div class="archetype-seg archetype-seg--breakthrough" style="width: ${((brk / totalT) * 100).toFixed(2)}%;" title="Breakthrough: ${formatInt(brk)}" aria-label="Breakthrough: ${formatInt(brk)}"><span class="archetype-seg-label">Breakthrough:</span><span class="archetype-seg-count">${formatInt(brk)}</span></div>
      <div class="archetype-seg archetype-seg--trap" style="width: ${((trap / totalT) * 100).toFixed(2)}%;" title="Thrashing trap: ${formatInt(trap)}" aria-label="Thrashing trap: ${formatInt(trap)}"><span class="archetype-seg-label">Thrashing trap:</span><span class="archetype-seg-count">${formatInt(trap)}</span></div>
    `;
  }
  if (barLegend) {
    barLegend.innerHTML = `
      <li><span class="legend-swatch" style="background-color: #2ad089;"></span> Survivor: ${formatInt(surv)} (TYPE_A_SURVIVOR)</li>
      <li><span class="legend-swatch" style="background-color: #26d0ce;"></span> Breakthrough: ${formatInt(brk)} (TYPE_B_SYSTEMS_BREAKTHROUGH)</li>
      <li><span class="legend-swatch" style="background-color: #ff6b6b;"></span> Thrashing trap: ${formatInt(trap)} (TYPE_C_THRASHING_TRAP)</li>
    `;
  }

  // Context token saturation histogram
  const cd = deepData?.context_dynamics || {};
  const buckets = cd.token_saturation_buckets || [];
  const sim = cd.compaction_simulation || {};
  const pb = cd.protobuf_token_summary || {};

  if (ctxNote && buckets.length > 0) {
    ctxNote.textContent = `Across ${formatInt(cd.total_estimated_tokens)} estimated tokens (${formatInt(pb.sessions_with_protobuf_tokens)} protobuf-instrumented sessions), ${formatInt(sim.steps_exceeding_2kb)} steps exceed 2KB (${formatPct(sim.potential_savings_pct, 2)} potential token savings).`;
  }

  if (satSvg && buckets.length > 0) {
    satSvg.innerHTML = "";
    const W = 960;
    const H = 300;
    const pad = { top: 28, right: 44, bottom: 52, left: 64 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    const maxSess = Math.max(...buckets.map((b) => Number(b.sessions) || 0), 1);
    const maxErr = Math.max(...buckets.map((b) => Number(b.avg_errors) || 0), 1);
    const slotW = plotW / buckets.length;
    const barW = Math.min(82, slotW * 0.48);

    // Baseline gridlines
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + plotH - (i / 4) * plotH;
      const sessTick = Math.round((maxSess / 4) * i);
      satSvg.appendChild(svgEl("line", {
        x1: pad.left,
        y1: y,
        x2: W - pad.right,
        y2: y,
        stroke: "#1E2C47",
        "stroke-dasharray": i === 0 ? null : "4 4",
      }));
      satSvg.appendChild(svgEl("text", {
        x: pad.left - 10,
        y: y + 4,
        fill: "#9AA8BE",
        "text-anchor": "end",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 11,
      }, formatInt(sessTick)));
    }

    const errPoints = [];
    buckets.forEach((b, idx) => {
      const cx = pad.left + idx * slotW + slotW / 2;
      const barH = (Number(b.sessions) / maxSess) * plotH;
      const yBar = pad.top + plotH - barH;
      const yErr = pad.top + plotH - (Number(b.avg_errors) / maxErr) * (plotH * 0.9);
      errPoints.push(`${cx.toFixed(1)},${yErr.toFixed(1)}`);

      const g = svgEl("g", {
        tabindex: "0",
        role: "button",
        class: "chart-point-target",
        "aria-label": `${b.bucket}: ${formatInt(b.sessions)} sessions, ${Number(b.avg_errors).toFixed(2)} avg errors, ${Number(b.avg_interventions).toFixed(2)} avg interventions`,
      });

      g.appendChild(svgEl("rect", {
        x: (cx - barW / 2).toFixed(1),
        y: yBar.toFixed(1),
        width: barW.toFixed(1),
        height: barH.toFixed(1),
        rx: 4,
        fill: "#1B4DFF",
        opacity: "0.52",
      }));

      g.appendChild(svgEl("text", {
        x: cx.toFixed(1),
        y: pad.top + plotH + 22,
        fill: "#F4F6FA",
        "text-anchor": "middle",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 11,
      }, b.bucket));

      g.appendChild(svgEl("text", {
        x: cx.toFixed(1),
        y: pad.top + plotH + 38,
        fill: "#9AA8BE",
        "text-anchor": "middle",
        "font-family": "JetBrains Mono, monospace",
        "font-size": 10.5,
      }, `${Number(b.avg_errors).toFixed(2)} err / ${Number(b.avg_interventions).toFixed(2)} int`));

      const showBucket = () => {
        if (!satReadout) return;
        satReadout.textContent = `${b.bucket}: ${formatInt(b.sessions)} sessions | Avg steps: ${Number(b.avg_steps).toFixed(1)} | Avg errors: ${Number(b.avg_errors).toFixed(2)} | Avg interventions: ${Number(b.avg_interventions).toFixed(2)} | Avg tokens: ${formatInt(b.avg_tokens)}`;
      };
      g.addEventListener("mouseenter", showBucket);
      g.addEventListener("focus", showBucket);
      g.addEventListener("click", showBucket);
      satSvg.appendChild(g);
    });

    // Overlay average error escalation line
    satSvg.appendChild(svgEl("polyline", {
      points: errPoints.join(" "),
      fill: "none",
      stroke: "#FF6B6B",
      "stroke-width": 2.5,
      "stroke-linejoin": "round",
    }));
    buckets.forEach((b, idx) => {
      const cx = pad.left + idx * slotW + slotW / 2;
      const yErr = pad.top + plotH - (Number(b.avg_errors) / maxErr) * (plotH * 0.9);
      satSvg.appendChild(svgEl("circle", {
        cx: cx.toFixed(1),
        cy: yErr.toFixed(1),
        r: 4.5,
        fill: "#FF6B6B",
      }));
    });
  }

  if (satTbody) {
    satTbody.innerHTML = buckets.map((b) => `
      <tr>
        <td data-label="Token bucket"><code>${escapeHtml(b.bucket)}</code></td>
        <td data-label="Sessions">${formatInt(b.sessions)}</td>
        <td data-label="Avg steps">${Number(b.avg_steps || 0).toFixed(1)}</td>
        <td data-label="Avg errors">${Number(b.avg_errors || 0).toFixed(2)}</td>
        <td data-label="Avg interventions">${Number(b.avg_interventions || 0).toFixed(2)}</td>
        <td data-label="Avg tokens">${formatInt(b.avg_tokens)}</td>
      </tr>
    `).join("");
  }

  // Searchable / filterable Titan session table
  const allSessions = titan.sessions || [];

  function archetypeBadge(code) {
    if (code === "TYPE_A_SURVIVOR") {
      return '<span class="status-pill status-pill--pass">Survivor</span>';
    }
    if (code === "TYPE_B_SYSTEMS_BREAKTHROUGH") {
      return '<span class="status-pill status-pill--info">Breakthrough</span>';
    }
    return '<span class="status-pill status-pill--fail">Thrashing trap</span>';
  }

  function renderTitanTable() {
    if (!titanTbody) return;
    const query = (searchInput?.value || "").trim().toLowerCase();
    const arch = archSelect?.value || "all";

    const filtered = allSessions.filter((s) => {
      if (arch !== "all" && s.archetype !== arch) return false;
      if (!query) return true;
      const hay = `${s.session_short || ""} ${s.workspace_name || ""} ${s.start_date || ""}`.toLowerCase();
      return hay.includes(query);
    });

    if (countEl) {
      countEl.textContent = `Showing ${formatInt(filtered.length)} of ${formatInt(allSessions.length)} Titan sessions`;
    }

    if (filtered.length === 0) {
      titanTbody.innerHTML = `
        <tr>
          <td data-label="Session" colspan="9">No Titan sessions match the active filter.</td>
        </tr>
      `;
      return;
    }

    titanTbody.innerHTML = filtered.map((s) => `
      <tr>
        <td data-label="Session"><code>${escapeHtml(s.session_short)}</code></td>
        <td data-label="Archetype">${archetypeBadge(s.archetype)}</td>
        <td data-label="Steps">${formatInt(s.total_steps)}</td>
        <td data-label="Tool calls">${formatInt(s.tool_calls)}</td>
        <td data-label="Error rate">${formatPct(s.error_rate_pct, 2)}</td>
        <td data-label="Interventions / 100">${Number(s.interventions_per_100_steps || 0).toFixed(2)}</td>
        <td data-label="Duration (h)">${Number(s.duration_hours || 0).toFixed(1)}</td>
        <td data-label="Workspace"><code>${escapeHtml(s.workspace_name)}</code></td>
        <td data-label="Date">${escapeHtml(s.start_date)}</td>
      </tr>
    `).join("");
  }

  if (searchInput) searchInput.addEventListener("input", renderTitanTable);
  if (archSelect) archSelect.addEventListener("change", renderTitanTable);
  renderTitanTable();
}

async function bootTelemetryObservatory() {
  try {
    const [manifest, overview, fleet, eras, models, deep] = await Promise.all([
      fetchBundle("manifest.json"),
      fetchBundle("overview.json"),
      fetchBundle("fleet_and_team.json"),
      fetchBundle("eras.json"),
      fetchBundle("models.json"),
      fetchBundle("deep_metrics.json"),
    ]);

    hydrateKpisAndProvenance(manifest, overview, fleet);
    initEraChart(eras);
    initModelChart(models);
    initCompactorSimulator(deep);
    initTitanAndSaturation(deep);
  } catch (err) {
    const readout = document.getElementById("era-chart-readout");
    if (readout) {
      readout.textContent = `Unable to load telemetry JSON bundles (${err.message}). Serve the website directory over HTTP to enable dynamic charts.`;
    }
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootTelemetryObservatory, { once: true });
} else {
  bootTelemetryObservatory();
}
