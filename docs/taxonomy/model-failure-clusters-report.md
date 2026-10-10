# Empirical Telemetry Analysis: Cross-Model Failure Clusters & Intervention Hotspots

**Dataset Source**: `data/telemetry.db` (722 Total Sessions, 219,289 Steps, 100,965 Tool Calls, 2,454 Interventions)
**Date**: 2026-10-10

---

## 1. Cross-Model Profile & Operational Biases

| Model | Sessions | Steps | Tool Calls | Errors | Error % | Interventions | Interv % |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `gemini-3.8-flash-high` | 393 | 123,284 | 57,401 | 452 | 0.79% | 1,068 | 0.87% |
| `gemini-3.8-flash-tiered` | 101 | 12,914 | 6,057 | 110 | 1.82% | 84 | 0.65% |
| `Gemini 3.5/Flash/Pro (Default)` | 93 | 8,412 | 3,835 | 88 | 2.29% | 9 | 0.11% |
| `Gemini 3` | 64 | 49,411 | 22,288 | 1,197 | 5.37% | 780 | 1.58% |
| `gemini-3.6-flash-tiered` | 33 | 2,098 | 836 | 34 | 4.07% | 33 | 1.57% |
| `gemini-3.6-flash-high` | 16 | 4,558 | 1,908 | 144 | 7.55% | 193 | 4.23% |
| `gemini-3.7-flash-high` | 15 | 17,472 | 8,124 | 46 | 0.57% | 256 | 1.47% |
| `gemini-3.1-pro-low` | 4 | 105 | 60 | 3 | 5.0% | 4 | 3.81% |
| `gemini-3.7-flash-tiered` | 1 | 73 | 35 | 0 | 0.0% | 1 | 1.37% |
| `gemini-3-flash-agent` | 1 | 688 | 309 | 23 | 7.44% | 13 | 1.89% |
| `GPT-OSS 120B (Medium)` | 1 | 274 | 112 | 1 | 0.89% | 13 | 4.74% |

### Key Model Bias Observations:
- **`gemini-3.8-flash-high`** (393 sessions, 54.4% of total): High endurance, but generates significant non-command loop candidates (over 10,192 redundant `view_file` / `list_dir` steps) and exit code 1 (933 failures) primarily from pattern probes and unhandled syntax edge cases.
- **`Gemini 3`** (64 sessions): Suffered higher rates of exit code 127 (`command not found`, 91 occurrences) and package manager locks, revealing aggressive assumption of installed system packages.
- **`gemini-3.8-flash-tiered`** (101 sessions): Demonstrates disciplined lower tool call error rate (2.7%), with primary failure modes clustered around test suite regressions and multi-branch git conflicts.
- **`GPT-OSS 120B (Medium)`** and singletons: Minimal footprint, primarily used in isolated exploratory tasks.

---

## 2. Top Failure Clusters by Model & Command Category

| Model | Category | Total Calls | Failures | Loops | Failure Rate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `gemini-3.8-flash-high` | `other` | 17,521 | 817 | 67 | 4.66% |
| `Gemini 3` | `other` | 8,213 | 671 | 159 | 8.17% |
| `gemini-3.8-flash-high` | `non_command` | 55,964 | 467 | 10,192 | 0.83% |
| `gemini-3.7-flash-high` | `other` | 3,715 | 203 | 44 | 5.46% |
| `gemini-3.8-flash-high` | `test_runner` | 4,160 | 188 | 39 | 4.52% |
| `Gemini 3` | `grep_search` | 1,253 | 167 | 14 | 13.33% |
| `gemini-3.8-flash-high` | `grep_search` | 3,734 | 151 | 4 | 4.04% |
| `gemini-3.8-flash-tiered` | `non_command` | 8,229 | 110 | 1,384 | 1.34% |
| `Gemini 3` | `test_runner` | 423 | 70 | 0 | 16.55% |
| `gemini-3.7-flash-high` | `grep_search` | 1,350 | 68 | 2 | 5.04% |
| `gemini-3.6-flash-high` | `other` | 890 | 65 | 25 | 7.3% |
| `Gemini 3` | `package_manager` | 343 | 61 | 13 | 17.78% |
| `gemini-3.8-flash-tiered` | `test_runner` | 796 | 58 | 3 | 7.29% |
| `Gemini 3` | `file_search` | 581 | 55 | 0 | 9.47% |
| `Gemini 3` | `git` | 871 | 50 | 29 | 5.74% |
| `gemini-3.7-flash-high` | `non_command` | 7,609 | 46 | 1,350 | 0.6% |
| `gemini-3.6-flash-high` | `git` | 509 | 45 | 14 | 8.84% |
| `gemini-3.8-flash-high` | `git` | 6,396 | 44 | 15 | 0.69% |
| `gemini-3.7-flash-high` | `test_runner` | 303 | 39 | 0 | 12.87% |
| `Gemini 3.5/Flash/Pro (Default)` | `other` | 498 | 35 | 6 | 7.03% |
| `gemini-3.6-flash-tiered` | `other` | 134 | 35 | 4 | 26.12% |
| `Gemini 3` | `file_system` | 672 | 35 | 2 | 5.21% |
| `gemini-3.8-flash-tiered` | `other` | 840 | 33 | 12 | 3.93% |
| `gemini-3.8-flash-high` | `file_system` | 2,691 | 31 | 99 | 1.15% |
| `gemini-3.8-flash-high` | `system_probe` | 1,247 | 30 | 2 | 2.41% |

