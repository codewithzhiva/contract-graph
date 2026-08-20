# Architecture and failure semantics

The collector is a stateless data plane. It validates bounded OTLP/HTTP JSON envelopes, extracts only routing metadata and configured field names, and forwards normalized observations. A failed control-plane call returns `503`/`502`; the collector does not claim acceptance.

The control plane is the source of truth. SQLite runs in WAL mode and batches each observation envelope in one transaction. Specifications are content-addressed. Comparison reports are computed from immutable specs and the latest aggregated runtime evidence.

## Trust boundaries

Collectors are expected to run beside trusted workloads. Production deployments must authenticate collector traffic and terminate TLS. The dashboard is read-only. Raw request bodies, response bodies, headers, and attribute values outside the allowlist are discarded.

## Scaling path

Replace the direct observation channel with JetStream/Kafka and SQLite with PostgreSQL. Partition observations by provider service. Comparison workers can then scale independently from ingestion.
