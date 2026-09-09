# Contributing to Reweft

Reweft welcomes human- and AI-assisted contributions under the same review, provenance, licensing, safety, and test standards.

## Development

Install the toolchains declared by the backend and frontend packages, or use Docker Compose. Run `make doctor`, `make contracts`, `make lint`, and `make test` before opening a pull request. Connector changes need contract fixtures covering pagination, partial permissions, malformed responses, timeouts, and cancellation/unknown-execution behavior where applicable. Target adapters need a capability record and artifact validation that accurately states its boundary.

Never commit credentials, customer metadata, proprietary SDK binaries, copied vendor fixtures, production screenshots, or private support bundles. SAP JCo binaries must be acquired separately under SAP terms and must not be redistributed here.

Substantial changes to contracts, safety policies, inference routing, or compatibility should begin with [the RFC template](docs/contributing/rfc-template.md). Update documentation and `contracts/acceptance.yaml` without overstating test status.

## Developer Certificate of Origin

Contributors certify their own commits by adding `Signed-off-by: Name <email>` to commit messages (`git commit -s`). This is a DCO sign-off, not a copyright assignment. Never forge another contributor's sign-off.

