# Contract: register-preset interface

The five-preset register registry is a frozen 1-5 mapping that emits a Tier 4 delta into the spec 008 prompt assembler. Lives in `src/prompts/register_presets.py`.

## Registry shape

```python
@dataclass(frozen=True)
class RegisterPreset:
    slider: int                 # 1..5
    name: str                   # canonical preset name (snake_case)
    tier4_delta: str | None     # delta text, or None for slider=3 (Balanced)


REGISTER_PRESETS: tuple[RegisterPreset, ...] = (
    RegisterPreset(1, "direct",         "Reply briefly and directly. ..."),
    RegisterPreset(2, "conversational", "Reply in a conversational register. ..."),
    RegisterPreset(3, "balanced",       None),  # no delta — tier text alone (FR-007 / FR-013)
    RegisterPreset(4, "technical",      "Use precise technical register. ..."),
    RegisterPreset(5, "academic",       "Use formal academic register. ..."),
)
```

Full delta text for each preset per spec FR-013 (canonical wording — see [data-model.md](../data-model.md#registerpreset)).

## Lookup helpers

```python
def preset_for_slider(slider: int) -> RegisterPreset:
    """Look up by slider value; raises ValueError if not in [1, 5]."""

def preset_for_name(name: str) -> RegisterPreset:
    """Look up by canonical name; raises KeyError if unknown."""
```

Both helpers are O(1) (the registry is a 5-element tuple; lookup-by-slider is `REGISTER_PRESETS[slider - 1]`). V14 budget 2 (slider lookup P95 < 1ms) is satisfied by construction.

## Resolver — override → session → default

```python
async def resolve_register(
    *,
    participant_id: str,
    session_id: str,
    register_default: int,         # SACP_REGISTER_DEFAULT
    db: Connection,
) -> tuple[int, RegisterPreset, Literal["session", "participant_override"]]:
    """Resolve the participant's effective register via the SQL JOIN
    documented in research.md §5.

    Returns (slider_value, preset, source).
    """
```

Per [research.md §5](../research.md): single SQL query with two LEFT JOINs and a COALESCE; the source attribution is `'participant_override'` iff the override row exists, else `'session'` (which encompasses both "session_register row exists" and "row absent, env default applies").

## Prompt-assembly integration

The resolver's preset feeds the spec 008 Tier 4 hook (per FR-007 / FR-013):

```python
async def assemble_prompt_for_turn(
    *,
    participant_id: str,
    session_id: str,
    prompt_tier: str,
    custom_prompt: str,
    shaping_retry_delta_text: str | None = None,   # set when a shaping retry is firing
    db: Connection,
) -> str:
    slider, preset, source = await resolve_register(
        participant_id=participant_id,
        session_id=session_id,
        register_default=SETTINGS.register_default,
        db=db,
    )
    return assemble_prompt(
        prompt_tier=prompt_tier,
        custom_prompt=custom_prompt,
        participant_id=participant_id,
        register_delta_text=preset.tier4_delta,            # may be None for slider=3
        shaping_retry_delta_text=shaping_retry_delta_text, # may be None on first attempt
    )
```

`assemble_prompt` (existing in `src/prompts/tiers.py`) gains two optional parameters. When non-None, each is appended after the existing tier text and after the participant's custom prompt. Order:

```text
TIER_LOW
TIER_MID_DELTA      (if tier >= 'mid')
TIER_HIGH_DELTA     (if tier >= 'high')
TIER_MAX_DELTA      (if tier == 'max')
custom_prompt       (if set, sanitized)
register_delta_text (if not None — i.e., slider != 3)
shaping_retry_delta (if not None — i.e., a retry is firing)
```

Canary embedding still wraps the assembled output (existing spec 008 behavior). The two new deltas sit closest to the user turn so they dominate model attention — this is by design for the shaping retry (the model needs the tightening directive at the most-recent position) and acceptable for the register delta.

## Independence from the master switch

The register slider is independent of `SACP_RESPONSE_SHAPING_ENABLED` per spec edge case ("Slider preset 3 (Balanced) selected with `SACP_RESPONSE_SHAPING_ENABLED=false`. Both controls are independent; the master switch gates only the filler scorer + retry. Slider deltas always emit regardless of the master switch — the slider is a prompt composition concern, not a shaping concern.").

The resolver runs unconditionally on every prompt assembly. The master switch only gates the filler-scorer + retry pipeline.

## `/me` payload extension

The resolver's three return values feed the `/me` endpoint per FR-010:

```python
{
    "register_slider": slider,           # int 1..5
    "register_preset": preset.name,      # "direct" | "conversational" | "balanced" | "technical" | "academic"
    "register_source": source,           # "session" | "participant_override"
}
```

Per [research.md §6](../research.md): three additive top-level fields, snake_case, two-value source enum.

## Lifecycle and cascade

- INSERT/UPDATE on `session_register` emits one `session_register_changed` audit event per [audit-events.md](./audit-events.md).
- INSERT/UPDATE on `participant_register_override` emits one `participant_register_override_set` audit event.
- Explicit DELETE on `participant_register_override` (facilitator clears) emits one `participant_register_override_cleared` audit event.
- Cascade DELETE (participant or session removed) does NOT emit a register-cleared audit event — the parent delete event is sufficient per [research.md §8](../research.md).

## V12 topology gate

In topology 7 (MCP-to-MCP), the orchestrator-side prompt assembler does not exist. The register-preset emitter is skipped at session-start per the V12 topology gate (per [research.md §10](../research.md)). The registry tuple itself remains importable — only the resolver call is gated.
