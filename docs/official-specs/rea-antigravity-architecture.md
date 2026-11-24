<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Technical Architecture Specification: REA (Reverse Engineer Anything) Native Antigravity Integration & Cleanroom Harmonization

**Document Reference**: `PSL-SPEC-2026-REA-001`  
**Governing Standard**: ICARO-42/b Ordinance  
**Classification**: Official Technical Architecture & Cleanroom Reconstruction Specification  
**Publication Path**: `docs/official-specs/rea-antigravity-architecture.md`  
**Status**: **APPROVED — ARCHITECTURAL CONTRACT**  

---

## 1. Document Metadata & Architectural Scope

### 1.1 Integration Scope & Solved Failure Classes
This specification establishes the official architectural blueprint for integrating **Reverse Engineer Anything (REA)** (upstream package `rea-agents`, web `https://rea.tools/`) into **agyis-harness** within the Google Antigravity™ runtime environment.

The architecture resolves three core integration classes cleanly without adding overhead to non-RE workflows:
1. **Opt-In Doctor Latency Isolation**: Heavy disassembler probes (`rea providers --json`) execute only under `--experimental-rea`, keeping standard `agyis doctor` strictly sub-second (`<1.0s`) with zero false warnings.
2. **Phase-Aware Cleanroom Fence**: `completion_fence_hook.py` decouples `spec_dirty` (`docs/specs/**`, `.agents/ledger/**`) from `code_dirty`, clearing specification work via `agyis verify --spec` or `rea verify-reconstruction` without forcing unit test runs.
3. **Subshell & Stream Resilience**: Lifecycle hooks provide transparent `PATH` shims for `rea`, elevated bounded sliding-window quotas (`8` in `15` calls, `<3` consecutive identical reads) for cleanroom specs, and character-offset pre-slicing (`>200KB`) for multi-megabyte disassembly dumps.

### 1.2 The Non-Interference Invariant
This specification codifies the foundational behavioral guarantee:

> [!IMPORTANT] The Non-Interference Invariant
> Agyis harness lifecycle hooks, runtime diagnostics, and completion gates must **never obstruct, falsely throttle, or coerce false testing demands** upon an agent executing legitimate binary reverse engineering, static analysis, or cleanroom specification authoring.
> 
> When REA tooling is not requested, the harness must remain completely zero-overhead and sub-second (<1.0s). When REA tooling is engaged, the harness must provide transparent PATH shims, phase-aware completion fence gating, loop exemptions for specifications, and bounded compaction for massive disassembly dumps.

### 1.3 High-Level Value Equation
$$\text{AGYIS (Deterministic Governance + Lifecycle Hooks)} + \text{REA (Evidence-Based Binary Reconstruction)} = \textbf{Provable Cleanroom Engineering}$$

Combining AGYIS and REA delivers an automated, evidence-backed workflow for analyzing legacy binaries, closed-source dependencies, protocols, and packaged runtimes, producing cleanroom specifications in `docs/specs/**` backed by immutable evidence ledgers in `.agents/ledger/**`.

---

## 2. Complete REA System Architecture & Catalog

REA exposes a symmetric two-tier interface for autonomous coding agents:
1. **Model Context Protocol (MCP) Stdio Server**: **255** MCP tools, **6** Guided Prompts, and Evidence URI resources running on MCP Protocol `2025-11-25`.
2. **Command Line Interface (CLI)**: **196** CLI subcommands supporting structured output formatting (`json`, `toon`, `yaml`, `markdown`, `jsonl`), token pagination, offset slicing, and non-interactive script piping.

### 2.1 Identity & Catalog Checksums (`rea@6.9.0`)
Every build and delivery artifact is validated against canonical cryptographic digests:

| Catalog Attribute | Authoritative Value | Verification Mechanism |
| :--- | :--- | :--- |
| **CLI Package Version** | `6.9.0` | `rea --version` / `package.json` |
| **REA SDK Version** | `2.3.1` | Embedded SDK contract |
| **Bundled Skill Version** | `"62"` | `skill.expected_version` (`reverse-engineer-anything`) |
| **MCP Tools Count** | **255 tools** | Stdio MCP `tools/list` / `rea mcp doctor` |
| **Guided Prompts Count** | **6 prompts** | Stdio MCP `prompts/list` / `rea mcp doctor` |
| **CLI Subcommands Count**| **196 subcommands** | `rea providers --json` `catalog.counts.cli_commands` |
| **Tools Catalog SHA-256**| `b3054fab57a222a4690d93cdba88805d7cbd2e6c0279dd596eecf213030c3797` | `rea providers --json` digest |
| **Prompts Catalog SHA-256**| `60078bd8ef8bd152b51440e7579fba2059beec18fec5148dd0ec10ef013213fe` | `rea providers --json` digest |
| **Combined Catalog SHA-256**| `2c725b48818ac5266198069330907c657f0fa2b6b8236065e5a191e20d95c2d7` | `rea mcp doctor` composite signature |

### 2.2 Complete Breakdown of the 255 MCP Tools (18 Functional Domains)

