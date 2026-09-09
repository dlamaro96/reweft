import type {
  AssessmentRecord, EvidenceRecord, InferenceProfileRecord, LiveSession, ProjectRecord,
  RunStateRecord, RuntimeDescriptor, SourceRecord, WorkspaceRecord,
} from './liveTypes';
import { ApiError } from './liveTypes';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';
const SESSION_KEY = 'reweft.live-session.v1';

async function readError(response: Response): Promise<{ message: string; details?: unknown }> {
  try {
    const body = await response.json() as { detail?: unknown; message?: string };
    const detail = body.detail;
    if (typeof detail === 'string') return { message: detail, details: body };
    if (detail && typeof detail === 'object' && 'message' in detail) return { message: String((detail as { message: unknown }).message), details: body };
    return { message: body.message ?? `Request failed with status ${response.status}`, details: body };
  } catch {
    return { message: `Request failed with status ${response.status}` };
  }
}

async function request<T>(path: string, options: RequestInit = {}, session?: LiveSession): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (options.body) headers.set('Content-Type', 'application/json');
  if (session) headers.set('Authorization', `Bearer ${session.token}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (error) {
    throw new ApiError(0, error instanceof Error ? error.message : 'The API could not be reached');
  }
  if (!response.ok) {
    const failure = await readError(response);
    throw new ApiError(response.status, failure.message, failure.details);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function getRuntime(signal?: AbortSignal): Promise<RuntimeDescriptor> {
  const raw = await request<Record<string, unknown>>('/api/v1/runtime', { signal });
  const rawMode = String(raw.mode ?? '');
  const bootstrapRequired = raw.bootstrap_required === true || raw.requires_bootstrap === true;
  const bootstrapped = typeof raw.bootstrapped === 'boolean' ? raw.bootstrapped : !bootstrapRequired;
  const mode = rawMode === 'synthetic-demo' || rawMode === 'demo'
    ? 'demo'
    : rawMode === 'bootstrap' || rawMode === 'setup' || bootstrapRequired || !bootstrapped
      ? 'bootstrap'
      : 'live';
  return {
    mode,
    bootstrapped,
    apiVersion: typeof raw.apiVersion === 'string' ? raw.apiVersion : typeof raw.api_version === 'string' ? raw.api_version : undefined,
    demoAvailable: raw.demoAvailable !== false && raw.demo_available !== false,
    persistence: typeof raw.persistence === 'string' ? raw.persistence : undefined,
  };
}

export function loadSession(): LiveSession | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<LiveSession>;
    if (!value.token || !value.workspaceId) return null;
    return { token: value.token, workspaceId: value.workspaceId, userId: value.userId };
  } catch { return null; }
}

export function saveSession(session: LiveSession): void { sessionStorage.setItem(SESSION_KEY, JSON.stringify(session)); }
export function clearSession(): void { sessionStorage.removeItem(SESSION_KEY); }

export async function bootstrapWorkspace(input: { token: string; email: string; display_name: string; workspace_name: string }): Promise<LiveSession> {
  const result = await request<{ api_token: string; workspace_id: string; user_id: string }>('/api/v1/auth/bootstrap', { method: 'POST', body: JSON.stringify(input) });
  const session = { token: result.api_token, workspaceId: result.workspace_id, userId: result.user_id };
  saveSession(session);
  return session;
}

const workspacePath = (session: LiveSession, suffix = '') => `/api/v1/workspaces/${encodeURIComponent(session.workspaceId)}${suffix}`;

export const liveApi = {
  workspace: (session: LiveSession) => request<WorkspaceRecord>(workspacePath(session), {}, session),
  projects: (session: LiveSession) => request<ProjectRecord[]>(workspacePath(session, '/projects'), {}, session),
  sources: (session: LiveSession) => request<SourceRecord[]>(workspacePath(session, '/sources'), {}, session),
  createProject: (session: LiveSession, name: string) => request<ProjectRecord>(workspacePath(session, '/projects'), { method: 'POST', body: JSON.stringify({ name }) }, session),
  profiles: (session: LiveSession) => request<InferenceProfileRecord[]>(workspacePath(session, '/inference-profiles'), {}, session),
  createProfile: (session: LiveSession, body: Record<string, unknown>) => request<InferenceProfileRecord>(workspacePath(session, '/inference-profiles'), { method: 'POST', body: JSON.stringify(body) }, session),
  testProfile: (session: LiveSession, profileId: string) => request<InferenceProfileRecord | { status: string; capabilities?: Record<string, unknown> }>(workspacePath(session, `/inference-profiles/${encodeURIComponent(profileId)}/test`), { method: 'POST' }, session),
  assessments: (session: LiveSession) => request<AssessmentRecord[]>(workspacePath(session, '/assessments'), {}, session),
  createAssessment: (session: LiveSession, body: Record<string, unknown>) => request<AssessmentRecord>(workspacePath(session, '/assessments'), { method: 'POST', body: JSON.stringify(body) }, session),
  transition: (session: LiveSession, runId: string, action: string, expectedVersion: number) => request<AssessmentRecord>(workspacePath(session, `/assessments/${encodeURIComponent(runId)}/transitions`), { method: 'POST', body: JSON.stringify({ action, expected_version: expectedVersion }) }, session),
  runState: (session: LiveSession, runId: string, signal?: AbortSignal) => request<RunStateRecord>(workspacePath(session, `/runs/${encodeURIComponent(runId)}/state`), { signal }, session),
  evidence: (session: LiveSession, runId?: string) => request<EvidenceRecord[]>(workspacePath(session, `/evidence${runId ? `?run_id=${encodeURIComponent(runId)}` : ''}`), {}, session),
  createPostgresSource: (session: LiveSession, body: Record<string, unknown>) => request<SourceRecord>(workspacePath(session, '/sources/postgresql'), { method: 'POST', body: JSON.stringify(body) }, session),
  testSource: (session: LiveSession, sourceId: string) => request<SourceRecord | { status: string; capabilities?: Record<string, unknown> }>(workspacePath(session, `/sources/${encodeURIComponent(sourceId)}/test`), { method: 'POST' }, session),
  exportRun: async (session: LiveSession, runId: string): Promise<Blob> => {
    const response = await fetch(`${API_BASE}${workspacePath(session, `/runs/${encodeURIComponent(runId)}/export`)}`, { headers: { Authorization: `Bearer ${session.token}`, Accept: 'application/zip, application/json' } });
    if (!response.ok) { const failure = await readError(response); throw new ApiError(response.status, failure.message, failure.details); }
    return response.blob();
  },
};
