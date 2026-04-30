# Performance Requirements Quality Checklist: MCP Server

**Purpose**: Validate the quality, clarity, and completeness of performance requirements in the MCP Server spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Audited**: 2026-04-29
**Feature**: [spec.md](../spec.md)

**Audit summary**: 9 items pass cleanly, 23 have findings. The MCP server has the most concrete numeric SCs (SC-001 2s connect, SC-003 1s inject, SC-004 1s lifecycle) but lacks per-tool budgets, throughput targets, and degradation-under-load contracts. The bounded SSE queue (FR-013, 256 events) is the one well-specified back-pressure mechanism.

## Latency Budgets

- [x] CHK001 Is the SC-001 "within 2 seconds" decomposed (TLS / auth / session bind / first event)?
  [GAP]. Aggregate 2s ceiling. Auth alone (token validate via `_authenticate` → DB lookup) is unspecified.

- [x] CHK002 Is the SC-003 "within 1 second" inject latency budget specified per stage (validate → enqueue → ACK response)?
  [GAP]. End-to-end ceiling only.

- [x] CHK003 Is the SC-004 "within 1 second" lifecycle-transition budget specified (DB UPDATE + cascade audit-log + broadcast notify)?
  [GAP].

- [x] CHK004 Is the per-tool latency budget specified (e.g. `get_history` may scan many messages; `export_json` reads everything)?
  [GAP]. Tools vary widely — small (`set_routing_preference`) vs. large (`export_json` reads whole session). No per-tool budgets.

- [x] CHK005 Is the SSE keepalive cadence (30s) specified as a perf knob with rationale?
  [PARTIAL]. Clarification log: "Keepalive comment sent every 30 s." Rationale (proxy idle timeouts, NAT pinhole) unspecified.

- [x] CHK006 Is the auth middleware latency budget specified?
  [GAP]. Every request hits the bearer-token validator; bcrypt or hash-compare cost varies.

## SSE Streaming

- [x] CHK007 Is the FR-013 256-event queue size paired with a measurable "wedged consumer" definition?
  [PARTIAL]. The mechanism is specified; the threshold for "this consumer is wedged and should be dropped" is implicit (queue full → drop on put_nowait). Spec doesn't surface drop-rate as a metric.

