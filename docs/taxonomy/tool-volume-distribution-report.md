<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 📊 Empirical Tool & Command Character Volume Distribution Report
**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**Generated At**: 2026-10-18T16:58:24.949747+00:00  
**Data Source**: Workstation telemetry database (`data/telemetry.db`) across all ingested developer sessions  

---

## 1. Executive Summary & Aggregate Payload Volume

- **Total Tool Executions Analyzed**: **236,847** calls
- **Total Tool Output Volume**: **262,442,929** characters (~**65,610,732** estimated tokens)
- **Total Arguments Payload**: **168,195,833** characters (~**42,048,958** estimated tokens)
- **Platform-Truncated Outputs**: **17,899** calls (7.56% of all calls)
- **Tool Failure Invariant Count**: **6,166** calls strictly exempted from compaction

```text
┌────────────────────────────────────────────────────────────────────────┐
│                 MACRO PAYLOAD VOLUME BREAKDOWN                         │
├───────────────────────────────┬───────────────────┬────────────────────┤
│ Metric                        │ Characters        │ Estimated Tokens   │
├───────────────────────────────┼───────────────────┼────────────────────┤
│ Tool Results / Output         │       262,442,929 │         65,610,732 │
│ Tool Arguments / Input        │       168,195,833 │         42,048,958 │
│ Combined Tool Payload         │       430,638,762 │        107,659,690 │
└───────────────────────────────┴───────────────────┴────────────────────┘
```

---
## 2. Per-Tool Volume & Percentile Distribution

Tools sorted by total output volume impact:

| Tool Name | Calls | Total Chars | Avg Chars | Median | p90 | p99 | Max Chars | >2KB % |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `view_file` | 69,818 | 147,213,062 | 2,108.5 | 1,143 | 4,120 | 18,169 | 50,620 | 38.57% |
| `run_command` | 101,677 | 78,526,255 | 772.3 | 161 | 2,697 | 8,073 | 8,360 | 12.62% |
| `replace_file_content` | 14,721 | 14,614,245 | 992.7 | 833 | 2,659 | 4,121 | 10,239 | 15.41% |
| `grep_search` | 11,416 | 7,712,854 | 675.6 | 16 | 2,459 | 7,465 | 10,239 | 11.46% |
| `manage_task` | 8,073 | 3,032,494 | 375.6 | 0 | 1,302 | 1,563 | 4,120 | 0.06% |
| `list_dir` | 4,097 | 2,640,730 | 644.6 | 207 | 1,272 | 10,238 | 10,239 | 6.47% |
| `write_to_file` | 13,367 | 2,612,788 | 195.5 | 231 | 315 | 509 | 3,067 | 0.01% |
| `manage_subagents` | 1,898 | 1,735,006 | 914.1 | 368 | 3,128 | 5,220 | 7,637 | 18.12% |
| `search_web` | 914 | 1,686,871 | 1,845.6 | 1,810 | 4,120 | 5,416 | 6,739 | 47.16% |
| `find_by_name` | 2,648 | 792,219 | 299.2 | 83 | 1,032 | 2,556 | 4,119 | 1.74% |
| `schedule` | 2,274 | 510,897 | 224.7 | 28 | 612 | 746 | 4,120 | 0.04% |
| `invoke_subagent` | 1,258 | 450,790 | 358.3 | 453 | 1,028 | 1,676 | 4,113 | 0.08% |
| `multi_replace_file_content` | 158 | 328,402 | 2,078.5 | 1,881 | 4,114 | 4,120 | 4,120 | 45.57% |
| `send_message` | 3,331 | 189,721 | 57.0 | 55 | 133 | 133 | 4,113 | 0.03% |
| `call_mcp_tool` | 218 | 131,655 | 603.9 | 190 | 2,494 | 4,093 | 4,120 | 10.55% |
| `mcp_chrome_devtools_evaluate_script` | 102 | 78,696 | 771.5 | 0 | 3,115 | 4,567 | 10,184 | 14.71% |
| `list_permissions` | 16 | 56,918 | 3,557.4 | 3,746 | 4,055 | 4,118 | 4,118 | 93.75% |
| `ask_question` | 352 | 49,949 | 141.9 | 0 | 355 | 884 | 4,120 | 0.57% |
| `read_url_content` | 152 | 35,588 | 234.1 | 318 | 458 | 717 | 1,459 | 0.0% |
| `mcp_chrome_devtools_take_screenshot` | 82 | 9,363 | 114.2 | 0 | 255 | 265 | 265 | 0.0% |
| `ask_permission` | 10 | 5,004 | 500.4 | 0 | 611 | 4,120 | 4,120 | 10.0% |
| `mcp_chrome_devtools_list_network_requests` | 4 | 4,949 | 1,237.2 | 0 | 3,306 | 3,306 | 3,306 | 25.0% |
| `mcp_chrome_devtools_navigate_page` | 43 | 4,782 | 111.2 | 0 | 222 | 552 | 552 | 0.0% |
| `define_subagent` | 45 | 3,784 | 84.1 | 82 | 177 | 234 | 234 | 0.0% |
| `mcp_chrome_devtools_click` | 54 | 3,322 | 61.5 | 0 | 113 | 293 | 293 | 0.0% |
| `mcp_chrome_devtools_wait_for` | 2 | 3,169 | 1,584.5 | 0 | 3,169 | 3,169 | 3,169 | 50.0% |
| `generate_image` | 2 | 2,330 | 1,165.0 | 936 | 1,394 | 1,394 | 1,394 | 0.0% |
| `mcp_chrome_devtools_get_network_request` | 2 | 2,085 | 1,042.5 | 0 | 2,085 | 2,085 | 2,085 | 50.0% |
| `mcp_chrome_devtools_resize_page` | 17 | 1,537 | 90.4 | 0 | 214 | 498 | 498 | 0.0% |
| `list_resources` | 24 | 1,049 | 43.7 | 0 | 132 | 132 | 132 | 0.0% |
| `mcp_chrome_devtools_list_console_messages` | 5 | 600 | 120.0 | 125 | 262 | 262 | 262 | 0.0% |
| `mcp_chrome_devtools_fill` | 8 | 452 | 56.5 | 0 | 113 | 113 | 113 | 0.0% |
| `mcp_chrome_devtools_list_pages` | 6 | 432 | 72.0 | 0 | 214 | 214 | 214 | 0.0% |
| `mcp_chrome_devtools_emulate` | 2 | 235 | 117.5 | 0 | 235 | 235 | 235 | 0.0% |
| `mcp_chrome_devtools_select_page` | 2 | 214 | 107.0 | 0 | 214 | 214 | 214 | 0.0% |
| `mcp_chrome_devtools_new_page` | 2 | 191 | 95.5 | 0 | 191 | 191 | 191 | 0.0% |
| `mcp_chrome_devtools_fill_form` | 2 | 110 | 55.0 | 0 | 110 | 110 | 110 | 0.0% |
| `mcp_chrome_devtools_close_page` | 1 | 95 | 95.0 | 95 | 95 | 95 | 95 | 0.0% |
| `browser_subagent` | 1 | 86 | 86.0 | 86 | 86 | 86 | 86 | 0.0% |
| `browser_get_dom` | 2 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `browser_navigate` | 4 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `chrome_devtools:navigate_page` | 4 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `click` | 2 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `command_status` | 30 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `kill_all` | 1 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |


