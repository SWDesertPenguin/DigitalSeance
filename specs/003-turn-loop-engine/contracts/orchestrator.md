# Orchestrator Interface Contracts

**Feature**: 003-turn-loop-engine

## ConversationLoop

```
start(session_id) → None
  - Begins the serialized turn loop for a session
  - Runs until session is paused/archived/deleted or all participants exhausted
  - Each iteration: check interrupts → route → classify → assemble → dispatch → persist → log

stop(session_id) → None
  - Gracefully stops the loop after the current turn completes

execute_turn(session_id) → TurnResult
  - Runs a single turn iteration (for testing/manual control)
  - Returns TurnResult with outcome details
```

## ContextAssembler

```
assemble(session_id, participant, budget) → list[ContextMessage]
  - Builds context in priority order:
    P1: pending interjections (≤500 tokens)
    P2: active proposals (≤500 tokens)
    P3: MVC floor (system prompt + last 3 turns)
    P4: latest summary checkpoint
    P5: additional history (fill remaining budget, newest-first)
  - Truncates at turn boundaries
  - Returns formatted messages with boundary markers

estimate_tokens(text, model) → int
  - Token count estimation via LiteLLM
```

## TurnRouter

```
route(session_id, candidate, context) → RoutingDecision
  - Evaluates candidate's routing_preference against context
  - Returns: intended, actual, action, complexity, domain_match, reason

next_speaker(session_id) → Participant | None
  - Round-robin through active, non-paused, within-budget participants
  - Returns None if all participants exhausted
```

## ProviderBridge

```
dispatch(participant, messages, timeout) → ProviderResponse
  - Decrypts API key, calls LiteLLM, discards key
  - Handles streaming accumulation
  - Returns: content, input_tokens, output_tokens, cost_usd

dispatch_with_retry(participant, messages, timeout, max_retries) → ProviderResponse
  - Wraps dispatch with retry logic
  - Exponential backoff on rate limits
  - Raises after max_retries exhausted
```

## Data Types

```
TurnResult:
  session_id: str
  turn_number: int
  speaker_id: str
  action: RoutingAction
  tokens_used: int
  cost_usd: float
  skipped: bool
  skip_reason: str | None

RoutingDecision:
  intended: str           # participant_id originally selected
  actual: str             # participant_id who actually responds
  action: RoutingAction   # routing action taken
  complexity: ComplexityScore
  domain_match: bool
  reason: str

ContextMessage:
  role: str               # 'system', 'user', 'assistant'
  content: str            # message text with boundary markers
  source_turn: int | None # original turn number (for tracing)

ProviderResponse:
  content: str
  input_tokens: int
  output_tokens: int
  cost_usd: float
  model: str
  latency_ms: int
```

## Error Types

```
AllParticipantsExhaustedError — every participant is paused/over-budget
ProviderDispatchError         — LiteLLM call failed after retries
ResponseQualityError          — empty/duplicate/repetitive response
BudgetExceededError           — turn would exceed participant's budget
```