- [x] CHK008 Is the broadcast fan-out latency bounded (event-arrival to all subscribers' queues)?
  [GAP]. With many subscribers, the fan-out loop iterates O(subscribers); cost unspecified.

- [x] CHK009 Is the SSE subscription overhead per-connection specified (memory: queue + asyncio task)?
  [GAP]. With 256-event queue × 100 sessions × 5 subs/session, memory grows; no upper bound.

- [x] CHK010 Is the streaming framing cost bounded (each event JSON-serialized, written, flushed)?
  [GAP]. Cheap but unspecified.

- [x] CHK011 Is the FR-017 deferred per-participant connection cap a known perf risk paired with an alerting threshold?
  [PARTIAL]. FR-017 documents the deferral and trigger ("any deployment that observes participants opening more than SACP_MAX_SSE_PER_PARTICIPANT (TBD)"); TBD threshold means there's nothing to alert on yet.

## Throughput

- [x] CHK012 Is the per-process concurrent-connection ceiling specified?
  [GAP]. uvicorn defaults; no application bound.

- [x] CHK013 Is the per-session subscriber count bounded?
  [GAP]. Could grow unbounded; with 256-event queue × N subs the memory cost scales linearly.

- [x] CHK014 Is the request-per-second throughput target specified per endpoint?
  [GAP]. Cross-ref 009 (rate limiting) defines per-endpoint caps but those are policy not perf.

- [x] CHK015 Is concurrent tool-call dispatch bounded per participant?
  [GAP]. A misbehaving client could pipeline 100 tool calls; nothing in spec caps that.

## Cold-Start

- [x] CHK016 Is the server startup time specified (alembic migrations + FastAPI app construction + first-request cold path)?
  [GAP]. SC-005 says "starts and accepts connections" but not how fast.

- [x] CHK017 Is the first-request latency (DB connection pool warmup, auth-cache cold, SSE queue init) specified?
  [GAP].

## DB-Backed Tool Latency

- [x] CHK018 Is the `get_history` latency bounded for very long sessions?
  [GAP]. Pagination is Phase 3 (security audit closeout CHK028 accepts the gap). With 10K-message sessions, full scan is expensive.

- [x] CHK019 Is the `export_json` / `export_markdown` latency bounded?
  [GAP]. Reads whole session; no ceiling.

- [x] CHK020 Is the debug-export latency cross-referenced from 010 §SC-005 (<500ms for typical sessions)?
  [PARTIAL]. 010 owns the contract; 006 spec doesn't surface it.

## Degradation Under Load

- [x] CHK021 Is back-pressure specified between turn-loop event production and SSE consumer broadcast?
  [PARTIAL]. FR-013 "drop on full" is per-consumer back-pressure. Producer-side back-pressure (slow broadcasts holding the loop) is NOT addressed because broadcasts use `put_nowait`.

- [x] CHK022 Is the system's behavior under sustained-high-rate broadcast specified?
  [GAP]. With sprint cadence × many sessions × many subscribers, broadcast load is unspecified.

- [x] CHK023 Are SLOs specified (P50, P95, P99) for any endpoint?
  [GAP]. None.

## Cost-Performance

- [x] CHK024 Is the FR-014 generic-500 + traceback-log cost (always logs full traceback even on benign errors) specified?
  [GAP]. Error logs include scrubbed traceback (007 ScrubFilter); for high error rates, log volume + scrubbing cost matters.

- [x] CHK025 Is the FR-016 CORS regex evaluation cost per-request specified?
  [GAP]. Per-request octet-validating regex is sub-ms but unspecified.

- [x] CHK026 Is the OpenAPI schema build cost (when SACP_ENABLE_DOCS=1) bounded?
  [GAP]. Lazy or eager? Unspecified.

## Measurement & Instrumentation

- [x] CHK027 Is per-endpoint structured-logging required (request-id, latency, status)?
  [PARTIAL]. Cross-ref 006 operations CHK016 (closed as accepted residual, "basic FastAPI logging covers it"). For perf SLO measurement, FastAPI defaults are insufficient.

- [x] CHK028 Is per-tool-call latency-histogram required?
  [GAP]. No /metrics endpoint.

- [x] CHK029 Is request-id propagation required across MCP API → orchestrator → DB?
  [GAP]. Cross-ref 003 CHK034 (same shape: no cross-table correlation).

- [x] CHK030 Is a load-test harness required (so SCs are testable against future regressions)?
  [GAP]. Test suite is functional; no perf load-test fixture.

- [x] CHK031 Is the SC-001 2s budget enforced in CI?
  [GAP]. SCs are observational, not gate-checked.

## Memory Footprint

- [x] CHK032 Is the per-connection memory footprint bounded (256-event queue × event size + asyncio task overhead)?
  [GAP]. With 256 events of avg 1KB JSON × N connections, memory is bounded but unsurfaced.

## Notes

- 32 items audited. The MCP server has more concrete numeric SCs than 003/004/005 but the SCs are observational, not enforceable.
- Highest-leverage findings to convert into spec amendments:
  - CHK001 / CHK002 / CHK003 (decompose existing SCs into per-stage budgets — turns observational targets into diagnosable ones).
  - CHK023 (P50/P95/P99 SLOs — operationally critical).
  - CHK013 / CHK032 (subscriber-count cap + memory bound — defends against the FR-017 deferred connection-cap risk).
  - CHK030 / CHK031 (load-test harness + CI gate for SC-001 — turns SCs into enforceable contracts).
  - CHK029 (request-id propagation across services — pairs with 003 CHK034).
- Lower-priority but useful:
  - CHK005 (keepalive cadence rationale — relevant for proxy / NAT deployments).
  - CHK018 / CHK019 (paginate large reads — already deferred to Phase 3 but worth tracking).
- Sister checklists: `requirements.md`, `security.md`, `operations.md` already on main. Cross-refs to 003 (turn-loop produces events), 010 (debug-export timing), 011 (Web UI's WebSocket on port 8751 mirrors this analysis).

## Closeout (2026-04-29)

Spec amendments to 006 close the highest-leverage GAPs:

- **CHK001** (SC-001 2s decomposed) closed by SC-007 (P95 connect-to-first-event <= 500ms).
- **CHK002 / CHK003** (per-tool budgets for inject + lifecycle) closed by FR-018 (per-tool latency capture) + SC-006 (P95 budgets per cheap/expensive class).
- **CHK004** (per-tool latency budget) closed by FR-018 + SC-006.
- **CHK008** (broadcast fan-out cost) addressed indirectly by FR-019 (subscriber cap x per-event cost = 16MB ceiling).
- **CHK013** (per-session subscriber count bounded) closed by FR-019 (SACP_MAX_SUBSCRIBERS_PER_SESSION default 64) + SC-008 (cap enforcement test).
- **CHK020** (cross-ref to 010 SC-005 debug-export) closed by SC-006 (explicit cross-ref).
- **CHK023** (SLO percentiles) closed by SC-006 + SC-007.
- **CHK029** (request-id propagation) closed by FR-020 (UUID4 + contextvars across MCP -> orchestrator -> DB).
- **CHK032** (per-connection memory bound) closed by FR-019 (16MB/session ceiling).

Items remaining [GAP] (require infrastructure or tier-4 work):

- CHK030 / CHK031 (load-test harness + CI gate) same shape across all 7 perf checklists.
- CHK016-019 (cold-start, throughput, DB-tool latency for very long sessions) depend on production observability.
- CHK024-026 (per-error log volume, regex cost, OpenAPI build cost) fine-grained instrumentation work.

Implementation of FR-018 / FR-019 / FR-020 / SC-006 / SC-007 / SC-008 ships as a follow-up PR (subscriber cap enforcement, request-id middleware, structured logs).