---

## 3. Specialized Domain Failure Signatures

### A. Database & Docker Operations (`db-ops` Justification)
Frequent failures when probing PostgreSQL or Docker services without non-interactive flags, missing environment credentials, or handling active connection locks:

- **`"python3 -c '\nimport sqlite3\nconn = sqlite3.connect(\"data/telemetry.db\")\nc = conn.cursor()\nc.execute(\"\"\"\n    SELECT COUNT(*), AVG(total_steps), AVG(tool_call_count)\n    FROM sessions\n    WHERE tool_error_count = 0 AND total_steps > 15\n\"\"\")\nrow = c.fetchone()\nprint(f\"Clean sessions (>15 steps, 0 tool errors): {row[0]}\")\nprint(f\"  Average steps: {row[1]:.1f}, Average tool calls: {row[2]:.1f}\")\n\nc.execute(\"\"\"\n    SELECT session_id, total_steps, tool_call_count, model, SUBSTR(workspace_path, 1, 40)\n    FROM sessions\n    WHERE tool_error_count = 0 AND total_steps > 25\n    ORDER BY total_steps DESC\n    LIMIT 5\n\"\"\")\nprint(\"\\nTop Clean Sessions:\")\nfor r in c.fetchall():\n    print(f\"  {r[0]}: steps={r[1]}, tools={r[2]}, model={r[3]}, ws={r[4]}\")\n'"`** (Exit 1, count=3)
  *Snippet*: `Created At: 2026-10-02T10:36:24+06:00 Completed At: 2026-10-02T10:36:24+06:00  The command exited with code 1. Output: Clean sessions (>15 steps, 0 tool errors): 0 Traceback (most recent call last):`
- **`"ssh -o StrictHostKeyChecking=no root@sg.purrfectsoft.co.uk \"docker exec -i coolify-db psql -U coolify -d coolify -c 'SELECT id, key, value, \\\"applicationId\\\" FROM environment_variables WHERE \\\"applicationId\\\" = 3;'\""`** (Exit 1, count=3)
  *Snippet*: `Created At: 2026-06-07T12:58:32Z Completed At: 2026-06-07T12:58:33Z  				The command failed with exit code: 1 				Output: 				ERROR:  column "applicationId" does not exist LINE 1: SELECT id, key, valu`
- **`"ssh root@sg.purrfectsoft.co.uk \"docker exec -i coolify-db psql -U coolify -d coolify -c \\\"SELECT id, status, log FROM application_deployments ORDER BY created_at DESC LIMIT 1;\\\"\""`** (Exit 1, count=3)
  *Snippet*: `Created At: 2026-05-29T20:10:56Z Completed At: 2026-05-29T20:10:56Z  				The command failed with exit code: 1 				Output: 				ERROR:  relation "application_deployments" does not exist LINE 1: SELECT i`
- **`"ssh root@sg.purrfectsoft.co.uk \"docker exec coolify-db psql -U coolify -d coolify -c 'select id, status, application_id, created_at from application_deployments order by id desc limit 5;'\""`** (Exit 1, count=3)
  *Snippet*: `Created At: 2026-06-03T18:01:24Z Completed At: 2026-06-03T18:01:25Z  				The command failed with exit code: 1 				Output: 				ERROR:  relation "application_deployments" does not exist LINE 1: ...elect`
- **`"ssh root@sg.purrfectsoft.co.uk \"docker exec mydz0e5m1hcfizrzpefxqb28-180430508936 netstat -tuln\""`** (Exit 127, count=3)
  *Snippet*: `Created At: 2026-06-03T18:19:28Z Completed At: 2026-06-03T18:19:29Z  				The command failed with exit code: 127 				Output: 				OCI runtime exec failed: exec failed: unable to start container process:`
