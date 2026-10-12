# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Centralized Telemetry Hub Application (ADR-030).

Starlette ASGI web service providing:
- Health checking probe
- GitHub Personal Access Token verification against purrfectsoft org
- Batch telemetry push ingestion with upsert
- Delta replication pull with anti-echo filtering
"""

from __future__ import annotations

import os
from typing import Optional

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from server.auth import verify_github_token
from server.storage import Storage, get_storage


def extract_token(request: Request) -> Optional[str]:
    """Extracts bearer token from Authorization header or query parameter."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return request.query_params.get("token")


async def health_endpoint(request: Request) -> JSONResponse:
    """Zero-auth health check probe."""
    storage: Storage = getattr(request.app.state, "storage", None) or get_storage()
    is_connected = storage.ping()
    db_status = "connected" if is_connected else "disconnected"
    status_code = 200 if is_connected else 503
    return JSONResponse(
        {
            "status": "ok" if is_connected else "error",
            "version": "1.0.0",
            "database": db_status,
        },
        status_code=status_code,
    )


async def auth_verify_endpoint(request: Request) -> JSONResponse:
    """Verifies GitHub PAT organization membership."""
    token = extract_token(request)
    if not token:
        try:
            body = await request.json()
            if isinstance(body, dict):
                token = body.get("token")
        except Exception:
            pass

    auth_res = verify_github_token(token)
    if not auth_res.authenticated:
        return JSONResponse(
            {
                "status": "error",
                "authenticated": False,
                "error": auth_res.error or "Authentication failed",
            },
            status_code=auth_res.status_code,
        )

    return JSONResponse({
        "status": "ok",
        "authenticated": True,
        "username": auth_res.username,
        "org": auth_res.org,
    })


async def sync_push_endpoint(request: Request) -> JSONResponse:
    """Bearer-authenticated batch ingestion endpoint."""
    token = extract_token(request)
    auth_res = verify_github_token(token)
    if not auth_res.authenticated:
        return JSONResponse(
            {
                "status": "error",
                "error": auth_res.error or "Unauthorized",
            },
            status_code=auth_res.status_code,
        )

    try:
        payload = await request.json()
    except Exception as exc:
        return JSONResponse(
            {"status": "error", "error": f"Invalid JSON payload: {exc}"},
            status_code=400,
        )

    sessions = payload.get("sessions", [])
    steps = payload.get("steps", [])
    tool_calls = payload.get("tool_calls", [])
    user_interventions = payload.get("user_interventions", [])

    storage: Storage = getattr(request.app.state, "storage", None) or get_storage()
    res = storage.upsert_batch(
        sessions=sessions,
        steps=steps,
        tool_calls=tool_calls,
        user_interventions=user_interventions,
        requesting_user=auth_res.username or "anonymous",
    )

    return JSONResponse({
        "status": "success",
        "accepted_sessions": len(sessions),
        "accepted_steps": len(steps),
        "accepted_tool_calls": len(tool_calls),
        "accepted_user_interventions": len(user_interventions),
        "details": res,
    })


async def sync_pull_endpoint(request: Request) -> JSONResponse:
    """Bearer-authenticated delta replication pull endpoint with anti-echo filtering."""
    token = extract_token(request)
    auth_res = verify_github_token(token)
    if not auth_res.authenticated:
        return JSONResponse(
            {
                "status": "error",
                "error": auth_res.error or "Unauthorized",
            },
            status_code=auth_res.status_code,
        )

    since = request.query_params.get("since", "1970-01-01T00:00:00Z")
    limit_str = request.query_params.get("limit", "100")
    offset_str = request.query_params.get("offset", "0")
    all_devs_raw = request.query_params.get("all_developers") or request.query_params.get("include_self") or ""
    all_developers = all_devs_raw.lower() in ("true", "1", "yes")
    developer = request.query_params.get("developer")

    try:
        limit = min(max(int(limit_str), 1), 1000)
    except ValueError:
        limit = 100

    try:
        offset = max(int(offset_str), 0)
    except ValueError:
        offset = 0

    storage: Storage = getattr(request.app.state, "storage", None) or get_storage()
    data = storage.query_delta(
        since=since,
        requesting_user=auth_res.username,
        limit=limit,
        all_developers=all_developers,
        developer=developer,
        offset=offset,
    )

    return JSONResponse({
        "status": "success",
        "since": since,
        "limit": limit,
        "offset": offset,
        "total_matching": data.get("total_matching", len(data["sessions"])),
        "has_more": data.get("has_more", False),
        "sessions": data["sessions"],
        "steps": data["steps"],
        "tool_calls": data["tool_calls"],
        "user_interventions": data["user_interventions"],
    })


def create_app(database_url: Optional[str] = None) -> Starlette:
    """Factory creating configured Starlette application instance."""
    routes = [
        Route("/api/v1/health", health_endpoint, methods=["GET"]),
        Route("/api/v1/auth/verify", auth_verify_endpoint, methods=["POST"]),
        # Primary sync endpoints
        Route("/api/v1/sync/push", sync_push_endpoint, methods=["POST"]),
        Route("/api/v1/sync/pull", sync_pull_endpoint, methods=["GET"]),
        # Backward compatibility aliases
        Route("/api/v1/telemetry/batch", sync_push_endpoint, methods=["POST"]),
        Route("/api/v1/telemetry/delta", sync_pull_endpoint, methods=["GET"]),
    ]

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]

    application = Starlette(routes=routes, middleware=middleware)
    application.state.storage = get_storage(database_url)
    return application


app = create_app()
