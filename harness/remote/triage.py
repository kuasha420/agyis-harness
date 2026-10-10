# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
PSL Harness: Remote Diagnostic & Cloud/Mesh Triage Engine (ADR-027).

Gathers multi-component health diagnostics (ports, services, resources, logs)
and renders deterministic, compact (<2KB) Markdown reports.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shlex
import subprocess
from typing import Any, Dict, List, Optional

from harness.remote.runner import RemoteRunner


class RemoteTriage:
    """
    Diagnostic engine for remote host troubleshooting and health inspection.
    """

    PROFILES = ("all", "ports", "services", "resources", "logs")

    @classmethod
    def build_triage_probe(
        cls,
        profile: str = "all",
        service: Optional[str] = None,
        lines: int = 50,
    ) -> str:
        """
        Builds a compact, portable shell probing command based on the requested profile.
        """
        bounded_lines = min(max(lines, 5), 200)

        parts: List[str] = ["set +e"]

        if profile in ("all", "resources"):
            parts.append("echo '=== HOST ==='")
            parts.append("hostname 2>/dev/null || uname -n")
            parts.append("uptime 2>/dev/null")
            parts.append("echo '=== RESOURCES ==='")
            parts.append("free -m 2>/dev/null || cat /proc/meminfo | head -n 4")
            parts.append("df -h / 2>/dev/null")

        if profile in ("all", "ports"):
            parts.append("echo '=== PORTS ==='")
            parts.append("ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null || lsof -iTCP -sTCP:LISTEN -P -n 2>/dev/null | head -n 25")

        if profile in ("all", "services"):
            parts.append("echo '=== SERVICES ==='")
            parts.append("systemctl --failed --no-pager 2>/dev/null || true")
            parts.append("if command -v pm2 >/dev/null 2>&1; then pm2 jlist 2>/dev/null || pm2 list 2>/dev/null; fi")
            parts.append("if command -v docker >/dev/null 2>&1; then docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null; fi")

        if profile in ("all", "logs") or service:
            parts.append("echo '=== LOGS ==='")
            if service:
                parts.append(
                    f"journalctl -u {shlex.quote(service)} -n {bounded_lines} --no-pager 2>/dev/null || "
                    f"if command -v pm2 >/dev/null 2>&1; then pm2 logs {shlex.quote(service)} --lines {bounded_lines} --nostream 2>/dev/null; fi"
                )
            elif profile == "logs":
                parts.append(
                    f"journalctl -n {bounded_lines} -p err..emerg --no-pager 2>/dev/null || "
                    f"tail -n {bounded_lines} /var/log/syslog 2>/dev/null || "
                    f"dmesg -T 2>/dev/null | tail -n {bounded_lines}"
                )

        return "; ".join(parts)

    @classmethod
    def format_triage_markdown(
        cls,
        raw_output: str,
        target: str,
        profile: str = "all",
        max_bytes: int = 2048,
    ) -> str:
        """
        Parses raw triage probe output and formats it into a deterministic, compact (<2KB) Markdown report.
        """
        sections: Dict[str, List[str]] = {}
        current_section = "GENERAL"
        sections[current_section] = []

        for line in raw_output.splitlines():
            line_strip = line.strip()
            if line_strip.startswith("=== ") and line_strip.endswith(" ==="):
                current_section = line_strip[4:-4].strip()
                sections[current_section] = []
            else:
                sections[current_section].append(line)

        lines_out: List[str] = [
            f"### 🩺 Remote Triage Report: `{target}` (Profile: `{profile}`)",
            "",
        ]

        # Host & Resources
        if "HOST" in sections or "RESOURCES" in sections:
            lines_out.append("#### 💻 Host & Resources")
            host_lines = sections.get("HOST", [])
            if host_lines:
                lines_out.append(f"- **Uptime**: `{host_lines[-1].strip() if host_lines else 'N/A'}`")
            res_lines = sections.get("RESOURCES", [])
            if res_lines:
                disk_line = [l for l in res_lines if "/" in l.split()]
                if disk_line:
                    lines_out.append(f"- **Disk (/)**: `{disk_line[0].strip()}`")
                mem_line = [l for l in res_lines if l.startswith("Mem:")]
                if mem_line:
                    lines_out.append(f"- **Memory**: `{mem_line[0].strip()}`")
            lines_out.append("")

        # Ports
        if "PORTS" in sections:
            lines_out.append("#### 🌐 Listening Sockets")
            port_lines = [
                l.strip()
                for l in sections["PORTS"]
                if l.strip() and not l.startswith("State") and not l.startswith("Active")
            ]
            if port_lines:
                lines_out.append("```")
                for pl in port_lines[:15]:
                    lines_out.append(pl[:100])
                lines_out.append("```")
            else:
                lines_out.append("_No listening ports discovered or permission denied._")
            lines_out.append("")

        # Services
        if "SERVICES" in sections:
            lines_out.append("#### ⚙️ Services Status")
            svc_lines = [l.strip() for l in sections["SERVICES"] if l.strip()]
            pm2_parsed = False
            raw_svc_text = "\n".join(svc_lines)
            try:
                m = re.search(r"\[\s*\{.*\}\s*\]", raw_svc_text, re.DOTALL)
                if m:
                    pm2_list = json.loads(m.group(0))
                    if pm2_list:
                        lines_out.append("**PM2 Processes:**")
                        for p in pm2_list[:10]:
                            p_name = p.get("name", "unknown")
                            p_status = p.get("pm2_env", {}).get("status", "unknown")
                            p_restarts = p.get("pm2_env", {}).get("restart_time", 0)
                            lines_out.append(f"- `{p_name}`: `{p_status}` (restarts: {p_restarts})")
                        pm2_parsed = True
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass

            other_lines = [
                l
                for l in svc_lines
                if not l.startswith("[")
                and not l.startswith("{")
                and not l.startswith("]")
                and not l.startswith("}")
            ]
            if other_lines:
                lines_out.append("```")
                for ol in other_lines[:12]:
                    lines_out.append(ol[:100])
                lines_out.append("```")
            elif not pm2_parsed:
                lines_out.append("_No failed units or active containers detected._")
            lines_out.append("")

        # Logs
        if "LOGS" in sections:
            lines_out.append("#### 📜 Diagnostic Logs")
            log_lines = [l.strip() for l in sections["LOGS"] if l.strip()]
            if log_lines:
                lines_out.append("```")
                for ll in log_lines[-20:]:
                    lines_out.append(ll[:100])
                lines_out.append("```")
            else:
                lines_out.append("_No log entries captured._")
            lines_out.append("")

        report = "\n".join(lines_out).strip()

        # Enforce deterministic <2KB bound
        report_bytes = report.encode("utf-8")
        if len(report_bytes) > max_bytes:
            truncated = report_bytes[: max_bytes - 60].decode("utf-8", errors="ignore")
            if truncated.count("```") % 2 != 0:
                truncated += "\n```"
            truncated += "\n\n_(output bounded to <2KB)_"
            return truncated

        return report

    @classmethod
    def run_triage(
        cls,
        runner: RemoteRunner,
        target: str,
        profile: str = "all",
        service: Optional[str] = None,
        lines: int = 50,
        port: Optional[int] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Executes triage probe and returns structured diagnostic dict.
        """
        probe_cmd = cls.build_triage_probe(profile=profile, service=service, lines=lines)
        result = runner.run(
            target=target,
            remote_cmd=probe_cmd,
            login_shell=True,
            port=port,
            timeout=timeout,
        )

        report_md = cls.format_triage_markdown(
            raw_output=result.stdout or result.stderr,
            target=target,
            profile=profile,
        )

        return {
            "target": target,
            "profile": profile,
            "service": service,
            "exit_code": result.returncode,
            "report_markdown": report_md,
            "raw_output": result.stdout,
        }


RemoteTriageEngine = RemoteTriage

