# Connector and target capability matrix

This is a readable index of the machine records under `contracts/`. `design` and `not run` mean there is no selectable release integration. Fixture results, when added, will not imply live certification.

## Connector release records

| Connector | Intended scope | Current visibility | Current validation |
|---|---|---|---|
| PostgreSQL | Native connection test, catalog metadata, bounded profiling | Hidden / design | Fixture not run; live not run |
| SAP BW definition import | Supported exported definitions and unresolved routines | Hidden / design | Fixture not run; live unavailable |
| SAP BW live collector | Read-only supported metadata through separately obtained runtime | Hidden / design | Fixture not run; live unavailable |
| Artifact bundle | Static pipeline/report artifacts without executing code or formulas | Hidden / design | Fixture not run; live not run |
| OpenLineage | Scoped event/lineage import with explicit namespace mapping | Hidden / design | Fixture not run; live not run |

Power BI, Tableau, Qlik, SAP Analytics Cloud, BEx/AFO, dbt, ADF/Synapse, SSIS, BODS, Informatica, Airflow, OpenMetadata, Git/folder/object-storage, and tabular/document artifacts remain product-spec coverage candidates until a manifest has real implementation and test evidence. They must not be shown as usable merely because the family is named here.

## Target records

| Target | Adapter status | Environment validation | Principal gap |
|---|---|---|---|
| Open local DuckDB | Design | Not run | No fixture execution or scale/operability validation |
| Databricks | Design | Not run | No workspace/runtime tested |
| Microsoft Fabric | Design | Not run | No tenant/capacity/API tested |
| Snowflake | Design | Not run | No account/edition/warehouse tested |
| BigQuery | Design | Not run | No project/region/API tested |

