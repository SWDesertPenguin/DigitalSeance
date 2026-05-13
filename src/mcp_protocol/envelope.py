# SPDX-License-Identifier: AGPL-3.0-or-later
"""JSON-RPC 2.0 envelope shapes. Spec 030 Phase 2, FR-019."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class MCPRequest(BaseModel):
    """Inbound JSON-RPC 2.0 request."""

    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] | None = None
    id: str | int | None = None


class MCPNotification(BaseModel):
    """Server-initiated JSON-RPC 2.0 notification (no id field)."""

    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] | None = None


class MCPError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: dict[str, Any] | None = None


class MCPErrorEnvelope(BaseModel):
    """JSON-RPC 2.0 error response envelope."""

    jsonrpc: str = "2.0"
    error: MCPError
    id: str | int | None = None


class MCPResponse(BaseModel):
    """JSON-RPC 2.0 success response envelope."""

    jsonrpc: str = "2.0"
    result: Any
    id: str | int | None = None
