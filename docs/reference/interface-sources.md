# Interface source register

This register records documentation to verify during implementation. A link does not prove implementation, compatibility, or a test result. Connector/target manifests record the actual validation boundary.

| Interface | Primary documentation | Verification status |
|---|---|---|
| OpenAI Responses create | https://developers.openai.com/api/reference/cli/resources/responses/methods/create | Documentation reviewed 2026-09-09; structured output uses `text.format`, tool execution remains application-owned, and usage/incomplete states must be surfaced. No provider integration test run. |
| FastAPI release notes | https://fastapi.tiangolo.com/release-notes/ | Documentation reviewed 2026-09-09; 0.141.1 listed for 2026-07-29. Repository compatibility remains test-dependent. |
| Temporal workflow determinism and self-hosting | https://docs.temporal.io/ | Not yet recorded against an implemented version |
| PostgreSQL client timeouts | https://www.postgresql.org/docs/current/runtime-config-client.html | Not yet recorded against an implemented version |
| SAP Java Connector licensing/download | https://support.sap.com/en/product/connectors/jco.html | Live SDK unavailable; no binary bundled |
| SAP BW interfaces | https://help.sap.com/ | Live system/version unavailable |
| Power BI metadata scanning | https://learn.microsoft.com/en-us/fabric/admin/metadata-scanning-setup | Tenant unavailable |
| Tableau Metadata API | https://help.tableau.com/current/api/metadata_api/en-us/index.html | Server unavailable |
| OpenLineage specification | https://openlineage.io/docs/ | Version to pin with implementation |
| OpenMetadata connectors | https://docs.open-metadata.org/latest/connectors | Server not required; ingestion scope unverified |
| GitHub Actions secure use | https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions | Workflow review pending CI execution |

Update each row with date, relevant version, implementation path, and evidence when verified. Do not copy proprietary documentation into fixtures.

