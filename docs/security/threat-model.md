# Threat model summary

Protected assets include source credentials and capacity, tenant evidence and graph data, configuration, prompts/model payloads, exports, audit history, generated artifacts, and service state. Principal threats are cross-workspace authorization failures, source-policy bypass, SSRF/redirect abuse, prompt or tool injection, archive/XML/formula injection, untrusted code execution, secret leakage, stale permits, retry amplification, and unsafe publication.

Primary boundaries are browser/gateway, API authorization, model gateway/egress policy, workload controller, collector credential compartment, import parser, artifact-validation sandbox, evidence store, and export delivery. Model output and imported content are untrusted data. They cannot mint permits, provide arbitrary URLs or credentials, broaden asset scope, or authorize executable code.

The compact Compose deployment improves network separation but is not a hardened multi-tenant sandbox or HA system. Host administrators and database administrators remain trusted. Container isolation alone is not presented as a complete hostile-code boundary; generated code execution must use an explicitly configured stronger sandbox or remain disabled.

