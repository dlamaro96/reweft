export type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info';

export interface SourceSystem {
  id: string;
  name: string;
  type: string;
  status: 'Ready' | 'Partial' | 'Needs attention';
  validation: 'Synthetic fixture' | 'Contract tested' | 'Not live verified';
  scope: string;
  resourceGroup: string;
  facts: [string, string][];
}

export interface Finding {
  id: string;
  severity: 'Critical' | 'High' | 'Medium' | 'Low';
  title: string;
  summary: string;
  area: string;
  state: 'Fact' | 'Interpretation' | 'Assumption';
  evidence: string;
  locator: string;
  assignee?: string;
}

export interface Asset {
  id: string;
  name: string;
  type: string;
  system: string;
  domain: string;
  usage: string;
  status: 'Observed' | 'Inferred' | 'Incomplete';
  description: string;
}

export interface Report {
  id: string;
  name: string;
  platform: string;
  disposition: 'Retain' | 'Rebuild' | 'Consolidate' | 'Review';
  metric: string;
  formula: string;
  usage: string;
  distinction: string;
}

export interface DemoSnapshot {
  mode: 'synthetic-demo';
  generatedAt: string;
  workspace: { name: string; project: string; objective: string };
  inventory: { label: string; value: number; qualifier: string; href: string }[];
  sources: SourceSystem[];
  findings: Finding[];
  assets: Asset[];
  reports: Report[];
  run: {
    id: string;
    state: 'Running' | 'Paused' | 'Complete';
    started: string;
    progress: number;
    current: string;
    tasks: { label: string; status: 'Complete' | 'Active' | 'Deferred'; detail: string }[];
  };
}
