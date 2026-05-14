# Quickstart: Enabling Prometheus Metrics

## Step 1 — Enable the metrics surface

Add to your `.env` or Dockge stack environment:

```
SACP_METRICS_ENABLED=true
```

The endpoint is disabled by default. The orchestrator will not register the route and will not collect any metrics until this var is set to `true`.

## Step 2 — (Optional) Tune the session grace window

```
SACP_METRICS_SESSION_GRACE_S=30
```

Default is 30 seconds (one standard Prometheus scrape interval). Valid range: 5 to 300. This controls how long terminated session metrics linger before eviction — long enough for a final scrape to capture terminal values.

## Step 3 — (Optional) Change the endpoint path

```
SACP_METRICS_BIND_PATH=/metrics
```

Default is `/metrics`. Must start with `/`. Changing this is rarely needed; document the new path in your Prometheus configuration if you do.

## Step 4 — Configure Prometheus

Add a scrape job to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: sacp
    static_configs:
      - targets: ["<orchestrator-host>:8750"]
    scrape_interval: 15s
    metrics_path: /metrics
```

Replace `<orchestrator-host>` with the hostname or IP of the SACP orchestrator. The default port is 8750.

## Step 5 — Verify scraping

After restarting the orchestrator and Prometheus, verify the endpoint responds:

```bash
curl http://<orchestrator-host>:8750/metrics
```

You should see Prometheus text-format output with `# HELP` and `# TYPE` headers. If you see `404 Not Found`, check that `SACP_METRICS_ENABLED=true` is set and the process restarted.

In Prometheus, query `sacp_participant_tokens_total` — if sessions are running, you should see per-session counters accumulating.

## Metric families available

See `docs/metrics.md` for the full catalog of metric families, labels, bounded enumerations, and cardinality bounds.

## Troubleshooting

- **404 on /metrics**: `SACP_METRICS_ENABLED` is not `true` or was not set before the process started. Restart the process with the var set.
- **Invalid value on startup**: `SACP_METRICS_SESSION_GRACE_S` is outside [5, 300] or `SACP_METRICS_BIND_PATH` is malformed. The process will exit with a clear error message.
- **No metrics after sessions run**: Confirm the scrape interval is short enough to catch a running session. Terminated sessions have their series evicted after the grace window.
