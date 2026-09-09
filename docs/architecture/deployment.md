# Deployment profiles and boundaries

The default Compose profile is a compact, single-node development/demonstration topology for only the synthetic gateway/API path. The API uses SQLite development persistence on a named volume, and only the gateway is published to the host. PostgreSQL is opt-in under `durable` but not connected to the application. The `workers` profile describes the intended PostgreSQL, Temporal, analysis-worker, and collector placement but is not runnable until those process modules and integration exist.

A production deployment must supply versioned images, backups for both application and Temporal state, shared evidence storage, database/Temporal availability, TLS ingress, secret management, resource limits, monitoring, and tested restore/upgrade procedures. No HA configuration has been validated yet.

Collectors may be placed near sources, but they authenticate permits from the central workload controller, receive only scoped secret material, and cannot expand authorization. Neither the API nor workers mount a Docker socket.
