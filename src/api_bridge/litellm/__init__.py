"""LiteLLM-backed provider adapter package (spec 020).

This package is the only location under `src/` permitted to import
`litellm`. The FR-005 architectural test enforces that constraint.

`LiteLLMAdapter` registers with `AdapterRegistry` under the name
`"litellm"` at module-import time per research.md §4.
"""

from __future__ import annotations

from src.api_bridge.adapter import AdapterRegistry
from src.api_bridge.litellm.adapter import LiteLLMAdapter

AdapterRegistry.register("litellm", LiteLLMAdapter)
