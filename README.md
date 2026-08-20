# ContractGraph

Runtime evidence for safer API evolution. ContractGraph combines OpenAPI change analysis with the dependencies and response fields consumers actually use.

## Why it exists

Static contract diffing can tell you that a field disappeared. It cannot tell you which running service depends on that field or how much observed traffic is exposed. ContractGraph closes that gap without retaining request values.

## Architecture

```text
OTLP/HTTP JSON --> Go collector --> privacy-safe observations --> FastAPI control plane
                                                               |--> SQLite WAL
OpenAPI v1 + v2 -----------------------------------------------|--> risk report / CI exit
                                                               |--> dashboard
```

The v0.1 reference deployment uses a direct authenticated collector-to-control-plane channel and SQLite WAL so it is runnable on a laptop. The ingestion boundary is deliberately transport-neutral for a future JetStream adapter.

## Quick start

```bash
docker compose up --build
```

- Dashboard: <http://localhost:8080>
- API documentation: <http://localhost:8000/docs>
- OTLP/HTTP JSON traces: `POST http://localhost:4318/v1/traces`

See [the demo](docs/demo.md) for a reproducible breaking-change scenario.

## Guarantees

- Request and response values are never persisted.
- Observation ingestion is idempotently aggregated by dependency and field sketch.
- Comparisons are deterministic for the same specifications and runtime evidence.
- The CI client exits with status `2` for high-risk changes.

## Limitations

- v0.1 analyses removed endpoints, operations, and top-level response fields; it is not a complete OpenAPI compatibility engine.
- OTLP/gRPC and a durable event-bus adapter are planned after the HTTP/JSON reference path is validated.
- SQLite is intended for the local demo; a horizontally scaled deployment needs PostgreSQL.

## Development

Use `make bootstrap`, `make verify`, `make demo`, and `make benchmark`. Benchmark results belong in `docs/benchmarks.md` and must include the machine profile.

## Security

See [SECURITY.md](SECURITY.md). Please do not send real production payloads to the demo deployment.

Apache-2.0 licensed.
