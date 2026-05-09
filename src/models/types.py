# SPDX-License-Identifier: AGPL-3.0-or-later

"""Enum types for all SACP domain values."""

from __future__ import annotations

from enum import StrEnum


class SessionStatus(StrEnum):
    """Session lifecycle states."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    DELETED = "deleted"


class ParticipantStatus(StrEnum):
    """Participant connection states."""

    ACTIVE = "active"
    PAUSED = "paused"
    OFFLINE = "offline"
    ERROR = "error"


class ParticipantRole(StrEnum):
    """Participant permission levels."""

    FACILITATOR = "facilitator"
    PARTICIPANT = "participant"
    PENDING = "pending"


class BranchStatus(StrEnum):
    """Conversation branch states."""

    ACTIVE = "active"
    ABANDONED = "abandoned"


class SpeakerType(StrEnum):
    """Message author classification."""

    AI = "ai"
    HUMAN = "human"
    SYSTEM = "system"
    SUMMARY = "summary"


class RoutingPreference(StrEnum):
    """Eight participant routing modes."""

    ALWAYS = "always"
    REVIEW_GATE = "review_gate"
    DELEGATE_LOW = "delegate_low"
    DOMAIN_GATED = "domain_gated"
    BURST = "burst"
    OBSERVER = "observer"
    ADDRESSED_ONLY = "addressed_only"
    HUMAN_ONLY = "human_only"


class RoutingAction(StrEnum):
    """Routing log action outcomes."""

    NORMAL = "normal"
    REVIEW_GATED = "review_gated"
    DELEGATED = "delegated"
    SKIPPED = "skipped"
    BURST_ACCUMULATING = "burst_accumulating"
    BURST_FIRED = "burst_fired"
    OBSERVER_READ = "observer_read"
    OBSERVER_INJECT = "observer_inject"
    ADDRESSED_ACTIVATION = "addressed_activation"
    HUMAN_TRIGGER = "human_trigger"
    TIMEOUT = "timeout"


class ComplexityScore(StrEnum):
    """Turn complexity classification."""

    LOW = "low"
    HIGH = "high"


class ModelTier(StrEnum):
    """Model capability tiers."""

    LOW = "low"
    MID = "mid"
    HIGH = "high"


class PromptTier(StrEnum):
    """System prompt verbosity tiers."""

    LOW = "low"
    MID = "mid"
    HIGH = "high"
    MAX = "max"


class ModelFamily(StrEnum):
    """Supported model families."""

    CLAUDE = "claude"
    GPT = "gpt"
    LLAMA = "llama"
    MISTRAL = "mistral"
    QWEN = "qwen"


class Provider(StrEnum):
    """LLM provider identifiers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    CUSTOM = "custom"


class CadencePreset(StrEnum):
    """Conversation pacing presets."""

    SPRINT = "sprint"
    CRUISE = "cruise"
    IDLE = "idle"


class AcceptanceMode(StrEnum):
    """Proposal acceptance strategies."""

    UNANIMOUS = "unanimous"
    MAJORITY = "majority"
    FACILITATOR = "facilitator"


class ComplexityClassifierMode(StrEnum):
    """Complexity detection method."""

    PATTERN = "pattern"
    EMBEDDING = "embedding"
    MODEL_CALL = "model_call"


class ReviewGateStatus(StrEnum):
    """Review gate draft resolution states."""

    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


class InterruptStatus(StrEnum):
    """Interrupt queue delivery states."""

    PENDING = "pending"
    DELIVERED = "delivered"


class ProposalStatus(StrEnum):
    """Proposal lifecycle states."""

    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class VoteChoice(StrEnum):
    """Vote options on proposals."""

    ACCEPT = "accept"
    REJECT = "reject"
    MODIFY = "modify"