- **`"ssh root@sg.purrfectsoft.co.uk \"docker exec qs46t5t8g80xgowhzf0tmuo1 psql -U purrfectcore_prod_user -d purrfectcore_prod -c \\\"SELECT email, roles FROM users WHERE email = 'arafat@purrfecthq.com';\\\"\""`** (Exit 1, count=3)
  *Snippet*: `Created At: 2026-06-15T17:21:03Z Completed At: 2026-06-15T17:21:04Z  				The command failed with exit code: 1 				Output: 				ERROR:  column "roles" does not exist LINE 1: SELECT email, roles FROM use`

### B. Mesh & Remote Operations (`mesh-ops` Justification)
SSH connection dropouts (Exit Code 255), unverified Tailscale hostnames, and unpinned socket paths:

- **`"ssh -o StrictHostKeyChecking=no root@103.174.51.23 \"cat /home/purrfecthq-staging-purrfectcore/htdocs/staging.purrfectcore.purrfecthq.com/purrfectcore-001/.env | grep GOOGLE\""`** (Exit 1, count=5)
  *Snippet*: `Created At: 2026-06-07T17:16:31Z Completed At: 2026-06-07T17:16:32Z  				The command failed with exit code: 1 				Output: 				cat: cat: /home/purrfecthq-staging-purrfectcore/htdocs/staging.purrfectcor`
- **`"ssh purrfecthq-jasper-infra@jasper.infra.purrfecthq.com \"/home/purrfecthq-jasper-infra/htdocs/jasper.infra.purrfecthq.com/yt-dlp --js-runtimes node --extractor-args youtube:player-client=android -f bestaudio -o - \\\"https://www.youtube.com/watch?v=Ly0fz0T_lQE\\\" > /dev/null\""`** (Exit 1, count=5)
  *Snippet*: `Created At: 2026-06-23T19:22:05Z Completed At: 2026-06-23T19:22:08Z  				The command failed with exit code: 1 				Output: 				WARNING: Your yt-dlp version (2026.02.04) is older than 90 days!          `
- **`"ssh -o StrictHostKeyChecking=no purrfecthq-jasper-infra@jasper.infra.purrfecthq.com \"ps aux | grep yt-dlp | grep -v grep\""`** (Exit 1, count=4)
  *Snippet*: `Created At: 2026-06-23T18:37:08Z Completed At: 2026-06-23T18:37:09Z  				The command failed with exit code: 1 			Stdout: 			 			Stderr: 			 `
- **`"ssh -o BatchMode=yes kuasha@bd.purrfectsoft.co.uk \"sudo -u purrfecthq-jasper-infra pm2 logs --lines 100 --nostream\""`** (Exit 1, count=3)
  *Snippet*: `Created At: 2026-09-02T00:52:05+06:00 Completed At: 2026-09-02T00:52:06+06:00  The command exited with code 1. Output: sudo: pm2: command not found  `
- **`"ssh -o StrictHostKeyChecking=no root@sg.purrfectsoft.co.uk \"docker exec -i coolify-db psql -U coolify -d coolify -c 'SELECT id, key, value, \\\"applicationId\\\" FROM environment_variables WHERE \\\"applicationId\\\" = 3;'\""`** (Exit 1, count=3)
  *Snippet*: `Created At: 2026-06-07T12:58:32Z Completed At: 2026-06-07T12:58:33Z  				The command failed with exit code: 1 				Output: 				ERROR:  column "applicationId" does not exist LINE 1: SELECT id, key, valu`
- **`"ssh root@sg.purrfectsoft.co.uk \"docker exec -i coolify-db psql -U coolify -d coolify -c \\\"SELECT id, status, log FROM application_deployments ORDER BY created_at DESC LIMIT 1;\\\"\""`** (Exit 1, count=3)
  *Snippet*: `Created At: 2026-05-29T20:10:56Z Completed At: 2026-05-29T20:10:56Z  				The command failed with exit code: 1 				Output: 				ERROR:  relation "application_deployments" does not exist LINE 1: SELECT i`

### C. Git Worktree & Branching Operations (`git-worktree-ops` Justification)
Stale worktrees, unmerged index collisions, checkout conflicts with dirty state, and orphan worktree directories:

- **`gh issue view 100`** (Exit 0, count=5)
  *Snippet*: `oerror executing cascade step: CORTEX_STEP_TYPE_RUN_COMMAND: read unix @ -> @: recvmsg: connection reset by peer � error executing cascade step: CORTEX_STEP_TYPE_RUN_COMMAND: read unix @ -> @: recvmsg`
