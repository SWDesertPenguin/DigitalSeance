"""Cross-spec integration test tier.

Tests in this package cover boundaries BETWEEN specs (e.g., turn-loop +
security-pipeline + context-assembly together) rather than any single
spec's unit-level behaviour. They run in a separate CI tier via
``pytest -m integration`` (see `.github/workflows/test.yml`).

See ``docs/cross-spec-integration.md`` for the boundary catalogue,
fixture-sharing conventions, and runtime-budget expectations.
"""