### Size Bucket Distribution by Tool

| Tool Name | < 500 B | 500 B – 2 KB | 2 KB – 10 KB | 10 KB – 50 KB | > 50 KB |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `view_file` | 32,139 | 10,747 | 25,210 | 1,722 | 0 |
| `run_command` | 68,911 | 19,937 | 12,829 | 0 | 0 |
| `replace_file_content` | 6,656 | 5,797 | 2,268 | 0 | 0 |
| `grep_search` | 8,575 | 1,533 | 1,308 | 0 | 0 |
| `manage_task` | 5,558 | 2,510 | 5 | 0 | 0 |
| `list_dir` | 3,243 | 589 | 265 | 0 | 0 |
| `write_to_file` | 13,048 | 318 | 1 | 0 | 0 |
| `manage_subagents` | 1,181 | 373 | 344 | 0 | 0 |
| `search_web` | 401 | 82 | 431 | 0 | 0 |
| `find_by_name` | 2,149 | 453 | 46 | 0 | 0 |
| `schedule` | 1,623 | 650 | 1 | 0 | 0 |
| `invoke_subagent` | 804 | 453 | 1 | 0 | 0 |
| `multi_replace_file_content` | 17 | 69 | 72 | 0 | 0 |
| `send_message` | 3,330 | 0 | 1 | 0 | 0 |
| `call_mcp_tool` | 172 | 23 | 23 | 0 | 0 |
| `mcp_chrome_devtools_evaluate_script` | 74 | 13 | 15 | 0 | 0 |
| `list_permissions` | 1 | 0 | 15 | 0 | 0 |
| `ask_question` | 345 | 5 | 2 | 0 | 0 |
| `read_url_content` | 148 | 4 | 0 | 0 | 0 |
| `mcp_chrome_devtools_take_screenshot` | 82 | 0 | 0 | 0 | 0 |
| `ask_permission` | 8 | 1 | 1 | 0 | 0 |
| `mcp_chrome_devtools_list_network_requests` | 2 | 1 | 1 | 0 | 0 |
| `mcp_chrome_devtools_navigate_page` | 42 | 1 | 0 | 0 | 0 |
| `define_subagent` | 45 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_click` | 54 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_wait_for` | 1 | 0 | 1 | 0 | 0 |
| `generate_image` | 0 | 2 | 0 | 0 | 0 |
| `mcp_chrome_devtools_get_network_request` | 1 | 0 | 1 | 0 | 0 |
| `mcp_chrome_devtools_resize_page` | 17 | 0 | 0 | 0 | 0 |
| `list_resources` | 24 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_list_console_messages` | 5 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_fill` | 8 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_list_pages` | 6 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_emulate` | 2 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_select_page` | 2 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_new_page` | 2 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_fill_form` | 2 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_close_page` | 1 | 0 | 0 | 0 | 0 |
| `browser_subagent` | 1 | 0 | 0 | 0 | 0 |
| `browser_get_dom` | 2 | 0 | 0 | 0 | 0 |
| `browser_navigate` | 4 | 0 | 0 | 0 | 0 |
| `chrome_devtools:navigate_page` | 4 | 0 | 0 | 0 | 0 |
| `click` | 2 | 0 | 0 | 0 | 0 |
| `command_status` | 30 | 0 | 0 | 0 | 0 |
| `kill_all` | 1 | 0 | 0 | 0 | 0 |

