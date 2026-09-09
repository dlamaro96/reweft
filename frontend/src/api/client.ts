import { demoSnapshot } from './demoSnapshot';
import type { DemoSnapshot } from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

export type SnapshotResult = {
  snapshot: DemoSnapshot;
  source: 'api' | 'synthetic-fallback';
  notice?: string;
};

function isDemoSnapshot(value: unknown): value is DemoSnapshot {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<DemoSnapshot>;
  return candidate.mode === 'synthetic-demo' && Array.isArray(candidate.sources) && Array.isArray(candidate.findings);
}

export async function getDemoSnapshot(signal?: AbortSignal): Promise<SnapshotResult> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/demo/snapshot`, {
      signal,
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new Error(`Demo endpoint returned ${response.status}`);
    const payload: unknown = await response.json();
    if (!isDemoSnapshot(payload)) throw new Error('Demo endpoint returned an incompatible snapshot');
    return { snapshot: payload, source: 'api' };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    return {
      snapshot: demoSnapshot,
      source: 'synthetic-fallback',
      notice: 'Using the bundled synthetic estate because the local API is unavailable.',
    };
  }
}