The **255** MCP tools in `rea@6.9.0` are organized across 18 specialized reverse engineering domains:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                            REA 6.9.0 (255 MCP TOOL TAXONOMY)                           │
├──────────────────────────┬──────────────────────────┬──────────────────────────────────┤
│ 1. Binary Session (6)    │ 2. Native Disasm (16)    │ 3. Cross-References (8)          │
│ • open_binary            │ • analyze_function       │ • xrefs                          │
│ • close_binary           │ • procedure_pseudo_code  │ • find_xrefs_to_name             │
│ • reset_investigation    │ • procedure_assembly     │ • procedure_references           │
│ • binary_session         │ • read_function_instr... │ • address_name, set_address_name │
│ • binary_overview        │ • batch_decompile / all  │ • resolve_native_call_targets    │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 4. Call Graphs (4)       │ 5. Semantic Tracing (9)  │ 6. Memory & Byte Search (14)     │
│ • procedure_callers      │ • trace_feature          │ • search_strings, search_bytes   │
│ • procedure_callees      │ • trace_call_path        │ • search_procedures, read_bytes  │
│ • get_call_graph         │ • trace_native_values    │ • list_strings, list_segments    │
│ • build_call_path        │ • trace_native_ui_action │ • list_procedures, inspect_by... │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 7. Annotations/Nav (13)  │ 8. Binary Metadata (27)  │ 9. Crash Analysis (1)            │
│ • comment, set_comment   │ • inspect_binary_layout  │ • inspect_recorded_crash         │
│ • inline_comment         │ • inspect_pe_resources   │                                  │
│ • annotate_native_func.. │ • inspect_go_binary      │                                  │
│ • list/set/unset_bookm.. │ • inspect_rust_binary    │                                  │
│ • get_navigation_context │ • inspect_sqlite_database│                                  │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 10. Apple / macOS (14)   │ 11. Managed / .NET (7)   │ 12. Electron & JS (14)           │
│ • inspect_macho          │ • inspect_managed_art... │ • analyze_javascript_application │
│ • inspect_plist          │ • inspect_managed_mem... │ • reconcile_javascript_runtime   │
│ • inspect_signature      │ • inspect_managed_nat... │ • recover_javascript_sources     │
│ • demangle_swift         │ • compare_managed_mem... │ • inspect_electron_fuses         │
│ • analyze_swift_types    │ • verify_managed_nati... │ • list/inspect_electron_page     │
│ • get_objc_classes       │ • import_managed_reco... │ • observe_javascript_runtime     │
│ • project_apple_appli... │ • project_managed_app... │ • compare_source_to_bundle       │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 13. Web & Browser (17)   │ 14. Android & Mobile (17)│ 15. Android ADB Control (24)     │
│ • list_browser_targets   │ • inspect_android_pack...│ • list_adb_devices / inspect     │
│ • inspect_web_page       │ • search_android_classes │ • list/pull/inspect_adb_package  │
│ • observe_web_session    │ • inspect_android_class  │ • start/stop_adb_app             │
│ • capture_browser_scen.. │ • inspect_android_method │ • read_adb_logcat                │
│ • inspect_playwright_tr. │ • decode_android_res...  │ • capture_adb_screen             │
│ • inspect_api_contract   │ • identify_flutter_build │ • install/uninstall_adb_package  │
│ • compare_web_captures   │ • inspect_dart_aot       │ • resolve_adb_packages           │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 16. Firmware & WASM (7)  │ 17. Network Packets (4)  │ 18. Dynamic, Build & Evidence(53)│
│ • inspect_firmware_reg...│ • inspect_packet_capture │ • start/load/instrument_frida    │
│ • extract_firmware       │ • inspect_pcap_capture   │ • start/console_gdb_session      │
│ • inspect_wasm_artifact  │ • inspect_packet_fields  │ • start_rizin_debug_session      │
│ • compare_wasm_interf... │ • inspect_pcap_client    │ • build_reconstruction_oblig...  │
│ • inspect_evm_interface  │                          │ • evaluate_reconstruction_cov... │
│ • decode_signal_record...│                          │ • verify_reconstruction          │
│ • inspect_signal_decod...│                          │ • record/list/verify_unknowns    │
└──────────────────────────┴──────────────────────────┴──────────────────────────────────┘
```

#### Detailed Domain Matrix & Input/Output Contracts

| # | Functional Domain | Tool Count | Representative Tool Names | Primary Arguments | Return Payload | Failure / Error Invariant |
|---|---|---|---|---|---|---|
| 1 | **Binary Session** | 6 | `open_binary`, `close_binary`, `reset_investigation`, `binary_session`, `binary_overview`, `open_bundle_resources` | `path: string`, `provider_id?: string` | `document`, `target_sha256`, `architecture`, `endianness`, `format` | Fails closed if file is missing, corrupt, or unsupported. Returns empty state when target-free. |
| 2 | **Native Disassembly** | 16 | `analyze_function`, `procedure_pseudo_code`, `procedure_assembly`, `read_function_instructions`, `batch_decompile`, `decompile_all`, `procedure_info`, `inspect_native_*` | `path?: string`, `address?: string`, `name?: string` | Complete function dossiers, basic block control flow graphs, pseudo-C listings. | Returns error if symbol unresolved; decompiler fallbacks preserve raw disassembly. |
| 3 | **Cross References** | 8 | `xrefs`, `find_xrefs_to_name`, `procedure_references`, `address_name`, `set_address_name`, `set_addresses_names`, `resolve_native_call_targets`, `match_native_functions` | `address: string`, `direction?: "to"\|"from"`, `name?: string` | Relocation table with callers, callees, data read/write sites. | Empty list on zero references; does not guess references. |
| 4 | **Call Graph** | 4 | `procedure_callers`, `procedure_callees`, `get_call_graph`, `build_call_path` | `root_address: string`, `depth?: number`, `from: string`, `to: string` | Directed acyclic graph (nodes, edges) mapping execution flow. | Bounds recursion at declared depth; preserves unresolved indirect call targets. |
| 5 | **Semantic Tracing** | 9 | `trace_feature`, `trace_call_path`, `trace_native_values`, `trace_native_ui_action`, `observe_native_calls`, `observe_native_ui`, `capture_native_ui_scenario`, `correlate_static_and_runtime`, `find_changed_behavior` | `feature: string`, `address: string`, `register?: string` | Step-by-step evidence chain from UI event or literal string to backend handler. | Negative search boundaries prevent infinite loops; flags unobserved leaps. |
| 6 | **Memory & Search** | 14 | `search_strings`, `search_procedures`, `search_bytes`, `read_bytes`, `address_to_file_offset`, `list_strings`, `list_names`, `list_segments`, `list_procedures`, `inspect_byte_entropy` | `pattern: string`, `hex_pattern: string`, `mask?: string` | Virtual address offset, section name, decoded string literal. | Returns empty match sets; error if mask length mismatches pattern. |
| 7 | **Annotations & Nav** | 13 | `comment`, `set_comment`, `inline_comment`, `set_inline_comment`, `annotate_native_function`, `list_bookmarks`, `set_bookmark`, `unset_bookmark`, `goto_address`, `next_address`, `prev_address`, `get_navigation_context`, `inspect_address_context` | `address: string`, `comment?: string`, `note?: string` | Mutation confirmation, navigation state, and active session bookmark ledger. | Disassembler session state mutation; rollback on write collision. |
| 8 | **Binary Metadata** | 27 | `inspect_binary_layout`, `inspect_pe_resources`, `inspect_pe_load_config`, `inspect_pe_certificates`, `inspect_pe_imports`, `inspect_binary_hardening`, `audit_release_exposure`, `inspect_go_binary`, `inspect_rust_binary`, `inspect_il2cpp_metadata`, `inspect_python_pyc`, `inspect_erlang_beam`, `inspect_v8_code_cache`, `inspect_sqlite_database`, `inspect_with_objdump`, `inspect_ntfs_journal`, `inspect_gpu_code_objects` | `path: string`, `table?: string`, `detail?: "summary"\|"full"` | Checksec mitigations (Canary, NX, PIE, RELRO), Go pclntab facts, Rust dep-v0 crates, SQLite tables, bytecode/journal facts. | Returns null metadata without panic when binary does not contain target runtime symbols. |
| 9 | **Crash Analysis** | 1 | `inspect_recorded_crash` | `path: string`, `include_debugger_context?: boolean` | Register states, faulting instruction, stack backtrace, signal taxonomy. | Preserves core dump memory isolation; fails if core header invalid. |
| 10 | **Apple / macOS** | 14 | `inspect_macho`, `inspect_plist`, `inspect_signature`, `inspect_apple_ips`, `list_architectures`, `demangle_swift`, `analyze_swift_types`, `get_objc_classes`, `get_objc_protocols`, `decode_interface_builder`, `inspect_keyed_archive`, `inspect_asset_catalog`, `trace_dylib_resolution`, `project_apple_application_graph` | `path: string`, `mangled_name?: string` | Objective-C class hierarchies, Swift struct metadata, compiled NIB UI trees, dyld @rpath load graph. | Fails closed on signature tampering; gracefully returns unmangled string if not Swift. |
| 11 | **Managed / .NET**| 7 | `inspect_managed_artifact`, `inspect_managed_members`, `inspect_managed_native_boundaries`, `compare_managed_members`, `verify_managed_native_boundaries`, `import_managed_reconstruction`, `project_managed_application_graph` | `path: string`, `managed_path: string`, `native_path: string` | CIL metadata tables, `ldstr` string pool, P/Invoke imports mapped to native DLL exports. | Flags calling convention mismatches; isolates unmanaged exports. |
| 12 | **Electron & JS** | 14 | `analyze_javascript_application`, `reconcile_javascript_runtime`, `recover_javascript_sources`, `export_web_scripts`, `inspect_electron_fuses`, `list_electron_targets`, `inspect_electron_page`, `capture_electron_scenario`, `list_javascript_runtime_targets`, `observe_javascript_runtime`, `compare_javascript_export_shapes`, `trace_application_feature`, `trace_javascript_semantics`, `compare_source_to_bundle` | `path: string`, `endpoint?: string`, `evidence_id?: string` | ASAR module graph, Electron IPC channel maps, hardcoded Electron fuses, recovered modules with SHA-256. | Detects disabled `--inspect` fuse (0x00) without launching app, preventing agent connection hang. |
| 13 | **Web & Browser** | 17 | `list_browser_targets`, `inspect_web_page`, `observe_web_session`, `observe_web_execution`, `capture_browser_scenario`, `discover_webmcp_tools`, `inspect_web_event_listeners`, `inspect_web_network_capture`, `trace_web_module_imports`, `trace_web_source_location`, `compare_web_captures`, `capture_web_screenshot`, `compare_web_screenshots`, `analyze_web_bundle`, `inspect_playwright_trace`, `inspect_api_contract`, `compare_static_and_observed_endpoints` | `endpoint: string`, `selector?: string`, `path?: string`, `format?: string` | DOM trees, live event listeners, parsed HAR/mitmproxy/Playwright captures, API contracts, sourcemap mappings. | Never initiates live external HTTP traffic during capture analysis; parses offline capture files hermetically. |
| 14 | **Android & Mobile**| 17 | `inspect_android_package`, `inspect_android_jni_bindings`, `search_android_classes`, `inspect_android_class`, `inspect_android_method`, `trace_android_references`, `decode_android_resources`, `identify_flutter_build`, `inspect_dart_aot`, `inspect_apk_signature`, `inspect_apktool_client`, `project_android_application_graph`, `project_harmony_application_graph`, `inspect_jeb_client`, `open_jeb_project`, `list_jeb_units`, `decompile_jeb_item` | `path: string`, `class_name?: string`, `method_name?: string` | Decompiled Java methods via JADX, Flutter engine commit hashes, Dart snapshot string pools, JNI bindings, resource XML. | Requires JDK 17+ and JADX JAR; fails with clean diagnostic message if JADX is unconfigured. |
| 15 | **Android ADB** | 24 | `inspect_adb_client`, `list_adb_devices`, `inspect_adb_device`, `list_adb_packages`, `pull_adb_package`, `read_adb_logcat`, `inspect_adb_package`, `start_adb_app`, `start_adb_activity`, `stop_adb_app`, `capture_adb_screen`, `list_adb_services`, `install_adb_package`, `uninstall_adb_package`, `pull_adb_file`, `push_adb_file`, `list_adb_processes`, `list_adb_directory`, `list_adb_features`, `inspect_adb_display`, `inspect_adb_window`, `read_adb_setting`, `collect_adb_bugreport`, `resolve_adb_packages` | `serial: string`, `package?: string`, `buffer?: string`, `lines?: number` | Device prop whitelist facts, APK binaries, bounded logcat slices, display dumpsys. | Bounds logcat lines to avoid terminal buffer overflow; requires authorized ADB device connection. |
| 16 | **Firmware & WASM**| 7 | `inspect_firmware_regions`, `extract_firmware`, `inspect_wasm_artifact`, `compare_wasm_interfaces`, `inspect_evm_interface`, `decode_signal_recording`, `inspect_signal_decoders` | `path: string`, `decoder?: string`, `options?: object` | Carved flash partitions, disassembled WebAssembly (WAT), EVM bytecode function selectors, decoded logic traces. | Non-destructive carving; refuses to overwrite non-empty destination directories. |
| 17 | **Network Packets**| 4 | `inspect_packet_capture`, `inspect_pcap_capture`, `inspect_packet_fields`, `inspect_pcap_client` | `path: string`, `filter?: string`, `fields?: string[]` | Dissected PCAP frames via TShark, DNS queries, TLS Server Name Indications (SNI). | Fails if TShark / Wireshark CLI missing; strictly operates on static PCAP files. |
| 18 | **Dynamic, Build & Cleanroom**| 53 | `start_frida_session`, `load_frida_script`, `instrument_with_frida`, `start_gdb_session`, `gdb_console`, `execute_rizin_command`, `cutter_command`, `start_rizin_debug_session`, `capture_process_scenario`, `compare_process_captures`, `export_evidence_bundle`, `import_evidence_bundle`, `inspect_analysis_view`, `build_reconstruction_obligation_ledger`, `evaluate_reconstruction_coverage`, `verify_reconstruction`, `record_unknown`, `list_unknowns`, `verify_unknown_resolution`, `start_build_computer`, `search_guidance`, etc. | `evidence_ids: string[]`, `spec_goal: string`, `claim: string`, `question: string` | Portable Evidence JSON bundles, typed obligation ledgers, mathematical coverage percentages, verified unknowns ledger. | Fail-closed evaluation; claims unsupported by concrete Evidence records are rejected. |

### 2.3 CLI Subcommand Architecture (196 Commands)
The REA CLI (`rea <command> [args]`) mirrors the MCP toolset, providing non-interactive, pipeline-friendly execution for scripts and shell commands.

- **Universal Formatting Flags**:
  - `--format json`: Standard RFC 8259 JSON for programmatic ingestion.
  - `--format toon`: Token-Optimized Object Notation, reducing token overhead by up to 45% compared to pretty-printed JSON.
  - `--format yaml`: Human-readable structured YAML.
  - `--format markdown`: GitHub Flavored Markdown tables and code fences for direct artifact embedding.
  - `--format jsonl`: Line-delimited JSON streams for massive dataset iteration.
- **Context Protection Controls**:
  - `--limit <N>`: Truncates output array elements to prevent context window exhaustion.
  - `--offset <N>`: Slices large data sets for deterministic pagination.
  - `--detail <summary|full>`: Emits high-level structural metrics or full AST dumps.
  - `--filter-output <jq-expr>`: Evaluates jq-like projection prior to stdout emission.

### 2.4 The 6 Guided MCP Prompts
REA defines 6 formal guided prompt contracts that enforce disciplined, evidence-based reverse engineering methodologies directly into agent reasoning:

```mermaid
flowchart TD
    A[Raw Binary or Application Target] --> B{Investigation Goal}
    B -->|Trace Single Feature| P1["investigate_feature<br/>• String & symbol search<br/>• Function dossier & xrefs<br/>• Record residual unknowns"]
    B -->|Version Comparison| P2["compare_application_versions<br/>• Full structural diff<br/>• Function behavior diff<br/>• Process capture diff"]
    B -->|Verify Cleanroom Spec| P3["verify_reconstruction<br/>• Evidence claim matching<br/>• Formal pass/fail gate<br/>• Zero speculative pass"]
    B -->|Crash Triage| P4["trace_crash<br/>• Core dump dissection<br/>• Faulting instruction xrefs<br/>• Separate crash from cause"]
    B -->|Audit Knowledge| P5["audit_residual_unknowns<br/>• Review open questions<br/>• Verify cited evidence<br/>• Cryptographic revision lock"]
    B -->|Dynamic Scenario| P6["prepare_bounded_process_capture<br/>• Ephemeral PTY execution<br/>• Exact boundary assertions<br/>• Sampling gap accounting"]