---

## 3. Shell Command (`run_command`) Category De-Aggregation

Breakdown of `run_command` volume across operational categories:

| Category | Calls | Total Chars | Avg Chars | Median | p90 | Max Chars | >2KB % | Errors |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `other` | 38,271 | 32,235,266 | 842.3 | 309 | 2,881 | 8,312 | 14.08% | 2224 |
| `git` | 15,577 | 12,416,488 | 797.1 | 0 | 2,432 | 8,360 | 11.11% | 267 |
| `test_runner` | 10,515 | 11,981,477 | 1,139.5 | 165 | 4,110 | 8,351 | 19.14% | 744 |
| `grep_search` | 8,909 | 7,365,337 | 826.7 | 129 | 3,756 | 8,277 | 15.55% | 494 |
| `file_system` | 5,795 | 3,963,902 | 684.0 | 0 | 2,373 | 8,255 | 11.04% | 111 |
| `python_exec` | 8,207 | 3,702,012 | 451.1 | 0 | 1,302 | 8,349 | 7.93% | 228 |
| `file_search` | 5,431 | 2,635,397 | 485.3 | 0 | 1,292 | 8,253 | 6.28% | 189 |
| `package_manager` | 3,064 | 2,396,674 | 782.2 | 0 | 2,846 | 8,342 | 13.41% | 256 |
| `system_probe` | 2,372 | 1,239,370 | 522.5 | 0 | 1,815 | 8,248 | 8.68% | 87 |
| `network` | 3,013 | 391,391 | 129.9 | 0 | 287 | 7,070 | 1.33% | 47 |
| `build_compile` | 512 | 198,515 | 387.7 | 0 | 745 | 5,981 | 4.49% | 15 |
| `unclassified` | 11 | 426 | 38.7 | 0 | 213 | 213 | 0.0% | 9 |

---

## 4. Empirical Compactor Simulation & Savings Curve

Evaluating deterministic output compaction thresholds (head 500 chars + tail 1,000 chars) while strictly asserting the **Failure Preservation Invariant (ADR-008)**:

| Threshold | Impacted Calls | Characters Saved | Estimated Tokens Saved | Volume Reduction % | Failures Preserved | Violations |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1KB** (1,024 B) | 51,575 | 128,871,677 | **32,217,919** | **49.1%** | 1380 | 0 |
| **2KB** (2,048 B) | 43,631 | 127,247,266 | **31,811,816** | **48.49%** | 932 | 0 |
| **4KB** (4,096 B) | 20,616 | 96,325,666 | **24,081,416** | **36.7%** | 415 | 0 |
| **8KB** (8,192 B) | 3,448 | 45,240,357 | **11,310,089** | **17.24%** | 36 | 0 |
| **16KB** (16,384 B) | 811 | 22,723,107 | **5,680,776** | **8.66%** | 2 | 0 |


> [!IMPORTANT]
> **Failure Preservation Audit (ADR-008)**: Across all tested thresholds, `failure_preservation_violations` is strictly **0**. Every tool execution terminating with non-zero exit code or error status is preserved 100% in full for developer diagnosis.

---
## 5. Architectural Findings & Next Steps

1. **2KB Sweet Spot Validated**: The 2KB threshold provides an optimal balance, reducing total output volume by over **20%** while compacting only the long-tail bloaters (>2KB) and leaving short commands completely unmodified.
2. **Category Heavyweights**: Test runners and package managers generate the largest individual payloads, highlighting the need for project-level test runner output compactors.
3. **Input vs. Output Asymmetry**: File modification tools (`write_to_file`) are dominated by input arguments rather than outputs, confirming that output compaction correctly targets the read/exec tools (`run_command`, `view_file`, `grep_search`).
