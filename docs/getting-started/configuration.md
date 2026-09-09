# Configuration

Use `examples/configurations/demo.yaml` for the isolated synthetic path or copy `.env.example` and configure a real provider/source through the UI or validated import. `${NAME}` substitutions are resolved only from the deployment allowlist; they are not shell expressions and cannot execute commands.

Precedence is strict: deployment boundaries cannot be relaxed; permitted environment/secret-file values apply next; workspace defaults remain within those boundaries; run settings may narrow but not widen. A run records its resolved revision without secret values.

Secrets use `secret://` references and are stored separately. Configuration exports contain references or redacted fields. Unknown keys and invalid combinations are rejected. TLS verification remains enabled; custom trust roots are deployment-controlled.

The conservative default policy is illustrative, not a guarantee of zero source impact. A request deadline is not proof of source-side cancellation.