```

1. **`investigate_feature`**:
   - *Objective*: Trace a requested feature, behavior, string, or symbol through artifact, symbol, and function evidence without claiming unobserved behavior.
   - *Required Arguments*: `feature` (string). *Optional*: `target_path`, `document`, `procedure`, `provider_id`.
   - *Disciplined Steps*: Route target $\to$ Search strings/procedures $\to$ Consult analysis view $\to$ Build function dossiers and xrefs $\to$ Record residual unknowns.
2. **`compare_application_versions`**:
   - *Objective*: Compare baseline and candidate application versions through complete inventory and runtime evidence without equating missing data with unchanged behavior.
   - *Required Arguments*: `left_target_path`, `right_target_path`. *Optional*: `left_manifest_id`, `right_manifest_id`, `focus_occurrence_id`.
   - *Disciplined Steps*: Open both targets $\to$ Reconstruct application graphs $\to$ Compare inventory $\to$ Differentiate functions $\to$ Record unknowns.
3. **`verify_reconstruction`**:
   - *Objective*: Formally evaluate a finite reconstruction specification against retained Evidence comparisons without broadening pass results into global equivalence.
   - *Required Arguments*: `reconstruction_goal` (string). *Optional*: `comparison_evidence_id`, `provider_id`.
   - *Disciplined Steps*: Audit comparison evidence $\to$ Evaluate per-claim typed specification $\to$ Report verification unknowns.
4. **`trace_crash`**:
   - *Objective*: Correlate a crash symptom (signal, exception, address) with static call/reference evidence and process capture observations.
   - *Required Arguments*: `crash_signal` (string). *Optional*: `target_path`, `document`, `procedure`, `capture_evidence_id`.
   - *Disciplined Steps*: Open target $\to$ Resolve faulting address to function dossier $\to$ Trace callers and references $\to$ Correlate with capture $\to$ Separate observed crash from inferred cause.
5. **`audit_residual_unknowns`**:
   - *Objective*: Review active residual unknown heads against retained evidence, revision integrity, and authority requirements without silently closing unanswered questions.
   - *Required Arguments*: `audit_scope` (string). *Optional*: `unknown_id`, `evidence_id`.
   - *Disciplined Steps*: List open heads $\to$ Verify resolved heads against cited evidence $\to$ Update unknowns with revision guards $\to$ Record newly discovered unknowns.
6. **`prepare_bounded_process_capture`**:
   - *Objective*: Run a caller-selected process experiment that answers a specific behavioral question under explicit boundaries.
   - *Required Arguments*: `behavior_question`, `executable`, `working_directory`. *Optional*: `prior_capture_evidence_id`.
   - *Disciplined Steps*: Execute scenario under ephemeral PTY $\to$ Compare with prior compatible captures $\to$ Record sampling gaps as unknowns.

---

## 3. Provider Matrix & Execution Engines

REA follows a strict **bring-your-own-provider** architecture for resource-intensive disassemblers, while providing built-in, zero-dependency parsers for portable formats.

```
                                  ┌──────────────────────────────┐
                                  │    REA Unified Interface     │
                                  │  (255 MCP / 196 CLI Tools)   │
                                  └──────────────┬───────────────┘
                                                 │
            ┌────────────────────────┬───────────┴───────────┬────────────────────────┐
            ▼                        ▼                       ▼                        ▼
 ┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐
 │    Heavy Engines     │ │  Mobile & Decompiler │ │  Dynamic Tracing     │ │ Built-in Parsers     │
 │ • Ghidra 12.1+       │ │ • JADX Headless JAR  │ │ • Frida Core         │ │ • Electron ASAR      │
 │   (Headless Java 21) │ │ • JEB MCP Client     │ │ • GDB MI (-i=mi)     │ │ • .NET PE/CLI        │
 │ • Hopper v4/v5       │ │ • Apktool & aapt2    │ │ • Rizin & Cutter     │ │ • Mach-O / Dyld      │
 │ • IDA Pro (idalib)   │ │ • sigrok-cli         │ │ • Wireshark / TShark │ │ • Go / Rust / SQLite │
 └──────────────────────┘ └──────────────────────┘ └──────────────────────┘ └──────────────────────┘
