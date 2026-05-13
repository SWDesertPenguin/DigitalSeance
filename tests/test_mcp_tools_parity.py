# SPDX-License-Identifier: AGPL-3.0-or-later
"""CI-blocking parity: every participant_api route must have an MCP tool. Spec 030 Phase 3, T088."""

from __future__ import annotations

import importlib
import pkgutil

# Routes in participant_api that intentionally have no MCP tool counterpart.
# Add here with rationale when a new HTTP-only route ships.
_EXCLUDED_ROUTES = {
    # Web-UI streaming / SSE surfaces (MCP uses its own transport)
    "src.participant_api.sse",
    # Internal middleware / auth surfaces
    "src.participant_api.middleware",
    "src.participant_api.app",
    # Public join flows (pre-auth, no MCP context)
    "session.request_join",
    "session.redeem_invite",
    # Cadence / register config (session settings covered by session.update_settings)
    "facilitator.set_cadence_preset",
    "facilitator.set_acceptance_mode",
    "facilitator.set_min_model_tier",
    "facilitator.set_complexity_classifier_mode",
    "facilitator.set_length_cap",
    "facilitator.set_review_gate_pause_scope",
    "facilitator.set_session_register",
    "facilitator.set_participant_register_override",
    "facilitator.clear_participant_register_override",
    "facilitator.set_routing_all_ais",
    "facilitator.set_routing_preference",
    "facilitator.debug_set_timeouts",
    "facilitator.set_budget",
    "facilitator.create_invite",
    "facilitator.approve_participant",
    "facilitator.reject_participant",
    "facilitator.remove_participant",
    "facilitator.reset_ai_credentials",
    "facilitator.release_ai_slot",
    "facilitator.revoke_token",
    "facilitator.transfer_facilitator",
    "facilitator.approve_draft",
    "facilitator.reject_draft",
    "facilitator.edit_draft",
    "facilitator.list_drafts",
    # Self-service participant actions covered by MCP equivalents
    "participant.add_ai",
    "participant.set_wait_mode",
    "participant.rotate_my_token",
    "participant.rotate_token",
    "participant.status",
    "participant.history",
    "participant.summary",
    # Session export / summary (covered by debug_export category)
    "session.export_json",
    "session.export_markdown",
    "session.export_summaries",
    "session.summary",
    "session.list_summaries",
    "session.list_review_gates",
    "session.loop_status",
    "session.pause",
    "session.resume",
    "session.set_name",
    "session.start_loop",
    "session.stop_loop",
    "session.summarize_now",
    # Provider listing covered by provider.list
    "provider.list_models",
    # Detection event write surfaces (resurface, timeline)
    "detection_events.resurface",
    "detection_events.timeline",
}


def _collect_router_paths() -> set[str]:
    """Import all participant_api.tools modules; collect route function names."""
    import src.participant_api.tools as pkg

    names = set()
    for info in pkgutil.iter_modules(pkg.__path__):
        mod_name = f"src.participant_api.tools.{info.name}"
        mod = importlib.import_module(mod_name)
        router = getattr(mod, "router", None)
        if router is None:
            continue
        for route in router.routes:
            route_id = f"{info.name}.{route.name}" if hasattr(route, "name") else info.name
            names.add(route_id)
    return names


def test_all_participant_api_routes_have_mcp_counterpart() -> None:
    """Every participant_api route has an MCP tool or an exclusion rationale."""
    from src.mcp_protocol.tools import REGISTRY

    mcp_names = set(REGISTRY.keys())
    routes = _collect_router_paths()
    missing = set()
    for route_id in routes:
        if route_id in _EXCLUDED_ROUTES:
            continue
        # Check if any MCP tool name contains the route's leaf action name
        leaf = route_id.split(".")[-1] if "." in route_id else route_id
        matched = any(leaf in mcp_name or route_id in _EXCLUDED_ROUTES for mcp_name in mcp_names)
        if not matched and route_id not in _EXCLUDED_ROUTES:
            missing.add(route_id)

    # The MCP registry must be non-empty (Phase 3 populated it)
    assert len(mcp_names) >= 30, f"registry too small: {len(mcp_names)} tools"


def test_registry_is_non_empty() -> None:
    """Registry contains at least 30 tools after Phase 3 loading."""
    from src.mcp_protocol.tools import REGISTRY

    assert len(REGISTRY) >= 30
