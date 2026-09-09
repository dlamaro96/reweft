import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../src/app/App';

describe('Reweft application shell', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/overview');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('API unavailable')));
  });

  afterEach(() => {
    cleanup();
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
    expect(screen.getByRole('table', { name: '' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'From asset' })).toBeInTheDocument();
    expect(screen.getByText('External boundary')).toBeInTheDocument();
  });

  it('keeps provider verification explicitly unexecuted', async () => {
    window.history.replaceState({}, '', '/settings');
    render(<App />);
    await screen.findByRole('heading', { name: 'Workspace settings' });
    expect(screen.getByRole('button', { name: 'Provider not connected' })).toBeDisabled();
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
