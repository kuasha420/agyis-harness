# 🏛️ Empirical Project Rules & Skills Ecosystem Audit
**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Generated At**: 2026-10-02 04:52:22Z  
**Data Source**: Cross-analysis of repository configuration files (`AGENTS.md`, `.agents/skills`) vs. session telemetry in `data/telemetry.db`

---

## Executive Summary: The Context Calibration Invariant

Agent autonomy, error rates, and human intervention frequency are **heavily governed by the quality, calibration, and architecture of the project's rules and skills**. 

When we evaluate the agent's behavior across distinct workspaces on this workstation, failures are rarely "pure model hallucinations"—they correlate directly with **harness misconfigurations, rule indirection, contradictory constraints, or missing domain commands**.

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Workspace Performance & Rule Calibration                        │
├──────────────────────────────┬────────────┬───────────┬────────────┬───────────────────┤
│ Workspace                    │ Sessions   │ Error %   │ Interv/Sess│ Rule Architecture │
├──────────────────────────────┼────────────┼───────────┼────────────┼───────────────────┤
| `sunshine-physio-universalapp` | 99 | 1.98% | 1.91 | 2 files (~6069 tok), 3 skills |
| `Jasper` | 72 | 3.63% | 3.15 | 7 files (~3635 tok), 26 skills |
| `purrmission` | 55 | 3.83% | 1.67 | 9 files (~5076 tok), 0 skills |
| `knot-mesh` | 28 | 3.24% | 5.79 | 5 files (~6786 tok), 7 skills |
| `mm-website` | 20 | 5.68% | 18.2 | 6 files (~3036 tok), 0 skills |
| `jimha` | 17 | 2.63% | 1.41 | 0 files (~0 tok), 0 skills |
| `knot` | 12 | 3.29% | 16.5 | None / Undetected |
| `purr` | 10 | 4.02% | 22.3 | 1 files (~1208 tok), 3 skills |
| `react-native-template-ts-plus` | 4 | 7.92% | 3.75 | 2 files (~1560 tok), 1 skills |
| `psl-website` | 4 | 4.68% | 16.5 | 6 files (~3307 tok), 0 skills |
| `purrmission-worktrees` | 2 | 2.14% | 11.0 | 3 files (~2162 tok), 0 skills |
| `purrfectcore-001` | 2 | 6.56% | 0.0 | 6 files (~3021 tok), 0 skills |
| `purrfectcore-client` | 1 | 0.0% | 0.0 | 6 files (~3139 tok), 2 skills |
| `purr-aurora` | 1 | 3.37% | 14.0 | None / Undetected |
| `p` | 1 | 8.33% | 3.0 | None / Undetected |
| `kno` | 1 | 6.45% | 9.0 | None / Undetected |
| `8-Ball-Pool-Guide-Line` | 1 | 4.95% | 36.0 | 0 files (~0 tok), 0 skills |
└──────────────────────────────┴────────────┴───────────┴────────────┴───────────────────┘
```

---

## 🔍 Deep-Dive: 4 Architectural Ecosystem Profiles

### Profile 1: The Golden Monorepo (`sunshine-physio-universalapp`)
* **Metrics**: **99 sessions**, **326.1 avg steps**, **2.0% error rate**, **1.91 interventions/session**.
* **Configuration Shape**:
  - Root `AGENTS.md` (2,735 tokens) with razor-sharp monorepo boundaries (`packages/shared`, `apps/api`, `apps/web`).
  - **Explicit Testing & DB Contracts**: Exact port defined (`Local PostgreSQL runs on port 5436`), exact migrations (`pnpm db:generate`, `pnpm db:migrate`), exact router abstraction (`createRouter()`).
  - **Strict Architectural Decision Tree**: Bound to an ultra-compact canonical cheat-sheet under 50 lines.
  - **Why It Succeeded**: The agent never had to probe ports, guess database commands, or invent validation layers. Autonomy remained consistently high over 99 multi-step sessions.

---

### Profile 2: The Explicit Command Dictionary (`purrmission`)
* **Metrics**: **55 sessions**, **160.7 avg steps**, **3.8% error rate**, **1.67 interventions/session** (Lowest intervention rate among active multi-task repos).
* **Configuration Shape**:
  - Root `AGENTS.md` with an **explicit command dictionary**:
    ```bash
    pnpm --filter @purrfecthq/purrmission-bot test
    pnpm --filter @psl-oss/pawthy test
    pnpm prisma:generate
    node scripts/gh-pr-review-comments.cjs
    ```
  - **Why It Succeeded**: Providing explicit, copy-pasteable CLI invocations eliminated Exit Code 127 (`command not found`) and Exit Code 2 (`syntax error`). The agent executed the exact filters required by the monorepo instead of guessing root npm commands.

---

### Profile 3: The Rule Fragmentation Trap (`mm-website`)
* **Metrics**: **20 sessions**, **858.1 avg steps**, **5.7% error rate**, **18.2 interventions/session** (**10x higher intervention rate** than Profile 1!).
* **Configuration Shape**:
  - Root `AGENTS.md` contained no inline technical specifications. Instead, it instructed the agent:
    ```markdown
    Start with these rule files before making changes:
    - .agent/rules/README.md
    - .agent/rules/overview.md
    - .agent/rules/development.md
    - .agent/rules/code-review.md
    - .agent/rules/workflow.md
    ```
  - **The Failure Mode**: The agent spent dozens of steps opening and reading 5 separate markdown documents (`view_file` loops), consuming 40k+ tokens before understanding the project context.
  - Furthermore, when the user asked the agent to deploy staging infrastructure (Coolify, Debian, Podman), the rules provided **zero remote-execution guidelines**, causing repeated `apt-get` non-interactive hangs and SSH connection drops.

---

### Profile 4: Deep Systems & Physical Hardware Mesh (`knot-mesh` & `purr`)
* **Metrics**:
  - `knot-mesh`: **28 sessions**, **616.5 avg steps**, **5.79 interventions/session**.
  - `purr`: **10 sessions**, **1,106.5 avg steps**, **22.3 interventions/session**.
* **Configuration Shape**:
  - Highly sophisticated system invariants (KDE Plasma 6 DBus script evaluation, Arch Linux pacman/yay non-interactive flags, Waydroid container preservation, Knot mesh multi-node topologies).
  - Dedicated skills: `subagent-ladder`, `core-mesh`, `knot-swarm`, `arch-kde-devops`.
* **Why Interventions Were High**:
  - **Legitimate Human-in-the-Loop Boundaries**: In `purr` and `knot-mesh`, interventions were not agent incompetence. They were **mandatory safety gates** for sudo passwords, pacman lock releases, physical display verification across hardware nodes (Steam Deck, ROG Ally, Laptop), and GPG signed commits.
  - **The Rule 1 Friction**: `knot-mesh` enforced an "Absolute ban on `|| true`". However, when the agent executed benign probe commands like `git diff | grep -i secret`, `grep` exited with code `1`, causing the agent to panic and seek rescue.

---

## 💡 Key Empirical Discoveries & Root Causes

### 1. The "Explicit Command Dictionary" Advantage
Repositories that declare the exact test, lint, and build commands in `AGENTS.md` (e.g. `purrmission`, `sunshine-physio`) see **50% fewer command errors** than repositories that assume the agent can infer Turborepo or npm filter syntax.

### 2. Multi-File Indirection is a Context Trap
Forcing the agent to traverse multiple `.agent/rules/*.md` files leads directly to:
1. Redundant `view_file` tool loops (the 3,951 loop calls noted in the baseline audit).
2. Premature context window saturation before the task even begins.
3. Information loss as rule content gets pushed beyond the attention boundary.
*Recommendation*: **Consolidate all essential invariants into a single root `AGENTS.md` under 200 lines.**

### 3. Rigid Negative Rules Need Probing Exceptions
Banning `|| true` without distinguishing between **production code** and **agent terminal inspection** created false-positive exit code 1 failures. The rule must explicitly distinguish:
- *Prohibited*: Swallowing errors in production code, build scripts, or CI checks.
- *Permitted/Encouraged*: Probing pattern matches where zero results is a valid outcome (`grep -E 'pattern' || true`).

---

## 🛠️ Recommendations for `psl-agy-harness`

1. **Rule Linter & Compactor Tool (`psl-lint-rules`)**:
   - Provide a CLI tool that inspects a repo's `AGENTS.md` and flags multi-file rule indirection, missing command dictionaries, and uncalibrated exit-code prohibitions.
2. **Context-Injected Command Palettes**:
   - Automatically expose the repo's primary scripts from `package.json` / `Makefile` / `pyproject.toml` as a structured palette so agents never guess invocations.
3. **Calibrated Reference `AGENTS.md`**:
   - Merge the best-in-class patterns from `sunshine-physio` (The 5 Ground Rules) and `purrmission` (Explicit Command Dictionary) into our reference harness rules.
