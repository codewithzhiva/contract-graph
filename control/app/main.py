from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_PATH = os.getenv("DATABASE_PATH", "contractgraph.db")
_lock = threading.Lock()


class Observation(BaseModel):
    consumer: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=128)
    route: str = Field(min_length=1, max_length=512)
    method: str = "GET"
    status_code: int = 0
    latency_ms: float = 0
    fields: list[str] = []


class ObservationBatch(BaseModel):
    observations: list[Observation] = Field(max_length=10_000)


class SpecCreate(BaseModel):
    service: str
    version: str
    document: dict[str, Any]


class ComparisonCreate(BaseModel):
    baseline_id: str
    candidate_id: str


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS observations (
          consumer TEXT NOT NULL, provider TEXT NOT NULL, route TEXT NOT NULL,
          method TEXT NOT NULL, status_code INTEGER NOT NULL, latency_ms REAL NOT NULL,
          fields_json TEXT NOT NULL, hits INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY (consumer, provider, route, method, fields_json)
        );
        CREATE TABLE IF NOT EXISTS specs (
          id TEXT PRIMARY KEY, service TEXT NOT NULL, version TEXT NOT NULL,
          document_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """)


app = FastAPI(title="ContractGraph Control Plane", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def ready() -> dict[str, str]:
    with db() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ready"}


@app.post("/v1/runtime/observations", status_code=202)
def record(batch: ObservationBatch) -> dict[str, int]:
    with _lock, db() as conn:
        for item in batch.observations:
            fields = json.dumps(sorted(set(item.fields)), separators=(",", ":"))
            conn.execute(
                """
              INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, 1)
              ON CONFLICT(consumer, provider, route, method, fields_json)
              DO UPDATE SET hits=hits+1, status_code=excluded.status_code,
                            latency_ms=(latency_ms+excluded.latency_ms)/2
            """,
                (
                    item.consumer,
                    item.provider,
                    item.route,
                    item.method.upper(),
                    item.status_code,
                    item.latency_ms,
                    fields,
                ),
            )
    return {"accepted": len(batch.observations)}


@app.get("/v1/graph")
def graph() -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM observations ORDER BY hits DESC").fetchall()
    edges = [dict(row) | {"fields": json.loads(row["fields_json"])} for row in rows]
    for edge in edges:
        edge.pop("fields_json", None)
    nodes = sorted({n for edge in edges for n in (edge["consumer"], edge["provider"])})
    return {"nodes": nodes, "edges": edges}


@app.post("/v1/specs", status_code=201)
def create_spec(spec: SpecCreate) -> dict[str, str]:
    canonical = json.dumps(spec.document, sort_keys=True, separators=(",", ":"))
    spec_id = hashlib.sha256(f"{spec.service}:{spec.version}:{canonical}".encode()).hexdigest()[:16]
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO specs VALUES (?, ?, ?, ?, ?)",
            (spec_id, spec.service, spec.version, canonical, datetime.now(UTC).isoformat()),
        )
    return {"id": spec_id, "service": spec.service, "version": spec.version}


@app.post("/v1/comparisons")
def compare(request: ComparisonCreate) -> dict[str, Any]:
    with db() as conn:
        baseline = conn.execute("SELECT * FROM specs WHERE id=?", (request.baseline_id,)).fetchone()
        candidate = conn.execute("SELECT * FROM specs WHERE id=?", (request.candidate_id,)).fetchone()
        if not baseline or not candidate:
            raise HTTPException(404, "specification not found")
        if baseline["service"] != candidate["service"]:
            raise HTTPException(409, "specifications belong to different services")
        observations = conn.execute(
            "SELECT * FROM observations WHERE provider=?", (baseline["service"],)
        ).fetchall()
    changes = breaking_changes(json.loads(baseline["document_json"]), json.loads(candidate["document_json"]))
    affected = []
    for row in observations:
        used = set(json.loads(row["fields_json"]))
        relevant = [
            change
            for change in changes
            if route_match(change["path"], row["route"])
            and (not change.get("field") or change["field"] in used)
        ]
        if relevant:
            affected.append(
                {"consumer": row["consumer"], "route": row["route"], "hits": row["hits"], "changes": relevant}
            )
    risk = "high" if affected else ("medium" if changes else "low")
    return {
        "service": baseline["service"],
        "risk": risk,
        "breaking_changes": changes,
        "affected_consumers": affected,
        "observed_hits_at_risk": sum(a["hits"] for a in affected),
    }


def breaking_changes(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    old_paths, new_paths = old.get("paths", {}), new.get("paths", {})
    for path, operations in old_paths.items():
        if path not in new_paths:
            changes.append({"kind": "endpoint_removed", "path": path})
            continue
        for method, operation in operations.items():
            if method.startswith("x-") or method == "parameters":
                continue
            if method not in new_paths[path]:
                changes.append({"kind": "operation_removed", "path": path, "method": method.upper()})
                continue
            old_props = response_properties(operation)
            new_props = response_properties(new_paths[path][method])
            for field in sorted(old_props - new_props):
                changes.append(
                    {"kind": "response_field_removed", "path": path, "method": method.upper(), "field": field}
                )
    return changes


def response_properties(operation: dict[str, Any]) -> set[str]:
    responses = operation.get("responses", {})
    response = responses.get("200") or responses.get("201") or {}
    schema = response.get("content", {}).get("application/json", {}).get("schema", {})
    return set(schema.get("properties", {}))


def route_match(spec_path: str, observed: str) -> bool:
    left, right = spec_path.strip("/").split("/"), observed.strip("/").split("/")
    return len(left) == len(right) and all(
        a == b or (a.startswith("{") and a.endswith("}"))
        for a, b in zip(left, right, strict=True)
    )
