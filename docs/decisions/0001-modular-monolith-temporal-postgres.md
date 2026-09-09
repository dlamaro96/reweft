# ADR 0001: Modular monolith with Temporal and PostgreSQL

- Status: accepted for initial implementation
- Date: 2026-09-09

## Decision

Keep domain logic in one Python package and deploy role-specific API, analysis-worker, and collector processes. Temporal owns durable orchestration. PostgreSQL stores application state, relational graph edges, journals, budgets, events, and separate Temporal persistence. Evidence blobs use protected local storage in compact deployments and an S3-compatible adapter when shared storage is required.

## Consequences

This preserves credential/source execution boundaries without introducing independent queues, graph databases, or vector databases. The compact topology is operationally approachable but not HA. Scale-out requires shared evidence storage and independently operated durable dependencies.

