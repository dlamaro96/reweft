import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../src/app/RuntimeApp';

describe('Reweft application shell', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/overview');
    sessionStorage.clear();
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/runtime')) return Promise.resolve(jsonResponse({ mode: 'demo', bootstrapped: true, demoAvailable: true }));
      return Promise.reject(new TypeError('API unavailable'));
    }));
  });

  afterEach(() => {
    cleanup();
    sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it('labels the fallback as synthetic and renders evidence-backed overview content', async () => {
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Estate overview' })).toBeInTheDocument();
    expect(await screen.findByText(/Using the bundled synthetic estate because the local API is unavailable/)).toBeInTheDocument();
    expect(screen.getByText('Monthly adjustment is absent from the candidate shared metric')).toBeInTheDocument();
    expect(screen.getByText('Demo · synthetic')).toBeInTheDocument();
  });

  it('navigates between primary screens without a reload', async () => {
    render(<App />);
    await screen.findByText('Systems observed');
    await userEvent.click(screen.getByRole('button', { name: 'Connections' }));
    expect(screen.getByRole('heading', { name: 'Connections' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/connections');
    expect(screen.getByText('Four distinct capability states')).toBeInTheDocument();
  });

  it('offers a keyboard command palette and filters assets', async () => {
    render(<App />);
    await screen.findByText('Systems observed');
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    const search = screen.getByPlaceholderText('Search assets, evidence, commands…');
    await userEvent.type(search, 'inventory');
    expect(screen.getByText('inventory_snapshot')).toBeInTheDocument();
    await userEvent.click(screen.getByText('inventory_snapshot'));
    expect(window.location.pathname).toBe('/estate');
  });

  it('exposes an accessible lineage table alternative', async () => {
    window.history.replaceState({}, '', '/estate');
    render(<App />);
    await screen.findByRole('heading', { name: 'Estate & lineage' });
    expect(await screen.findByRole('table', { name: '' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'From asset' })).toBeInTheDocument();
    expect(screen.getByText('External boundary')).toBeInTheDocument();
  });

  it('keeps provider verification explicitly unexecuted', async () => {
    window.history.replaceState({}, '', '/settings');
    render(<App />);
    await screen.findByRole('heading', { name: 'Workspace settings' });
    expect(await screen.findByRole('button', { name: 'Provider not connected' })).toBeDisabled();
    expect(screen.getByText('Unknown — no provider invocation has been recorded.')).toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/v1/demo/snapshot', expect.anything()));
  });

  it('closes evidence drawers with Escape and restores trigger focus', async () => {
    window.history.replaceState({}, '', '/findings');
    render(<App />);
    const trigger = await screen.findByRole('button', { name: /Monthly adjustment is absent/ });
    await userEvent.click(trigger);
    expect(screen.getByRole('dialog', { name: /F-014/ })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: /F-014/ })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});

describe('live runtime isolation', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/overview');
    sessionStorage.clear();
  });

  afterEach(() => {
    cleanup();
    sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it('shows a runtime error without automatically substituting demo records', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('connection refused')));
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'The Reweft API is unavailable' })).toBeInTheDocument();
    expect(screen.getByText(/No synthetic records were substituted/)).toBeInTheDocument();
    expect(screen.queryByText('Systems observed')).not.toBeInTheDocument();
  });

  it('bootstraps the first workspace and persists the scoped browser session', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/runtime')) return Promise.resolve(jsonResponse({ mode: 'bootstrap', bootstrapped: false, demoAvailable: true }));
      if (url.endsWith('/api/v1/auth/bootstrap') && init?.method === 'POST') return Promise.resolve(jsonResponse({ api_token: 'issued-token', workspace_id: 'workspace-new', user_id: 'user-new' }, 201));
      if (/\/workspaces\/workspace-new$/.test(url)) return Promise.resolve(jsonResponse({ id: 'workspace-new', name: 'Acme data team' }));
      if (url.endsWith('/projects') || url.endsWith('/inference-profiles') || url.endsWith('/assessments')) return Promise.resolve(jsonResponse([]));
      return Promise.resolve(jsonResponse({ detail: 'not found' }, 404));
    }));
    render(<App />);
    await screen.findByRole('heading', { name: 'Create the first workspace' });
    await userEvent.type(screen.getByLabelText(/^Bootstrap token/), 'a'.repeat(32));
    await userEvent.type(screen.getByLabelText('Email'), 'owner@example.test');
    await userEvent.type(screen.getByLabelText('Display name'), 'Workspace owner');
    await userEvent.type(screen.getByLabelText('Workspace name'), 'Acme data team');
    await userEvent.click(screen.getByRole('button', { name: 'Create workspace' }));
    expect(await screen.findByRole('heading', { name: 'Workspace overview' })).toBeInTheDocument();
    expect(JSON.parse(sessionStorage.getItem('reweft.live-session.v1') ?? '{}')).toEqual({ token: 'issued-token', workspaceId: 'workspace-new', userId: 'user-new' });
  });

  it('keeps failed authorized requests in a partial live state', async () => {
    saveTestSession();
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/runtime')) return Promise.resolve(jsonResponse({ mode: 'live', bootstrapped: true, demoAvailable: true, persistence: 'sqlite-development' }));
      if (url.endsWith('/projects') || url.endsWith('/inference-profiles') || url.endsWith('/assessments')) return Promise.resolve(jsonResponse([]));
      if (/\/workspaces\/workspace-live$/.test(url)) return Promise.resolve(jsonResponse({ detail: 'workspace store unavailable' }, 503));
      return Promise.resolve(jsonResponse({ detail: 'not found' }, 404));
    }));
    render(<App />);
    expect(await screen.findByText('Partial workspace data')).toBeInTheDocument();
    expect(screen.getByText(/no demo records were substituted/i)).toBeInTheDocument();
    expect(screen.getByText('Live')).toBeInTheDocument();
    expect(screen.queryByText('Synthetic Manufacturing')).not.toBeInTheDocument();
  });

  it('reports a live source-create failure without fixture capability results', async () => {
    window.history.replaceState({}, '', '/connections');
    saveTestSession();
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/runtime')) return Promise.resolve(jsonResponse({ mode: 'live', bootstrapped: true, demoAvailable: true }));
      if (url.endsWith('/projects') || url.endsWith('/inference-profiles') || url.endsWith('/assessments')) return Promise.resolve(jsonResponse([]));
      if (/\/workspaces\/workspace-live$/.test(url)) return Promise.resolve(jsonResponse({ id: 'workspace-live', name: 'Live workspace' }));
      if (url.endsWith('/sources/postgresql') && init?.method === 'POST') return Promise.resolve(jsonResponse({ detail: 'connector runtime unavailable' }, 503));
      return Promise.resolve(jsonResponse({ detail: 'not found' }, 404));
    }));
    render(<App />);
    await screen.findByRole('heading', { name: 'Add PostgreSQL source' });
    const inputs = screen.getByRole('main').querySelectorAll('input');
    await userEvent.type(inputs[0], 'Production metadata');
    await userEvent.type(inputs[1], 'db.internal');
    await userEvent.clear(inputs[2]); await userEvent.type(inputs[2], '5432');
    await userEvent.type(inputs[3], 'analytics');
    await userEvent.type(inputs[4], 'reweft_reader');
    await userEvent.type(inputs[5], 'secret://sources/postgres');
    await userEvent.type(inputs[6], 'public');
    await userEvent.click(screen.getByRole('button', { name: 'Save source' }));
    expect(await screen.findByText('Source operation failed')).toBeInTheDocument();
    expect(screen.getByText(/No fixture result was shown/)).toBeInTheDocument();
    expect(screen.queryByText('Metadata accessible')).not.toBeInTheDocument();
  });

  it('preserves not-tested source state when a real connection test fails', async () => {
    window.history.replaceState({}, '', '/connections');
    saveTestSession();
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/runtime')) return Promise.resolve(jsonResponse({ mode: 'live', bootstrapped: true, demoAvailable: true }));
      if (url.endsWith('/projects') || url.endsWith('/inference-profiles') || url.endsWith('/assessments')) return Promise.resolve(jsonResponse([]));
      if (/\/workspaces\/workspace-live$/.test(url)) return Promise.resolve(jsonResponse({ id: 'workspace-live', name: 'Live workspace' }));
      if (url.endsWith('/sources/postgresql') && init?.method === 'POST') return Promise.resolve(jsonResponse({ id: 'source-1', name: 'Production metadata', connector: 'postgresql', test_status: 'Not tested' }, 201));
      if (url.endsWith('/sources/source-1/test')) return Promise.resolve(jsonResponse({ detail: 'network unreachable' }, 503));
      return Promise.resolve(jsonResponse({ detail: 'not found' }, 404));
    }));
    render(<App />);
    await screen.findByRole('heading', { name: 'Add PostgreSQL source' });
    const inputs = screen.getByRole('main').querySelectorAll('input');
    await userEvent.type(inputs[0], 'Production metadata');
    await userEvent.type(inputs[1], 'db.internal');
    await userEvent.clear(inputs[2]); await userEvent.type(inputs[2], '5432');
    await userEvent.type(inputs[3], 'analytics');
    await userEvent.type(inputs[4], 'reweft_reader');
    await userEvent.type(inputs[5], 'secret://sources/postgres');
    await userEvent.type(inputs[6], 'public');
    await userEvent.click(screen.getByRole('button', { name: 'Save source' }));
    await screen.findByText('Not tested');
    await userEvent.click(screen.getByRole('button', { name: 'Test connection' }));
    expect(await screen.findByText('Source operation failed')).toBeInTheDocument();
    expect(screen.getByText(/network unreachable/)).toBeInTheDocument();
    expect(screen.getByText('Not tested')).toBeInTheDocument();
    expect(screen.queryByText('Ready')).not.toBeInTheDocument();
  });
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function saveTestSession() {
  sessionStorage.setItem('reweft.live-session.v1', JSON.stringify({ token: 'test-bearer', workspaceId: 'workspace-live' }));
}