```

### 3.1 Heavy Disassembler Engines

#### 1. Ghidra Engine (Headless 12.1+)
- **Supported Architectures**: x86, x86_64, ARM, AArch64, MIPS, PowerPC, RISC-V, SPARC.
- **Runtimes & Environment**: Requires 64-bit **OpenJDK 21 or newer** and a complete Ghidra distribution.
  - `GHIDRA_INSTALL_DIR`: Must point to the Ghidra root (e.g. `/opt/ghidra`).
  - **Dynamic JVM Discovery Ladder**: Rather than relying on static paths, REA traverses an ordered discovery ladder to identify a compatible JDK 21+ runtime:
    1. `$JAVA_HOME` (if valid JDK 21+ binary exists at `$JAVA_HOME/bin/java`).
    2. `/usr/lib/jvm/java-21-openjdk*` (Linux standard OpenJDK path glob).
    3. `/usr/lib/jvm/java-21-openjdk-amd64` (Ubuntu / Debian multiarch).
    4. `/usr/lib/jvm/jre-21-openjdk` (Fedora / RHEL).
    5. `/opt/homebrew/opt/openjdk@21` (macOS Homebrew Apple Silicon).
    6. `/usr/local/opt/openjdk@21` (macOS Homebrew Intel).
    7. `/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home` and `/Library/Java/JavaVirtualMachines/openjdk-21.jdk/Contents/Home` (macOS PKG installers).
- **Headless Invariant**: Invokes `$GHIDRA_INSTALL_DIR/support/analyzeHeadless` in ephemeral workspace directories (`/tmp/rea_ghidra_*`). It never opens an interactive GUI window.
- **Native Decompiler**: Employs the precompiled ELF/Mach-O native decompiler binary located at `$GHIDRA_INSTALL_DIR/Ghidra/Features/Decompiler/os/<os_arch>/decompile`.
- **Java Version Trap & Provider Fallback Order**: On systems where default `java` is Java 8 or Java 17, REA explicitly enforces `JAVA_HOME` pointing to JDK 21 from the discovery ladder, preventing `unsupported_version` JVM crashes. If no JDK 21+ is available on the host, REA automatically degrades through the disassembler provider fallback order:
  $$\text{Ghidra} \longrightarrow \text{Rizin} \longrightarrow \text{objdump} \longrightarrow \text{built-in parsers}$$

#### 2. Hopper Disassembler (v4 / v5)
- **Supported Targets**: Linux ELF (Ubuntu, Arch, Fedora) and macOS Mach-O.
- **Environment**: Requires `HOPPER_LAUNCHER_PATH` and an active display socket or virtual framebuffer.
- **Headless Hopper Contract**:
  - **Display Socket Probing**: Checks for active `$DISPLAY` or `$WAYLAND_DISPLAY` environment variables.
  - **Headless & Virtual Framebuffer Fallback**: If no display socket is present, REA probes for `xvfb-run` (e.g. `xvfb-run -a <hopper-cmd>`) or sets `QT_QPA_PLATFORM=offscreen`.
  - **Graceful Degradation**: If neither a physical display nor a virtual framebuffer is available (e.g. minimal headless CI or bare SSH session), Hopper is marked `unavailable: "no display socket"`, and disassembly requests fall back cleanly to Ghidra or Rizin without raising unhandled Qt platform errors or crashing the supervisor.
- **IPC Mechanism**: Communicates via Hopper's local script server and IPC socket to extract disassembly listings and basic block graphs.

#### 3. IDA Pro & IDA MCP
- **Supported Versions**: IDA Pro 9.0 and 9.1+ (Windows, Linux, macOS arm64).
- **Profiles**:
  - *Legacy Attached Profile*: Binds to an already-running IDA GUI instance by binary SHA-256 without modifying the active database.
  - *Modern Headless Supervisor*: Spawns IDA in headless batch mode via `idalib-mcp`, creates private temporary IDBs, and terminates cleanly upon session exit.
- **Headless Supervisor Isolation Protocol**:
  - **Ephemeral Sandbox Isolation**: The supervisor copies the target binary to an ephemeral, isolated directory (`/tmp/rea_ida_<uuid>/`) before analysis.
  - **Mandatory Autonomous Flags**:
    - `-A`: Autonomous mode (suppresses all interactive modal dialogs, license prompts, and blocking message boxes).
    - `-B`: Batch mode (executes non-interactive disassembly and analysis generation).
    - `-o`: Output redirection (redirects generated `.idb` / `.i64` database files into the ephemeral sandbox away from the original source tree).
  - **Zero-Mutation Invariant**: Asserts zero file mutation or lock generation within the original binary directory, preventing database lock collisions and indefinite process hangs.

### 3.2 Mobile & Decompiler Providers
- **JADX**: Requires `jadx-headless-mcp` 0.7.1 JAR configured via `REA_JADX_MCP_JAR` with JDK 17+. Handles Android APK DEX decompilation to structured Java classes.
- **JEB Decompiler**: Integrates with running PNF Software JEB instances via its native MCP bridge (`inspect_jeb_client`).
- **Apktool & Sigrok**: Uses local system binaries (`apktool`, `sigrok-cli`) for non-destructive Android resource decoding and logic analyzer signal processing.

### 3.3 Dynamic Instrumentation Engines
- **Frida Core**: Connects via Node/Python Frida bindings to attach to running processes or spawn binaries under memory hooks, executing ephemeral scripts without mutating target files on disk.
- **GDB Machine Interface (MI)**: Spawns ephemeral `gdb -i=mi` instances with an inferior pseudo-terminal, permitting non-interactive backtrace inspections and core dump dissections.
- **Rizin & Cutter**: Executes non-interactive Rizin batch commands (`rizin -q -c "<cmd>" <binary>`) and connects to Cutter GUI instances via live Python bridges.

### 3.4 Built-in Portable Parsers (Zero External Dependency)
To guarantee high performance and hermetic operation without requiring external disassemblers for routine tasks, REA provides built-in parsers:
- **Electron & ASAR**: Unpacks and maps Electron archives, parses JavaScript ASTs, inspects hardcoded Chromium fuse bytes (`NodeCliInspect`, `RunAsNode`), and maps IPC channels.
- **.NET PE/CLI**: Parses PE headers, metadata streams (`#~`, `#Strings`, `#Blob`), `ldstr` CIL bytecode, and P/Invoke DLL boundary bindings directly in JavaScript.
- **Mach-O & Apple**: Parses Mach-O load commands, LC_SEGMENT, code signing entitlements, and dyld resolution paths (`@rpath`, `@loader_path`).
- **Go Binaries**: Extracts Go module versions, dependency trees, and pclntab function tables.
- **Rust Binaries**: Extracts `.dep-v0` cargo auditable metadata packages.
- **SQLite Databases**: Performs read-only, lock-free schema and table inspection via Node.js native SQLite drivers (`node:sqlite`).

---

## 4. Antigravity Native Integration & Happy Path

Google Antigravity coordinates tools and agents across three core components:
1. **MCP Configuration**: `~/.gemini/config/mcp_config.json` registering stdio and SSE servers.
2. **Modular Skills**: `~/.gemini/config/skills/` (global) and `.agents/skills/` (project-level).
3. **Agent Brain & Transcripts**: `~/.gemini/antigravity/` preserving state, logs, and context.

### 4.1 Definitive MCP Configuration Specification
To achieve complete, error-free integration between Google Antigravity and REA across diverse host environments, the `mcpServers.rea` block in `~/.gemini/config/mcp_config.json` is configured following portable resolution semantics:

```json
{
  "mcpServers": {
    "rea": {
      "command": "rea",
      "args": [
        "mcp"
      ],
      "env": {
        "GHIDRA_INSTALL_DIR": "/opt/ghidra",
        "JAVA_HOME": "${DYNAMIC_JVM_PATH}",
        "REA_MCP_INPUT_SCHEMA_PROFILE": "full",
        "REA_MCP_OUTPUT_SCHEMA_PROFILE": "off"
      }
    }
  }
}
```

> [!NOTE] Portable Host Resolution & Dynamic JVM Ladder
> - **Portable `command` Resolution**: In standard environments where `rea` is installed globally (via `pnpm add -g rea-agents` or `npm install -g rea-agents`), `"command": "rea"` executes directly via user PATH shims injected by the harness. When configured via `agyis onboard --experimental-rea` or `agyis install -g --experimental-rea`, the installer dynamically resolves `command` to the host's concrete entrypoint (e.g. `$(pnpm root -g)/rea-agents/scripts/rea.mjs`, `$(npm root -g)/rea-agents/scripts/rea.mjs`, or `~/.local/share/pnpm/rea`).
> - **Dynamic `JAVA_HOME` Discovery**: The environment variable `JAVA_HOME` is dynamically populated during provisioning using the JVM Discovery Ladder:
>   1. Existing `$JAVA_HOME` (if valid JDK 21+).
>   2. Linux OpenJDK glob: `/usr/lib/jvm/java-21-openjdk*`.
>   3. Ubuntu / Debian multiarch: `/usr/lib/jvm/java-21-openjdk-amd64`.
>   4. Fedora / RHEL: `/usr/lib/jvm/jre-21-openjdk`.
>   5. macOS Homebrew (Apple Silicon): `/opt/homebrew/opt/openjdk@21`.
>   6. macOS Homebrew (Intel): `/usr/local/opt/openjdk@21`.
>   7. macOS Temurin / OpenJDK PKG: `/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home`.
> - **Provider Fallback**: If JDK 21+ is unavailable or Ghidra verification fails, disassembler operations degrade in sequence: `Ghidra -> Rizin -> objdump -> built-in parsers`.

