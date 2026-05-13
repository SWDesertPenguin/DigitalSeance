# SPDX-License-Identifier: AGPL-3.0-or-later
"""ToolDefinition, RegistryEntry types. Spec 030 Phase 3, tool-registry-shape.md."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ToolDefinition:
    """Static metadata for a single MCP tool."""

    name: str
    description: str
    paramsSchema: dict  # noqa: N815
    returnSchema: dict  # noqa: N815
    errorContract: tuple[str, ...]  # noqa: N815
    scopeRequirement: str  # noqa: N815
    aiAccessible: bool  # noqa: N815
    idempotencySupported: bool  # noqa: N815
    paginationSupported: bool  # noqa: N815
    v14BudgetMs: int  # noqa: N815
    versionSuffix: str | None = None  # noqa: N815
    deprecatedAt: datetime | None = None  # noqa: N815
    category: str = ""


@dataclass
class RegistryEntry:
    """Live registry slot pairing a definition with its dispatch callable."""

    definition: ToolDefinition
    dispatch: Callable[..., Any]
