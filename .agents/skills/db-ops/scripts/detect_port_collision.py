#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
detect_port_collision.py: Dynamic Database Port Collision Detection (Issue #62).

Standalone, zero-dependency standard library tool for diagnosing database port
occupancy (default 5432), attributing container/process ownership across Docker
and host processes, finding free ports (5432..5442), and surgically re-binding
.env files preserving comments, quotes, and URL query parameters.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

RE_POSTGRES_PORT = re.compile(
    r'^(\s*POSTGRES_PORT\s*=\s*[\'"]?)(\d+)([\'"].*|.*)$',
    re.MULTILINE,
)

RE_DATABASE_URL = re.compile(
    r'^(\s*(?:DATABASE_URL|DIRECT_URL|POSTGRES_PRISMA_URL|POSTGRES_URL|POSTGRES_URL_NON_POOLING)\s*=\s*[\'"]?)'
    r'(postgres(?:ql)?://(?:[^@/\n]+@)?(?:[^:/\s\n?#\'"]+))'
    r'(?::\d+)?'
    r'(/[^?\s\n#\'"]*)?'
    r'(\?[^#\s\n\'"]*)?'
    r'([\'"].*|.*)$',
    re.MULTILINE,
)


def is_port_in_use(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """
    Tier 1: Non-blocking socket connect and bind probe on host:port.
    Returns True if port is occupied / active, False if unbound and available.
    """
    # 1. Connect probe (is a daemon actively listening?)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            if s.connect_ex((host, port)) == 0:
                return True
    except Exception:
        pass

    # 2. Bind probe (is the address/port reserved by a socket or TIME_WAIT?)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
    except OSError:
        return True
    except Exception:
        pass

    return False


def probe_docker_port_owner(
    port: int,
    workspace_root: Optional[Path | str] = None,
    timeout: float = 2.0,
) -> Optional[Dict[str, Any]]:
    """
    Tier 2: Probe Docker daemon for container publishing target port.
    Parses container name, status, image, and compose project labels.
    """
    try:
        res = subprocess.run(
            ["docker", "ps", "--filter", f"publish={port}", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    if res.returncode != 0 or not res.stdout.strip():
        return None

    effective_ws = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()

    for line in res.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        cid = data.get("ID", "")
        cname = data.get("Names", "")
        image = data.get("Image", "")
        status = data.get("Status", "")
        ports = data.get("Ports", "")
        raw_labels = data.get("Labels", "") or ""

        labels: Dict[str, str] = {}
        for part in raw_labels.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                labels[k.strip()] = v.strip()

        project = labels.get("com.docker.compose.project", "")
        working_dir = labels.get("com.docker.compose.project.working_dir", "")
        service = labels.get("com.docker.compose.service", "")

        is_self = False
        if working_dir:
            try:
                wd_path = Path(working_dir).resolve()
                if effective_ws == wd_path or effective_ws in wd_path.parents or wd_path in effective_ws.parents:
                    is_self = True
            except Exception:
                pass

        if not is_self:
            ws_name = effective_ws.name.lower()
            if project and project.lower() == ws_name:
                is_self = True
            elif cname and ws_name in cname.lower():
                is_self = True

        return {
            "type": "docker",
            "id": cid,
            "name": cname,
            "image": image,
            "status": status,
            "ports": ports,
            "project": project,
            "working_dir": working_dir,
            "service": service,
            "is_self": is_self,
        }

    return None


def probe_host_process_owner(port: int, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    """
    Tier 3: Fallback inspection via lsof or ss when port is occupied outside Docker.
    """
    # Attempt 1: lsof
    try:
        res = subprocess.run(
            ["lsof", "-iTCP:" + str(port), "-sTCP:LISTEN", "-P", "-n"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            lines = res.stdout.strip().splitlines()
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 3:
                    cmd_name = parts[0]
                    try:
                        pid = int(parts[1])
                    except ValueError:
                        pid = None
                    user = parts[2]
                    return {
                        "type": "host_process",
                        "pid": pid,
                        "name": cmd_name,
                        "user": user,
                        "details": f"Process '{cmd_name}' (PID: {pid}, User: {user})",
                    }
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Attempt 2: ss
    try:
        res = subprocess.run(
            ["ss", "-tulpn", f"sport = :{port}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            for line in res.stdout.strip().splitlines():
                if f":{port}" in line:
                    m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
                    if m:
                        cmd_name = m.group(1)
                        pid = int(m.group(2))
                        return {
                            "type": "host_process",
                            "pid": pid,
                            "name": cmd_name,
                            "user": None,
                            "details": f"Process '{cmd_name}' (PID: {pid})",
                        }
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return {
        "type": "host_process",
        "pid": None,
        "name": "unknown",
        "user": None,
        "details": f"Non-docker process or daemon bound to port {port}",
    }


def find_free_port(start_port: int = 5432, max_port: int = 5442, host: str = "127.0.0.1") -> Optional[int]:
    """
    Scans candidate ports in range [start_port, max_port] and returns first unbound port.
    """
    for p in range(start_port, max_port + 1):
        if not is_port_in_use(p, host=host):
            return p
    return None


def check_port_collision(
    port: int = 5432,
    workspace_root: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """
    Executes full 3-tier collision ladder:
    Returns dict with status ("UNBOUND", "SELF_OWNED", "FOREIGN_COLLISION"),
    port, collision (bool), owner, free_port, details, remediation.
    """
    if not is_port_in_use(port):
        return {
            "status": "UNBOUND",
            "collision": False,
            "port": port,
            "owner": None,
            "free_port": port,
            "details": f"Port {port} is unbound and free for database binding.",
            "remediation": None,
        }

    # Tier 2: Docker Attribution
    docker_owner = probe_docker_port_owner(port, workspace_root=workspace_root)
    if docker_owner:
        if docker_owner.get("is_self"):
            return {
                "status": "SELF_OWNED",
                "collision": False,
                "port": port,
                "owner": docker_owner,
                "free_port": None,
                "details": f"Port {port} is active and owned by current workspace container '{docker_owner.get('name')}'.",
                "remediation": None,
            }
        else:
            free_p = find_free_port(start_port=port, max_port=port + 10)
            cid = docker_owner.get("id") or docker_owner.get("name")
            cproj = docker_owner.get("project") or "unknown"
            cname = docker_owner.get("name") or cid
            remediation = (
                f"Stop colliding container ('docker stop {cid}') or rebind local database port "
                f"(e.g. to {free_p or (port + 1)}) via: detect_port_collision.py --find-free --rebind --env .env"
            )
            return {
                "status": "FOREIGN_COLLISION",
                "collision": True,
                "port": port,
                "owner": docker_owner,
                "free_port": free_p,
                "details": f"Port {port} collision: occupied by foreign container '{cname}' (project: '{cproj}').",
                "remediation": remediation,
            }

    # Tier 3: Host Process Fallback
    proc_owner = probe_host_process_owner(port)
    free_p = find_free_port(start_port=port, max_port=port + 10)
    pname = (proc_owner or {}).get("name") or "unknown"
    pid = (proc_owner or {}).get("pid")
    pid_str = f" (PID: {pid})" if pid else ""
    remediation = (
        f"Terminate colliding host process or rebind local database port "
        f"(e.g. to {free_p or (port + 1)}) via: detect_port_collision.py --find-free --rebind --env .env"
    )
    return {
        "status": "FOREIGN_COLLISION",
        "collision": True,
        "port": port,
        "owner": proc_owner,
        "free_port": free_p,
        "details": f"Port {port} collision: occupied by host process '{pname}'{pid_str}.",
        "remediation": remediation,
    }


def rebind_env_file(env_path: Path | str, new_port: int) -> Tuple[bool, str]:
    """
    Surgically re-binds POSTGRES_PORT and DATABASE_URL in the target .env file,
    preserving quotes, URL query parameters, passwords, and surrounding comments.
    """
    p = Path(env_path)
    if not p.is_file():
        return False, f"Target env file does not exist: {env_path}"

    try:
        content = p.read_text(encoding="utf-8")
    except Exception as exc:
        return False, f"Failed to read {env_path}: {exc}"

    new_content, n_url = RE_DATABASE_URL.subn(
        r'\g<1>\g<2>:' + str(new_port) + r'\g<3>\g<4>\g<5>',
        content,
    )
    new_content, n_port = RE_POSTGRES_PORT.subn(
        r'\g<1>' + str(new_port) + r'\g<3>',
        new_content,
    )

    if n_url > 0 or n_port > 0:
        try:
            p.write_text(new_content, encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to write updated {env_path}: {exc}"
        return True, f"Updated {n_port} port variable(s) and {n_url} database URL(s) to port {new_port} in {env_path}."

    return False, f"No matching POSTGRES_PORT or DATABASE_URL variables found in {env_path}."


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect database port collisions across Docker containers and host processes (Issue #62)."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Probe specified port for collision (default: 5432).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5432,
        help="Port to inspect (default: 5432).",
    )
    parser.add_argument(
        "--find-free",
        action="store_true",
        help="Scan candidate ports 5432-5442 for first unbound port.",
    )
    parser.add_argument(
        "--rebind",
        action="store_true",
        help="Rebind .env file with discovered or specified free port.",
    )
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="Path to .env file to rebind.",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Workspace root to determine container ownership.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    # If no flags provided, default to --check
    do_check = args.check or (not args.find_free and not args.rebind)
    do_find_free = args.find_free
    do_rebind = args.rebind

    check_info: Dict[str, Any] = {}
    free_port: Optional[int] = None
    action_taken = "none"
    rebind_message: Optional[str] = None

    if do_check:
        check_info = check_port_collision(port=args.port, workspace_root=args.workspace)
        free_port = check_info.get("free_port")

    if do_find_free or (do_rebind and free_port is None):
        free_port = find_free_port(start_port=args.port, max_port=args.port + 10)
        if not check_info:
            check_info = {
                "status": "UNBOUND" if free_port == args.port else "OCCUPIED",
                "port": args.port,
                "owner": None,
                "free_port": free_port,
                "details": f"First free candidate port is {free_port}." if free_port else "No free port in range.",
            }

    if do_rebind:
        if not args.env:
            err_msg = "Error: --env <path> is required when --rebind is specified."
            if args.json:
                print(json.dumps({"status": "ERROR", "error": err_msg}, indent=2))
            else:
                sys.stderr.write(f"{err_msg}\n")
            return 1

        target_port = free_port if free_port is not None else (args.port + 1)
        ok, msg = rebind_env_file(args.env, target_port)
        rebind_message = msg
        action_taken = "rebind" if ok else "rebind_failed"

    output_payload: Dict[str, Any] = {
        "status": check_info.get("status", "UNKNOWN"),
        "port": args.port,
        "owner": check_info.get("owner"),
        "free_port": free_port,
        "action_taken": action_taken,
        "details": check_info.get("details", ""),
    }
    if rebind_message:
        output_payload["rebind_message"] = rebind_message
    if check_info.get("remediation"):
        output_payload["remediation"] = check_info.get("remediation")

    if args.json:
        print(json.dumps(output_payload, indent=2))
    else:
        print(f"Database Port ({args.port}) Status: {output_payload['status']}")
        print(f"Details: {output_payload['details']}")
        if output_payload.get("owner"):
            owner = output_payload["owner"]
            owner_name = owner.get("name") or owner.get("id") or "unknown"
            owner_type = owner.get("type", "unknown")
            print(f"Owner: {owner_name} ({owner_type})")
        if free_port:
            print(f"Candidate Free Port: {free_port}")
        if output_payload.get("remediation"):
            print(f"Remediation: {output_payload['remediation']}")
        if rebind_message:
            print(f"Rebind: {rebind_message}")

    if do_rebind:
        return 0 if action_taken == "rebind" else 1

    if do_find_free and not do_check:
        return 0 if free_port is not None else 1

    if do_check:
        if check_info.get("status") == "FOREIGN_COLLISION":
            return 1
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