### 4.2 Token Conservation Analysis & Schema Pruning
A major vulnerability in multi-hundred-tool MCP integrations is context window bloat during initial tool enumeration:
- **`REA_MCP_INPUT_SCHEMA_PROFILE: "full"`**:
  Ensures that when an agent invokes REA MCP tools (via `inheritMcp: true`), Antigravity receives exhaustive property descriptions, required parameter lists, and parameter types for all **255** tools, preventing hallucinated arguments.
- **`REA_MCP_OUTPUT_SCHEMA_PROFILE: "off"`**:
  Standard MCP schemas publish return payload schemas in addition to input schemas. For **255** tools, transmitting output schema definitions injects thousands of redundant tokens into every single conversational turn. Setting the output schema profile to `"off"` eliminates this token tax entirely while leaving input validation 100% intact.

### 4.3 Client Frame Overflow Prevention
Antigravity's JSON-RPC stdio transport buffers individual tool responses. If an agent executes an unfiltered disassembly dump (e.g. 50,000 lines of disassembly), the client frame can overflow or freeze the UI thread.

**REA Happy Path Safeguards**:
1. **`detail: "summary"` Mode**: Agents must default to `detail: "summary"` when calling tools like `analyze_javascript_application` or `binary_overview`.
2. **Evidence ID Referencing**: REA caches full analysis trees under immutable `evidence_id` hashes and returns lightweight summary receipts.
3. **Paging via `inspect_analysis_view`**: Agents inspect specific slices or modules on demand using `inspect_analysis_view(evidence_id, view, page)` without re-running analysis or flooding context.

### 4.4 Skills Integration (First-Party `re-ops` + Dynamic Upstream Provisioning)
- **First-Party Layer 1 Skill (`harness/skills/re-ops/SKILL.md`)**: Target-agnostic Agyis operational runbook housing the complete **`PSL-RE-001` On-Demand Domain Pack** — cleanroom quarantine (`PSL-RE-001 §1`), pre-analyzed Ghidra direct-mount acceleration (`PSL-RE-001 §2`), the complete 15-subcommand `agyis re` lifecycle palette, 4-vector cleanroom verification, and the 5-step REA surgical escalation ladder. Provisioned via `--role re`, `--role cleanroom`, or the `ops` skill group.
- **Upstream Dynamic Skill (`reverse-engineer-anything`)**: Encapsulates upstream REA operational runbooks, disassembler choice matrices, and cleanroom verification protocols without vendoring external upstream markdown inside `harness/skills/`:
  - **Dynamic Discovery & Provisioning (`provision_rea_skill()` in `harness/runtime/healing.py`)**: Discovers upstream `skills/reverse-engineer-anything/SKILL.md` from `rea providers --json` package `root_path` or user `pnpm`/`npm` global stores, symlinking or downloading on-demand into target skills roots (`~/.gemini/config/skills/reverse-engineer-anything/SKILL.md` or workspace `.agents/skills/`).
  - **Triggers**: Executed on-demand via `agyis init --experimental-rea`, `agyis doctor --experimental-rea --heal`, or `agyis install -g --experimental-rea`.

---

## 5. Cleanroom Reconstruction Contracts

Cleanroom reverse engineering requires a mathematical boundary between the **dirty room** (binary analysis, decompiler inspection) and the **clean room** (specification authoring, clean implementation).