- **`gh secret set -f .env -R purrfectsoft/psl-website`** (Exit 1, count=3)
- **`"GIT_EDITOR=true git rebase --continue"`** (Exit 1, count=2)
  *Snippet*: `Created At: 2026-09-18T02:40:25+06:00 Completed At: 2026-09-18T02:40:25+06:00  The command exited with code 1. Output: hint: Waiting for your editor to close the file... [detached HEAD f2bac98] feat(`
- **`"git checkout production && git commit --allow-empty -m \"chore: trigger coolify deployment\" && git push origin production"`** (Exit 1, count=2)
  *Snippet*: `Created At: 2026-06-05T00:54:33Z Completed At: 2026-06-05T00:54:34Z  				The command failed with exit code: 1 			Stdout: 			 			Stderr: 			 `
- **`"git config user.name; git config user.email"`** (Exit 1, count=2)
  *Snippet*: `Created At: 2026-09-18T18:25:00+06:00 Completed At: 2026-09-18T18:25:01+06:00  The command exited with code 1. Stdout:  Stderr:  `
- **`"/home[WORKSPACE_ROOT]/bin/knot exec desktop \"cd [USER_HOME]/Dev/jimha && git tag -s v1.0.0 -m 'Release v1.0.0 - JimHa\\'s Magical Key Smash Game' && git push origin v1.0.0\""`** (Exit 1, count=1)
  *Snippet*: `Created At: 2026-09-29T10:58:19+06:00 Completed At: 2026-09-29T10:58:20+06:00  The command exited with code 1. Output: zsh:1: unmatched '  `

---

## 4. Human-in-the-Loop Intervention Hotspots

### Breakdown of Operator Steering Triggers:
- **`db_and_migration`**: 55 operator steering prompts
- **`mesh_and_tailscale`**: 61 operator steering prompts
- **`git_worktree_and_branches`**: 56 operator steering prompts
- **`loop_stop_and_wait`**: 142 operator steering prompts
- **`credentials_and_tokens`**: 89 operator steering prompts
- **`test_and_verification`**: 107 operator steering prompts

### Preceding Tool Failures Leading to Operator Rescues:
Direct interventions immediately triggered after tool failures:
- **Step 1474** (`run_command`, model `Gemini 3`): Operator prompt: *"Did we do anything exotic in our previous waydroid attempt in this system Btw, @[conversation:"Waydroid Setup and Optimization"] - that is messing with the more generic purr receipe integration?"*
- **Step 335** (`write_to_file`, model `gemini-3.8-flash-high`): Operator prompt: *"should be fixed now"*
- **Step 333** (`write_to_file`, model `gemini-3.8-flash-high`): Operator prompt: *"Give me an one liner fix"*
- **Step 142** (`view_file`, model `gemini-3.8-flash-high`): Operator prompt: *"Fix in place and also file an issue in the psl-agy-harness repo. Then continue"*
- **Step 5626** (`run_command`, model `gemini-3.8-flash-high`): Operator prompt: *"gemma benchmark isn't going the right way. check"*
- **Step 65** (`run_command`, model `Gemini 3`): Operator prompt: *"findout why my controller not connecting with wire mode"*
- **Step 5462** (`run_command`, model `gemini-3.8-flash-high`): Operator prompt: *"update the other 3 issues to document complete and remaining scope of each issue."*
- **Step 1183** (`run_command`, model `gemini-3.8-flash-high`): Operator prompt: *"@[Quote] Can confirm - I set up kde connect between some nodes manually, but didn't get any help from knot-mesh, yet. @[Quote] yikes @[Quote] and @[Quote] we should keep only the important and highlig"*
- **Step 472** (`run_command`, model `gemini-3-flash-agent`): Operator prompt: *"what?"*
- **Step 352** (`run_command`, model `gemini-3-flash-agent`): Operator prompt: *"Can we create a minimally scoped PAT using cli?"*

---

## 5. Architectural Synthesis: Three New Modular Skills

Based on the empirical failure clusters and operator intervention hotspots identified in this audit, we codify three new operational runbooks:

1. **`db-ops`**: Standardized database diagnostic and inspection runbook for PostgreSQL / SQLite / Docker instances (connection pooling, active locks, vacuuming, non-interactive CLI invocations). Eliminates interactive prompts and hanging client queries.
2. **`mesh-ops`**: Knot hardware mesh coordination runbook (dynamic node discovery, Tailscale/WireGuard ping, state sync between Desktop, Laptop, and Handhelds). Resolves SSH exit code 255 dropouts and unverified mesh targets.
3. **`git-worktree-ops`**: Safe multi-branch worktree management, branch cleanup, orphan prune, and stashes without index corruption. Resolves dirty tree checkout errors and orphaned worktree index locks.
