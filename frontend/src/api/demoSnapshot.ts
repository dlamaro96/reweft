import type { DemoSnapshot } from './types';

export const demoSnapshot: DemoSnapshot = {
  mode: 'synthetic-demo',
  generatedAt: '2026-09-09T08:30:00Z',
  workspace: {
    name: 'Synthetic Manufacturing',
    project: 'BW retirement assessment',
    objective: 'Assess legacy retirement readiness',
  },
  inventory: [
    { label: 'Systems observed', value: 5, qualifier: '3 fully inventoried', href: '/connections' },
    { label: 'Assets catalogued', value: 148, qualifier: '12 with incomplete scope', href: '/estate' },
    { label: 'Reports assessed', value: 24, qualifier: '7 need disposition', href: '/reports' },
    { label: 'Open findings', value: 11, qualifier: '3 high priority', href: '/findings' },
  ],
  sources: [
    { id: 'src-bw', name: 'BW/4HANA sample', type: 'SAP BW', status: 'Partial', validation: 'Synthetic fixture', scope: 'Queries, transformations, ADSOs', resourceGroup: 'erp-core', facts: [['Network', 'Reachable'], ['Authentication', 'Fixture only'], ['Metadata', '42 objects'], ['Objective coverage', 'Partial']] },
    { id: 'src-pg', name: 'Operations warehouse', type: 'PostgreSQL', status: 'Ready', validation: 'Synthetic fixture', scope: 'manufacturing, distribution', resourceGroup: 'analytics-postgres', facts: [['Network', 'Fixture only'], ['Authentication', 'Fixture only'], ['Metadata', '42 fixture objects'], ['Objective coverage', 'Complete for fixture']] },
    { id: 'src-bi', name: 'Commercial reporting', type: 'Power BI', status: 'Partial', validation: 'Not live verified', scope: 'Sales & distribution workspace', resourceGroup: 'bi-tenant', facts: [['Network', 'Not tested'], ['Authentication', 'Not configured'], ['Metadata', 'Fixture: 24 reports'], ['Objective coverage', 'Partial']] },
    { id: 'src-dbt', name: 'Transformation project', type: 'dbt artifacts', status: 'Ready', validation: 'Synthetic fixture', scope: 'manifest, catalog, run results', resourceGroup: 'artifact-import', facts: [['Network', 'Not required'], ['Authentication', 'Not required'], ['Metadata', '31 models'], ['Objective coverage', 'Complete']] },
    { id: 'src-ol', name: 'Pipeline lineage', type: 'OpenLineage', status: 'Ready', validation: 'Synthetic fixture', scope: 'manufacturing namespace', resourceGroup: 'artifact-import', facts: [['Network', 'Not required'], ['Authentication', 'Not required'], ['Metadata', '18 events'], ['Objective coverage', 'Complete']] },
  ],
  findings: [
    { id: 'F-014', severity: 'High', title: 'Monthly adjustment is absent from the candidate shared metric', summary: 'The similarly named net sales reports are not semantically equivalent. One applies a separate period-end adjustment after invoice aggregation.', area: 'Semantics', state: 'Fact', evidence: '3 artifacts', locator: 'bw://TRFN/ZSD_NET_ADJ/ABAP#L18-L31' },
    { id: 'F-021', severity: 'High', title: 'Legacy outbound dependency blocks retirement', summary: 'A scheduled distributor extract has no mapped replacement path in the proposed target scenario.', area: 'Retirement', state: 'Interpretation', evidence: '2 observations', locator: 'bw://DTP/ZDIST_MONTHLY#schedule' },
    { id: 'F-008', severity: 'High', title: 'Customer identity mapping remains uncertain', summary: 'Four percent of synthetic customer keys map to more than one canonical candidate; this is fixture-derived, not a production estimate.', area: 'Data quality', state: 'Fact', evidence: '1 test result', locator: 'test://identity/customer-crosswalk/result.json#/ambiguous' },
    { id: 'F-030', severity: 'Medium', title: 'Inventory scope excludes archived workbook delivery', summary: 'The reporting scan lacks access to one archived workspace mentioned by the distribution schedule.', area: 'Coverage', state: 'Assumption', evidence: '1 gap', locator: 'coverage://reporting/workspaces#archived' },
    { id: 'F-019', severity: 'Medium', title: 'Fiscal period close logic is duplicated', summary: 'Equivalent fiscal-period derivations appear in BW transformation logic and two semantic models.', area: 'Reuse', state: 'Interpretation', evidence: '5 code spans', locator: 'graph://field/fiscal_period/upstream' },
  ],
  assets: [
    { id: 'A-101', name: 'ZSD_NET_SALES', type: 'BW Query', system: 'BW/4HANA sample', domain: 'Commercial', usage: 'Observed 6 days ago', status: 'Observed', description: 'Invoice net amount by customer, material and fiscal period.' },
    { id: 'A-102', name: 'ZSD_NET_ADJ', type: 'Transformation', system: 'BW/4HANA sample', domain: 'Commercial', usage: 'Executed monthly', status: 'Observed', description: 'Applies period-end commercial adjustments to aggregated invoices.' },
    { id: 'A-103', name: 'fact_invoice_line', type: 'dbt model', system: 'Transformation project', domain: 'Commercial', usage: 'Built daily', status: 'Observed', description: 'Invoice line facts with conformed customer and material identifiers.' },
    { id: 'A-104', name: 'distribution_extract', type: 'Scheduled export', system: 'BW/4HANA sample', domain: 'Distribution', usage: 'Delivered monthly', status: 'Observed', description: 'Delimited outbound file for the synthetic distributor portal.' },
    { id: 'A-105', name: 'inventory_snapshot', type: 'PostgreSQL table', system: 'Operations warehouse', domain: 'Manufacturing', usage: 'Queried 2 days ago', status: 'Observed', description: 'Daily stock-position snapshot by plant, location and product.' },
    { id: 'A-106', name: 'plant_capacity_plan', type: 'Workbook', system: 'Commercial reporting', domain: 'Manufacturing', usage: 'Unknown', status: 'Incomplete', description: 'Planning workbook discovered by reference; content was outside scan scope.' },
  ],
  reports: [
    { id: 'R-12', name: 'Net sales — management', platform: 'Power BI', disposition: 'Rebuild', metric: 'Adjusted net sales', formula: 'SUM(invoice.net_amount) + SUM(monthly_adjustment.amount)', usage: '19 viewers · 30d', distinction: 'Includes signed period-end adjustment at fiscal-month grain.' },
    { id: 'R-13', name: 'Net sales — operations', platform: 'Power BI', disposition: 'Consolidate', metric: 'Invoice net amount', formula: 'SUM(invoice.net_amount)', usage: '8 viewers · 30d', distinction: 'Invoice-only value at line grain; no adjustment.' },
    { id: 'R-18', name: 'Stock position', platform: 'BW Query', disposition: 'Rebuild', metric: 'Closing stock', formula: 'LAST_VALUE(stock_qty) BY fiscal_day', usage: 'Scheduled daily', distinction: 'Non-additive snapshot; must not be summed across time.' },
    { id: 'R-22', name: 'Distributor delivery', platform: 'File export', disposition: 'Review', metric: 'Delivered quantity', formula: 'SUM(delivery.qty) WHERE goods_issue = true', usage: 'Scheduled monthly', distinction: 'Remaining external boundary with no confirmed target consumer.' },
  ],
  run: {
    id: 'RUN-042', state: 'Running', started: 'Today, 08:12', progress: 72, current: 'Tracing remaining outbound dependencies',
    tasks: [
      { label: 'Inventory & coverage', status: 'Complete', detail: '148 assets across 5 configured systems' },
      { label: 'Semantic reconstruction', status: 'Complete', detail: '27 metrics; 4 require reconciliation' },
      { label: 'Lineage investigation', status: 'Active', detail: 'Resolving distribution extract path' },
      { label: 'Operational assessment', status: 'Complete', detail: '8 schedules and 3 service windows' },
      { label: 'Modernization proposal', status: 'Deferred', detail: 'Starts after dependency tracing completes' },
    ],
  },
};
