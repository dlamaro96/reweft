export type RuntimeMode = 'bootstrap' | 'live' | 'demo';

export interface RuntimeDescriptor {
  mode: RuntimeMode;
  bootstrapped: boolean;
  apiVersion?: string;
  demoAvailable: boolean;
  persistence?: string;
}

export interface LiveSession {
  token: string;
  workspaceId: string;
  userId?: string;
}

export interface WorkspaceRecord {
  id: string;
  name: string;
  created_at?: string;
}

export interface ProjectRecord {
  id: string;
  workspace_id: string;
  name: string;
  created_at?: string;
}

export interface InferenceProfileRecord {
  id: string;
  workspace_id: string;
  name: string;
  provider: string;
  endpoint_class: string;
  model: string;
  base_url?: string | null;
  credential_ref?: string | null;
  capabilities?: { test_status?: string; structured_output?: boolean; tool_calling?: boolean };
  revision: number;
  last_successful_test?: string | null;
}

export type LiveRunState = 'queued' | 'collecting' | 'analyzing' | 'designing' | 'verifying' | 'paused-by-user' | 'paused-by-source-policy' | 'paused-by-budget' | 'completed' | 'completed-with-gaps' | 'failed' | 'cancelled';

export interface AssessmentRecord {
  id: string;
  workspace_id: string;
  project_id: string;
  objective: string;
  scope: Record<string, unknown>;
  inference_profile_id?: string | null;
  state: LiveRunState;
  version: number;
  policy_revision?: number;
  configuration_revision?: number;
  gaps?: string[];
  created_at: string;
  updated_at: string;
}

export interface EvidenceRecord {
  id: string;
  run_id?: string | null;
  platform: string;
  environment: string;
  native_object_id: string;
  media_type: string;
  collection_status: string;
  classification: string;
  original_location: string;
  locator: { kind: string; value: string; external_label: string };
  created_at: string;
}

export interface LiveFinding {
  id: string;
  title: string;
  severity?: string;
  knowledge_state?: string;
  interpretation?: string;
  impact?: string;
  recommendation?: string;
  evidence_ids?: string[];
  assumptions?: string[];
}

export interface LiveModernization {
  status?: string;
  scenario?: string;
  assumptions?: string[];
  work_packages?: Array<{ id?: string; name: string; status?: string; description?: string }>;
  target_models?: Array<{ name: string; kind?: string; grain?: string }>;
  metrics?: Array<{ name: string; definition: string; grain?: string; additive_behavior?: string; distinct_from?: string[] }>;
  report_dispositions?: Array<{ report?: string; disposition?: string; reason?: string }>;
  mappings?: Array<{ source_asset: string; target_asset?: string | null; status: string; rationale?: string }>;
}

export interface RunStateRecord {
  run: AssessmentRecord;
  progress?: number | null;
  phase?: string;
  message?: string;
  source_operations?: Array<{ id: string; source_name?: string; operation?: string; state: string; actual_termination?: string }>;
  evidence?: EvidenceRecord[];
  findings?: LiveFinding[];
  modernization?: LiveModernization | null;
  partial?: boolean;
  gaps?: string[];
}

export interface SourceRecord {
  id: string;
  name: string;
  connector?: string;
  status?: string;
  validation?: string;
  scope?: unknown;
  test_status?: string;
  capabilities?: Record<string, unknown>;
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public details?: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}
