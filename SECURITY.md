# Security policy

## Reporting

Do not open a public issue for a suspected vulnerability. Use GitHub's private vulnerability reporting for the repository once it is enabled. If that facility is unavailable, privately contact a maintainer through their verified GitHub profile. No response-time SLA is promised for this community project.

Include affected revision, impact, reproducible steps, and suggested mitigation while excluding real credentials and customer data. Maintainers will acknowledge when practical, investigate, coordinate a fix and disclosure, and credit reporters who want attribution.

## Supported versions

Reweft is pre-release and currently has no supported production release line. Security fixes land on the active development branch until a release policy is established. A passing scanner is not proof that the software is vulnerability-free.

## Scope

The trust boundaries include workspace isolation, collector credential separation, model-data egress, source workload admission, imports/renderers, generated-artifact validation, authentication, and exports. Reports about third-party infrastructure or social engineering outside this repository may be out of scope.