```
┌──────────────────────────────────────┐     ┌───────────────────────────────────────────┐
│        DIRTY ROOM: ANALYSIS          │     │       CLEAN ROOM: IMPLEMENTATION          │
│ • Target Binaries & Libraries        │     │ • Cleanroom Specifications (`docs/specs/`)│
│ • Disassembly & Decompilation Dumps  │     │ • Obligation Ledger                       │
│ • Ephemeral Scratch (`.rea/**`)      │     │   (`.agents/ledger/obligation_ledger.json`)│
│ • Reverse Engineering Prompts        │     │ • Cleanroom Code Implementation           │
│ • Retained Evidence (`evidence_id`)  │     │ • Formal Verification (`agyis verify`)    │
└──────────────────┬───────────────────┘     └──────────────────▲────────────────────────┘
                   │                                            │
                   │           EVIDENCE BOUNDARY                │
                   └───────────────────►────────────────────────┘
```

### 5.1 Repository Ledger Structure
Cleanroom deliverables are codified in two repository locations:
1. **Cleanroom Specifications (`docs/specs/**`)**:
   - Human- and agent-readable architectural, protocol, and functional specifications.
   - Authoritative API contracts, finite state machine definitions, and wire layouts.
   - Contains zero copied decompiled code or vendor proprietary signatures (`agyis verify --spec`).
2. **Obligation Ledgers (`.agents/ledger/**`)**:
   - Machine-verifiable contracts scaffolded via `agyis verify --scaffold` (`harness/cleanroom/obligation.py`):
     - `obligation_ledger.json` (**Primary `REA 6.9.0` strictObject Schema**): Root object containing strictly `evidence_bundle` (`artifacts`, `captures`, `environments`, `providers`, `records`, `scenarios`, `unknowns`), `reviewed_obligations`, and `manifest` (`bindings` list, `contradictions` list). Top-level `"$schema"` is prohibited in `REA 6.9.0`.
     - `manifest.json` (*Legacy fallback schema*): Bindings between obligations, evidence hashes, and `"satisfied"` verification proofs.

### 5.2 Typed Obligation Ledger Model (`.agents/ledger/obligation_ledger.json`)
`validate_obligation_ledger()` validates `.agents/ledger/obligation_ledger.json` against the strict `REA 6.9.0` contract (`harness/cleanroom/obligation.py`):
- Root keys are strictly `{"evidence_bundle", "reviewed_obligations", "manifest"}` (omit deprecated `"$schema"`).
- `reviewed_obligations` requires `"obligation_version": 1` (integer `>= 1`), a `target` strictObject (`artifact_sha256`, `application_node_id`, `semantic_node_id`, `location`), valid `"disposition"` in `{"active", "blocked", "out-of-scope"}`, and `review_evidence_ids` referencing `ev_<64-hex>` records.
- `manifest.bindings` MUST be a `list` of binding objects (not a dict).

```json
{
  "evidence_bundle": {
    "artifacts": [
      {
        "digest": { "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" },
        "format": "markdown"
      }
    ],
    "captures": [],
    "environments": [],
    "providers": [
      { "id": "ghidra", "name": "Ghidra Headless Decompiler", "version": "11.0" }
    ],
    "records": [
      {
        "evidence_id": "ev_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "provider": { "id": "ghidra", "name": "Ghidra Headless Decompiler", "version": "11.0" },
        "subject": {
          "name": "target_binary",
          "digest": { "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc" },
          "format": "elf64",
          "local_path": ".dirtyroom/binaries/target.bin",
          "architecture": "x86_64"
        },
        "predicate_type": "static-disassembly",
        "operation": "procedure_pseudo_code",
        "confidence": "observed",
        "authority": "shipped-artifact"
      }
    ],
    "scenarios": [],
    "unknowns": []
  },
  "reviewed_obligations": [
    {
      "obligation_id": "OBL-001",
      "obligation_version": 1,
      "title": "Packet deserializer contract",
      "application_layer": "protocol",
      "family": "cleanroom",
      "target": {
        "artifact_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        "application_node_id": null,
        "semantic_node_id": null,
        "location": "packet_deserializer"
      },
      "required": true,
      "required_case_kinds": ["positive"],
      "required_original_authority": "static",
      "required_fixture_authority": "unit",
      "required_verifier_authority": "unit",
      "requires_parser_type": false,
      "dependency_obligation_ids": [],
      "residual_unknown_ids": [],
      "unavailable_authority": [],
      "required_next_evidence": [],
      "disposition": "active",
      "review_evidence_ids": ["ev_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]
    }
  ],
  "manifest": {
    "bindings": [
      {
        "obligation_id": "OBL-001",
        "owner": {
          "module_path": "src/protocol/deserializer.py",
          "symbol": "decode_packet",
          "owner_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
        },
        "parser_type": null,
        "original_cases": [
          {
            "kind": "positive",
            "evidence_id": "ev_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "location": "0x401000"
          }
        ],
        "fixtures": [
          {
            "fixture_id": "FIX-001",
            "case_kind": "positive",
            "authority": "unit",
            "evidence_ids": ["ev_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]
          }
        ],
        "verifier": {
          "verifier_id": "VER-001",
          "claim_id": "CLM-001",
          "command": "python3 -m unittest tests/test_deserializer.py",
          "authority": "unit",
          "status": "pass",
          "result_evidence_id": "ev_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          "enumerated_obligation_ids": ["OBL-001"],
          "nondeterminism": {
            "mode": "total-order",
            "specification": "Deterministic byte-stream framing"
          }
        }
      }
    ],
    "contradictions": []
  }
}
```

### 5.3 Residual Unknowns Lifecycle
Incomplete reverse engineering often tempts models to hallucinate missing fields. REA prevents this via an explicit **Residual Unknowns Lifecycle**:

```mermaid
sequenceDiagram
    participant Agent
    participant REA as REA Evidence Engine
    participant Ledger as .agents/ledger/unknowns.json

    Agent->>REA: record_unknown(question, context, authority_needed)
    REA-->>Ledger: Store unknown record with UUID & revision hash
    REA-->>Agent: Return unknown_id
    Note over Agent: Investigation proceeds; new evidence discovered
    Agent->>REA: verify_unknown_resolution(unknown_id, resolving_evidence_id)
    alt Evidence Validates Resolution
        REA-->>Ledger: Mark unknown resolved with cited evidence
        REA-->>Agent: Status: Resolved (PASS)
    else Evidence Insufficient
        REA-->>Agent: Status: Invalidation Error (REJECTED)
    end
```

- **`record_unknown`**: Formally records an unanswered question or missing specification authority with explicit revision tracking.
- **`list_unknowns`**: Queries active open heads.
- **`verify_unknown_resolution`**: Asserts that an unknown was resolved by citing concrete Evidence IDs. Silent closure of unknowns without evidence is strictly prohibited.

### 5.4 Formal Verification Gates
Before an implementation is declared complete, it must clear two formal gates:
1. **`evaluate_reconstruction_coverage`**: Measures implementation source code against the obligation ledger, calculating verified vs unmet obligations.
2. **`verify_reconstruction`**: Formally evaluates individual reconstruction claims against retained Evidence comparisons. Passes are granted only when supported by mathematical evidence.

---

## 6. Lifecycle Hook Harmonization & The Non-Interference Invariant

To resolve the frictions documented in Issues #44 and #45, the four primary lifecycle hooks in `harness/hooks/` are harmonized as follows:

### 6.1 `command_safety_hook.py` (Toolchain PATH & Batch Modes)
- **Problem**: In non-login subshells, `rea` commands fail with Exit Code 127 because `~/.local/share/pnpm` or `~/.npm-global/bin` is omitted from `PATH`. Commands wrapped in `command` (e.g. `command -v rea` or `command rea`) bypass toolchain detection. Additionally, interactive disassembler commands can hang waiting for stdin.
- **Remediation**:
  1. Add `"rea"` to `USER_TOOLCHAINS` in `harness/hooks/command_safety_hook.py`:
     ```python
     USER_TOOLCHAINS = (
         "agyis", "psl", "knot", "uv", "pnpm", "npm", "npx", "cargo", "rustc",
         "pytest", "ruff", "black", "mypy", "flake8", "tsc", "rea",
     )
     ```
  2. Extend host candidate PATH shims in `get_user_path_shims()` to cover global npm installations:
     ```python
     def get_user_path_shims() -> List[str]:
         candidates = [
             Path.home() / ".local/bin",
             Path.home() / ".cargo/bin",
             Path.home() / ".local/share/pnpm",
             Path.home() / ".npm-global/bin",
             Path.home() / ".pyenv/shims",
         ]
         return [str(p) for p in candidates if p.is_dir()]
     ```
  3. Extend `USER_TOOLCHAIN_REGEX` prefix wrapper to capture `command`:
     ```python
     USER_TOOLCHAIN_REGEX = re.compile(
         r"(?:^|[;&|]\s*|\b(?:sudo|xargs|nohup|exec|env|time|command)\s+)\s*(?:/[^\s]+/)?\b("
         + "|".join(USER_TOOLCHAINS)
         + r")\b"
     )
     ```
  4. Add `rea` package suggestions in `COMMON_PACKAGE_SUGGESTIONS`:
     ```python
     "rea": "Install via 'pnpm add -g rea-agents' or run with 'npx rea-agents'",
     ```
  5. Enforce non-interactive batch flags for low-level disassemblers (e.g. rewrite raw `gdb` to `gdb -batch`, `rizin` to `rizin -q`).

### 6.2 `anti_loop_hook.py` (Cleanroom Spec & Verification Exemptions)
- **Problem**: Reviewing cleanroom specifications during reverse engineering tripped sliding-window repeat denials ($\ge 4$ in 15 calls). Granting blanket immunity via `_is_peer_heartbeat` would create an unmonitored loophole where agents could endlessly loop reading the same spec. Furthermore, running REA verifiers did not reset loop counters because REA was missing from `TEST_VERIFICATION_PATTERNS`.
- **Remediation**:
  1. **Bounded Sliding-Window Spec Quota (No Blanket Immunity)**:
     - Do **NOT** place `docs/specs/**` into `_is_peer_heartbeat` (which grants blanket immunity bypassing all checks).
     - Instead, implement an elevated sliding-window frequency quota for specification files:
       ```python
       SPEC_DIR_PREFIXES = ("/docs/specs/", "docs/specs/", "/.agents/ledger/", ".agents/ledger/")
       SPEC_WINDOW_MAX_CALLS = 8  # Elevated from default 4 in 15-call window
       ```
     - **Strict Consecutive Repeat Enforcement**: Regardless of the elevated window quota, consecutive identical `read_file`/`view_file` calls are strictly enforced: $\ge 3$ consecutive calls to the exact same specification path are immediately denied to prevent cognitive lockup.
  2. Register REA verification commands in `TEST_VERIFICATION_PATTERNS`:
     ```python
     TEST_VERIFICATION_PATTERNS = (
         # ... existing runners ...
         r"(?:^|[\s;&|])rea\s+(?:verify|verify-reconstruction|test)\b",
         r"(?:^|[\s;&|])python3?\s+-m\s+harness(?:\.cli)?\s+(?:verify|verify-cleanroom)\b",
         r"(?:^|[\s;&|])agyis\s+verify\b",
     )
     ```
  3. Recognize background task logs from long-running REA operations without premature anti-polling blocks when accompanied by explicit time fences.

### 6.3 `completion_fence_hook.py` (Phase-Aware Cleanroom Gating)
- **Problem**: Issue #45 un-isolated merging marked `code_dirty = True` whenever `docs/specs/**` was edited. Agents performing pure reverse engineering were deadlocked upon trying to stop, forced to trigger the safety valve twice because no project software tests existed. Conversely, storing executable code in `docs/specs/**` could allow unverified code execution without test verification. Additionally, REA verifiers called via MCP (`call_mcp_tool`) were invisible to command-line completion fences.
- **Remediation**:
  1. **Phase-Aware Decoupling & Extension Constraints (DEF-01 Code-in-Specs Loophole Guard)**:
     - Introduce distinct state tracking for pure specification authoring vs production code dirtying.
     - **Declarative Extension Whitelist**: Only files with declarative extensions qualify for pure `spec_dirty`:
       ```python
       DECLARATIVE_SPEC_EXTENSIONS = (
           ".md", ".json", ".yaml", ".yml", ".proto", ".schema", ".fbs", ".toml", ".txt"
       )
       ```
     - **Code-in-Specs Guard**: Any modified file in `docs/specs/**` or `.agents/ledger/**` bearing a code extension (`.py`, `.ts`, `.rs`, `.go`, `.sh`, `.c`, `.cpp`, `.js`, etc.) **MUST trigger `code_dirty = True`** (dual dirty state), strictly requiring project unit test verification before completion.
     - Pure `spec_dirty = True` (with `code_dirty = False`) is set **only** when all modified files reside in `docs/specs/**` or `.agents/ledger/**` and possess exclusively declarative extensions.
  2. **Specification Clearance Routes & MCP Clearance (DEF-03)**:
     - When *only* `spec_dirty` is True and `code_dirty` is False, the completion fence permits termination without coercing software unit test suites, provided cleanroom verification is executed or recorded.
     - **CLI Verifier Route**: Executing `rea verify-reconstruction`, `rea test`, or `agyis verify --spec` resets `spec_dirty = False`.
     - **MCP Tool Interception (PostToolUse)**: `completion_fence_hook.py` intercepts MCP tool completions:
       ```python
       def handle_post_tool_use(tool_name: str, args: dict, result: dict) -> None:
           if tool_name == "call_mcp_tool":
               inner_tool = args.get("ToolName", "")
               if inner_tool in ("verify_reconstruction", "evaluate_reconstruction_coverage"):
                   if result.get("status") != "error":
                       clear_spec_dirty()
           elif "verify_reconstruction" in tool_name or "evaluate_reconstruction_coverage" in tool_name:
               if result.get("status") != "error":
                   clear_spec_dirty()
       ```
  3. **Formal Ledger & Manifest Clearance Schema (DEF-06)**:
     - **Primary Obligation Ledger (`.agents/ledger/obligation_ledger.json`, `REA 6.9.0`)**: `is_manifest_verified()` (`harness/hooks/fence_classifiers.py`) prioritizes `.agents/ledger/obligation_ledger.json` via `validate_obligation_ledger()` (`harness/cleanroom/obligation.py`), checking valid `evidence_bundle` (`artifacts`, `captures`, `environments`, `providers`, `records`, `scenarios`, `unknowns`), non-empty `reviewed_obligations` (`obligation_id`, `obligation_version >= 1`, `target` strictObject, `disposition` in `{"active", "blocked", "out-of-scope"}`), and `manifest` (`bindings` list, zero unresolved `contradictions`), rejecting deprecated top-level `"$schema"`. Generated via `agyis verify --scaffold`.
     - **Legacy Clearance Manifest Fallback (`.agents/ledger/manifest.json`)**: If `obligation_ledger.json` is absent, `.agents/ledger/manifest.json` clears `spec_dirty` when conforming to the schema below:
       ```json
       {
         "$schema": "https://json-schema.org/draft/2020-12/schema",
         "title": "CleanroomManifest",
         "type": "object",
         "required": ["status", "evidence_hash", "target", "verified_at", "verifier", "obligations"],
         "properties": {
           "status": {
             "type": "string",
             "enum": ["verified"]
           },
           "evidence_hash": {
             "type": "string",
             "pattern": "^[a-f0-9]{64}$"
           },
           "target": { "type": "string" },
           "verified_at": { "type": "string", "format": "date-time" },
           "verifier": { "type": "string" },
           "obligations": {
             "type": "array",
             "minItems": 1,
             "items": {
               "type": "object",
               "required": ["id", "status", "proof"],
               "properties": {
                 "id": { "type": "string" },
                 "status": { "type": "string", "enum": ["satisfied"] },
                 "proof": { "type": "string" }
               }
             }
           }
         }
       }
       ```
     - **Validation Invariant**: Either `.agents/ledger/obligation_ledger.json` passes `validate_obligation_ledger()`, or `.agents/ledger/manifest.json` declares `"status": "verified"`, a 64-character lowercase SHA-256 `evidence_hash`, and non-empty `"satisfied"` `obligations`.
     - **Exact Cleanroom Rejection Message**: When `evaluate_stop` is invoked with `spec_dirty == True` and `code_dirty == False`, the fence rejects termination with the verbatim message:
       ```
       Cleanroom Verification Required: Unverified cleanroom contract edits detected in: <files>. Execute 'rea verify-reconstruction' or 'agyis verify --spec' before stopping.
       ```
  4. **Universal Verifier Recognition**: Register REA verification patterns (`rea verify`, `rea verify-reconstruction`, `agyis verify`, `agyis verify --spec`) in `UNIVERSAL_TEST_RUNNER_PATTERNS` so executing verification clears cleanroom dirty state.
  5. **Scratch Path Isolation**: Exempt REA scratch paths from dirty tracking:
     ```python
     def is_ephemeral_scratch_path(path_str: str) -> bool:
         # ... existing scratch checks ...
         if "/.rea/" in norm or norm.startswith(".rea/"):
             return True
         if "/artifacts/rea/" in norm or "/decompiled/" in norm:
             return True
         return False
     ```

### 6.4 `output_compactor_hook.py` (Bounded Disassembly Compaction)
- **Problem**: Calling `.splitlines()` and iterating line-by-line across multi-megabyte disassembly dumps (e.g. 50MB objdump) causes memory exhaustion (OOM) and exceeds the 5.0-second hook timeout in `hooks.json` (DEFECT-001 / DEF-04).
- **Remediation**:
  1. **Character-Offset Slicing Before Line Splitting**:
     - When middle segment length exceeds 200KB (`len(middle) > 200_000`), slicing **MUST** occur on raw character offsets prior to calling `.splitlines()`:
       ```python
       if len(middle) > 200_000:
           head_chunk = middle[:100_000]
           tail_chunk = middle[-100_000:]
           # Split only the bounded 100KB chunks
           candidate_lines = head_chunk.splitlines() + tail_chunk.splitlines()
       ```
     - This bounds line processing to at most ~200KB of text regardless of total dump size (e.g. 100MB), completely eliminating OOM and timeout failures.
  2. **Preserved Error Line Bounding**: Diagnostic and error lines scanned from the candidate lines are bounded to a **maximum of 50 lines**.
  3. **Preserve JSON Syntax**: When compacting JSON outputs, maintain structural outer brackets rather than raw character truncations that corrupt syntax.

---

## 7. Opt-In Provisioning & UX Architecture

To maintain the ADR-014 product-project separation and safeguard host environments, REA integration is strictly **opt-in**.

### 7.1 CLI Invocations Matrix

```bash
# ==============================================================================
# 1. Workspace Initialization & Onboarding
# ==============================================================================
agyis init                                     # Standard workspace initialization (REA omitted)
agyis init --experimental-rea                  # Provisions REA skills & scaffolds .agents/ledger/
agyis onboard --experimental-rea               # Fleet onboarding with REA support

# ==============================================================================
# 2. Diagnostics & Verification Matrix
# ==============================================================================
agyis doctor                                   # Standard host audit (STRICT SUB-SECOND <1.0s)
                                               # REA probed via zero-delay fast path; 0 warnings added

agyis doctor --experimental-rea                # Comprehensive REA diagnostic sweep:
                                               # • Probes rea binary version (6.9.0+ / 255 MCP tools)
                                               # • Probes mcp_config.json registration
                                               # • Probes JDK 21+ & Ghidra 11.0+/12.2+ installation
                                               # • Deep provider scan (rea providers --json)

# ==============================================================================
# 3. Safe Zero-Sudo Auto-Healing
# ==============================================================================
agyis doctor --experimental-rea --heal         # Safe user-space auto-healing:
                                               # • Installs rea-agents via pnpm/npm if missing
                                               # • Writes mcp_config.json with JDK 21 & Ghidra paths
                                               # • Provisions reverse-engineer-anything skill

# ==============================================================================
# 4. Global Installation
# ==============================================================================
agyis install -g --experimental-rea            # Configures global MCP and installs global skill
```

### 7.2 Strict Preservation of the Sub-Second Doctor Invariant
In `harness/runtime/doctor.py`:
- When `--experimental-rea` is **omitted**:
  - The runtime performs a fast `shutil.which("rea")` check (<0.005s).
  - Heavy disassembler discovery (`rea providers --json`) is **skipped entirely**.
  - If REA is unconfigured or absent, `doctor.py` outputs a concise informational note and adds **0 warnings** to the summary tally.
  - Overall `agyis doctor` runtime remains strictly within the **<1.0s benchmark target**.
- When `--experimental-rea` is **present**:
  - Deep diagnostics are executed, reporting exact statuses for Ghidra, Hopper, IDA, JADX, and MCP configuration:
    - **Ghidra**: Traverses dynamic JVM discovery ladder (`$JAVA_HOME` -> Linux OpenJDK glob -> Ubuntu amd64 -> Fedora JRE -> macOS Homebrew -> macOS PKG), asserts JDK 21+ compliance, and verifies headless `analyzeHeadless` execution. If JDK 21+ is missing, reports fallback chain (`Ghidra -> Rizin -> objdump -> built-in parsers`).
    - **Hopper (Headless Hopper Contract)**: Probes for `$DISPLAY` / `$WAYLAND_DISPLAY`, tests for `xvfb-run`, or verifies `QT_QPA_PLATFORM=offscreen`. If neither a display socket nor a virtual framebuffer is available, marks Hopper `unavailable: "no display socket"` and confirms fallback routing to Ghidra or Rizin without throwing Qt platform exceptions.
    - **IDA Pro**: Audits headless batch execution profile, verifying autonomous flags (`-A`, `-B`, `-o`) and sandbox isolation.
    - **JADX**: Validates JDK 17+ runtime and accessibility of `REA_JADX_MCP_JAR`.
    - **MCP Server**: Audits `~/.gemini/config/mcp_config.json` registration, confirming portable command resolution and schema profiles.

---

## 8. Accelerated Decompilation Architecture: Direct Mount, Daemon Bridge & Query Cache (Issue #113, `PSL-RE-001`)

To eliminate the severe latency bottlenecks encountered during reverse engineering operations on large closed-source binaries (`>10 MB`, e.g., `<68MB-PE32+-target.exe>` with `356,000` procedures and `817,000` strings), Agyis Harness introduces a 3-tier acceleration architecture satisfying the sub-2-second decompilation benchmark required by **`PSL-RE-001 §2`**.

### 8.1 Empirical Latency Benchmarks (Target: 68MB PE32+ Binary)

| Tier | Optimization Architecture | Execution Pathway | Latency | Speedup |
| :--- | :--- | :--- | :--- | :--- |
| **Baseline** | Stock REA + Project Reuse (ADR-028) | Ad-hoc CLI + 1.3GB Disk Clone | `132.10s` | 1.0x |
| **Optimization 2** | **Direct In-Place Mount** (`-readOnly -noanalysis`) | Ad-hoc CLI (Zero Clone) | `9.78s` | **13.5x** |
| **Optimization 1** | **Persistent MCP Bridge Daemon** | In-Memory MCP Tool Invocation | `~0.20s - 0.80s` | **165x - 660x** |
| **Optimization 3** | **Deterministic Query Cache** | Local Disk Cache (`.dirtyroom/cache/`) | `<0.005s` | **>26,000x** |

### 8.2 Optimization 1: Persistent REA MCP Bridge Daemon Support
- **Mechanism**: The REA MCP server maintains an open connection with persistent language provider and decompiler instances in memory, eliminating cold JVM startup penalties (8–10s) on every query.
- **Supervisor Daemon (`agyis re daemon [status|start|stop]`)**:
  - `start`: Launches detached supervisor holding open stdio connection to `rea mcp`, performs MCP protocol `initialize` handshake to warm up providers, and writes PID to `.dirtyroom/logs/rea_daemon.pid`.
  - `status`: Inspects daemon liveness, uptime, child PID, mounted Ghidra projects, and MCP registration.
  - `stop`: Gracefully terminates the daemon process via SIGTERM with SIGKILL fallback.
- **Environment Injection**: `harness/runtime/tool_checks_rea.py` automatically injects `REA_GHIDRA_PROJECT_DIR`, `REA_GHIDRA_PROJECT_NAME`, `REA_GHIDRA_PROJECT_PATH`, `REA_GHIDRA_DIRECT_MOUNT="1"`, and `AGYIS_DIRTYROOM` into the generated `mcpServers.rea.env` block.

### 8.3 Optimization 2: Direct In-Place Mount (`REA_GHIDRA_DIRECT_MOUNT=1`)
- **Mechanism**: Eliminates the 1.3GB disk cloning step in REA:
  - Bypasses `copyExistingGhidraProject` in `dist/ghidra/GhidraProjectSnapshot.js`, `dist/ghidra/GhidraLauncher.js`, `dist/mcp/binary-*.js`, and `dist/cli-runtime/binary-*.js`, plus `GhidraReleasePolicy.js` for Ghidra `12.2+` compatibility.
  - Enforces `-noanalysis` and `-readOnly` flags when launching Ghidra's `analyzeHeadless` on the repository root.
  - Transparently injected via `harness/hooks/command_safety_hook.py` (`inject_rea_dirtyroom_env`) for any terminal command invoking `rea decompile/disasm/xrefs/read-bytes`.

### 8.4 Optimization 3: Deterministic Decompiler Query Cache
- **Mechanism**: Caches decompiled C pseudocode under `.dirtyroom/cache/decompile/{binary}_{bin_id}_{procedure}.c`.
- **Cache Management (`agyis re cache [status|clear]`)**:
  - `status`: Inspects cache disk usage, file counts, hit rates, and category breakdowns (<5ms responses).
  - `clear`: Purges cached entries (`--type all|decompile`) and resets hit counters with `--dry-run` preview.
  - `cmd_decompile`: Inspects cache before launching any process, returning cached output in `<5ms`. CLI flag `--no-cache` forces cache bypass and refreshes the cache entry with fresh decompiler output.

### 8.5 Turnkey Dirtyroom Seeding, Priming & Routine Hygiene
*Full operational runbook documented in [`docs/runbooks/dirtyroom-operations.md`](../runbooks/dirtyroom-operations.md).*
- **Turnkey PCAP Seeding (`agyis re seed`)**: Ingests libpcap and pcapng frames directly into the SQLite `packets` table, extracting IP/port tuples, payload lengths, and frame summaries, while establishing formal linkages to target binary records and run tracking.
- **Decompiler Cache Priming (`agyis re prime`)**: Pre-warms the deterministic query cache on top-priority functions (exported symbols and largest subroutines) or user-supplied symbol files, ensuring subsequent queries hit the `<5ms` cache tier.
- **Orphan Lock & Storage Hygiene (`agyis re clean`)**: Safely detects and purges stale Ghidra `.lock` files after `/proc` safety checks, prunes rotated logs (while preserving active daemon logs), and executes SQLite `VACUUM`, `REINDEX`, and `ANALYZE` to reclaim disk space.

### 8.6 Address Inspection, Translation & Dual-Mode Cross-References
- **Address Resolution & Translation Engine (`harness/re/address.py`, `agyis re addr`)**: Parses PE32/PE32+ DOS, COFF, and Optional Headers; translates bidirectionally across Virtual Address (VA), Relative Virtual Address (RVA), and File Offset; identifies containing PE sections with access permissions; correlates addresses to canonical symbols, strings, and RTTI classes in `<2ms`.
- **Smart Procedure Resolution (`cmd_decompile`)**: Automatically intercepts numeric interior addresses passed to `agyis re decompile <address>`, queries the `functions` table for the containing procedure boundary, resolves to the canonical entry symbol (e.g. `FUN_140bc8790 (+0x5)`), and passes the entrypoint to the decompiler backend.
- **Dual-Mode Cross-References (`harness/re/xrefs.py`, `agyis re xrefs`)**:
  - *Mode A (Pre-analyzed SQLite Cache)*: Sub-millisecond queries on `xrefs` table for known call and data references.
  - *Mode B (Direct Binary Scanning)*: Scans executable `.text` sections for relative `CALL` (`0xE8`) and `JMP` (`0xE9`) instruction opcodes; scans `.rdata`/`.data` sections for 4-byte (PE32) and 8-byte (PE32+) pointer references. Supports `--type {all,code,data}` filtering and `--json` export.

---

## 9. Verification & Compliance Gates

All REA integration modules, hook gates, and cleanroom verifiers must satisfy deterministic automated checks prior to release:

| Layer / Scope | Verification Command | Target Contract |
| :--- | :--- | :--- |
| **Cleanroom Specs Gate** | `agyis verify --spec` | Asserts `docs/specs/**` contains zero executable code files and clears `spec_dirty`. |
| **Obligation Ledger Scaffold** | `agyis verify --scaffold` | Generates `.agents/ledger/obligation_ledger.json` (`REA 6.9.0` strictObject) schema template. |
| **Full Reconstruction Gate** | `agyis verify` / `rea verify-reconstruction` | Validates `.agents/ledger/obligation_ledger.json` (and legacy `manifest.json`) obligations against evidence. |
| **Zero-Delay Doctor** | `agyis doctor` | Confirms sub-second (`<1.0s`) baseline check without launching heavy disassembler scans. |
| **Opt-In REA Audit** | `agyis doctor --experimental-rea` | Audits `rea`, `mcp_config.json`, JDK 21+, Ghidra, Hopper, IDA Pro, and JADX provider chains. |
| **Address Inspection Gate** | `agyis re addr 0x... --json` | Validates VA <-> RVA <-> File Offset mapping and symbol attribution in `<2ms`. |
| **Cross-Reference Gate** | `agyis re xrefs 0x... --json` | Validates dual-mode (SQLite + binary direct scan) xref resolution across code and data. |
| **Query Cache Status Gate** | `agyis re cache status` | Asserts active cache directory, sub-millisecond retrieval, and accurate hit rates. |
| **Daemon Bridge Status Gate** | `agyis re daemon status` | Inspects persistent MCP supervisor state and direct-mount environment. |
| **Dirtyroom Seeding Gate** | `agyis re seed --json` | Validates PCAP frame ingestion and binary run linkage into SQLite. |
| **Cache Priming Gate** | `agyis re prime --dry-run` | Validates candidate priority function selection and cache key generation. |
| **Hygiene Cleanup Gate** | `agyis re clean --dry-run` | Verifies safe stale lock detection, log pruning, and database vacuum paths. |
| **Full Harness Test Suite** | `python3 -m harness.cli test` | Executes hermetic unit and contract suites across all runtime, hook, and cleanroom modules. |

---

## 10. Governing Standards & Compliance
This technical specification is issued under the authority of Purrfect Software Limited (PSL) and is governed by the **ICARO-42/b Ordinance**. All implementations must adhere strictly to the Non-Interference Invariant, the Sub-Second Benchmark Invariant, and the Product vs. Project Bifurcation (ADR-014).
