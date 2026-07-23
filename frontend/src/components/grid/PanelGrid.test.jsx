// Render smoke tests for the K2 grid shell: panels render in saved order and size, the box
// contract's drill-through and header-action slots behave independently, and edit mode
// exposes resize/remove/re-add. Drag itself is @dnd-kit's concern (and needs a real pointer),
// so ordering is exercised through the persistence path instead — see layoutMerge.test.js
// for the reconciliation rules.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import PanelGrid from './PanelGrid.jsx';

// The grid calls the layout API on mount; keep it hermetic and offline-shaped.
vi.mock('../../services/layoutApi', () => ({
  fetchLayout: vi.fn(() => Promise.resolve([])),
  saveLayout: vi.fn(() => Promise.resolve([])),
}));
import { fetchLayout, saveLayout } from '../../services/layoutApi';

function makePanels() {
  return [
    { id: 'releases', title: 'Releases', render: () => <p>release body</p> },
    { id: 'submittals', title: 'Submittals', render: () => <p>submittal body</p> },
    { id: 'budget', title: 'Budget', render: () => <p>budget body</p> },
  ];
}

// Rendered panel ids, in document order — the thing ordering tests actually care about.
function renderedIds() {
  return [...document.querySelectorAll('[data-panel-id]')].map(el => el.dataset.panelId);
}

function panelEl(id) {
  return document.querySelector(`[data-panel-id="${id}"]`);
}

const editLayout = () => screen.getByRole('button', { name: 'Edit layout' });

// This jsdom setup exposes window.localStorage as a bare object (no setItem/clear), so
// install a working in-memory Storage per test. The hook tolerates either — its reads and
// writes are try/catch'd — but the stub lets us exercise the cached-layout path.
function stubLocalStorage(seed = {}) {
  const store = { ...seed };
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    writable: true,
    value: {
      getItem: k => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: k => { delete store[k]; },
      clear: () => { for (const k of Object.keys(store)) delete store[k]; },
    },
  });
  return store;
}

beforeEach(() => {
  stubLocalStorage();
  vi.mocked(fetchLayout).mockResolvedValue([]);
  vi.mocked(saveLayout).mockResolvedValue([]);
});

afterEach(() => vi.clearAllMocks());

describe('PanelGrid', () => {
  it('renders every panel body in canonical order by default', async () => {
    render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);

    expect(screen.getByText('release body')).toBeDefined();
    expect(screen.getByText('submittal body')).toBeDefined();
    expect(screen.getByText('budget body')).toBeDefined();
    await waitFor(() => expect(fetchLayout).toHaveBeenCalledWith('test:1'));
  });

  it('applies a server-saved order over the canonical one', async () => {
    vi.mocked(fetchLayout).mockResolvedValue([{ id: 'budget' }, { id: 'releases' }, { id: 'submittals' }]);
    render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);

    await waitFor(() => expect(renderedIds()).toEqual(['budget', 'releases', 'submittals']));
  });

  it('applies a saved size class as a column span', async () => {
    vi.mocked(fetchLayout).mockResolvedValue([{ id: 'releases', span: 3 }]);
    render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);

    await waitFor(() => expect(panelEl('releases').className).toContain('lg:col-span-3'));
    expect(panelEl('submittals').className).not.toContain('col-span');
  });

  it('quantizes height to row units so panels line up instead of following content', async () => {
    vi.mocked(fetchLayout).mockResolvedValue([
      { id: 'releases', rows: 4 },
      { id: 'submittals' },
    ]);
    render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);

    await waitFor(() => expect(panelEl('releases').className).toContain('row-span-4'));
    // Unspecified panels take the default height rather than sizing to their content.
    expect(panelEl('submittals').className).toContain('row-span-2');
    // The body scrolls inside the fixed height instead of stretching the row.
    expect(panelEl('submittals').querySelector('.overflow-y-auto')).not.toBeNull();
  });

  it('hides a panel the saved layout parks, and lists it as available in edit mode', async () => {
    vi.mocked(fetchLayout).mockResolvedValue([{ id: 'budget', hidden: true }]);
    render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);

    await waitFor(() => expect(renderedIds()).toEqual(['releases', 'submittals']));

    fireEvent.click(editLayout());
    expect(screen.getByRole('button', { name: '+ Budget' })).toBeDefined();
  });

  it('surfaces a panel added since the layout was saved', async () => {
    // Saved layout predates 'budget'; it must still render, not vanish.
    vi.mocked(fetchLayout).mockResolvedValue([{ id: 'submittals' }, { id: 'releases' }]);
    render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);

    await waitFor(() => expect(renderedIds()).toEqual(['submittals', 'releases', 'budget']));
  });

  it('opens the drill-through when the header is clicked', () => {
    const onOpen = vi.fn();
    const panels = [{ id: 'a', title: 'Releases', onOpen, render: () => <p>body</p> }];
    render(<PanelGrid surfaceKey="test:1" panels={panels} />);

    fireEvent.click(screen.getByRole('button', { name: /Releases/ }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('does not open the drill-through when the header action is clicked', () => {
    const onOpen = vi.fn();
    const onAction = vi.fn();
    const panels = [{
      id: 'a',
      title: 'Notes',
      onOpen,
      headerAction: <button onClick={onAction}>+ Add Note</button>,
      render: () => <p>body</p>,
    }];
    render(<PanelGrid surfaceKey="test:1" panels={panels} />);

    fireEvent.click(screen.getByText('+ Add Note'));
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onOpen).not.toHaveBeenCalled(); // the action slot must never drill through
  });

  it('renders the empty state instead of the body when isEmpty', () => {
    const panels = [{
      id: 'a', title: 'RFIs', isEmpty: true,
      empty: <p>No open RFIs</p>, render: () => <p>should not render</p>,
    }];
    render(<PanelGrid surfaceKey="test:1" panels={panels} />);

    expect(screen.getByText('No open RFIs')).toBeDefined();
    expect(screen.queryByText('should not render')).toBeNull();
  });

  it('stays usable when layout persistence is unavailable', async () => {
    vi.mocked(fetchLayout).mockRejectedValue(new Error('offline'));
    render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);

    // Falls back to canonical order rather than rendering nothing.
    await waitFor(() => expect(renderedIds()).toEqual(['releases', 'submittals', 'budget']));
  });

  it('seeds from the localStorage cache on first paint, before the server responds', () => {
    stubLocalStorage({
      'brain_grid_layout:test:1': JSON.stringify([{ id: 'budget' }, { id: 'submittals' }, { id: 'releases' }]),
    });
    // Server call never settles — the cached layout is what avoids a reorder flash.
    vi.mocked(fetchLayout).mockReturnValue(new Promise(() => {}));

    render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);
    expect(renderedIds()).toEqual(['budget', 'submittals', 'releases']);
  });

  it('does not echo the loaded server layout back to the server', async () => {
    // Applying the server's own layout is a state change, so without explicit suppression
    // it would schedule a save — every page load writing back what it just read.
    vi.mocked(fetchLayout).mockResolvedValue([{ id: 'budget' }, { id: 'releases' }, { id: 'submittals' }]);
    render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);

    await waitFor(() => expect(renderedIds()).toEqual(['budget', 'releases', 'submittals']));
    // Wait past the 600ms save debounce — a scheduled save would have fired by now.
    await new Promise(r => setTimeout(r, 800));
    expect(saveLayout).not.toHaveBeenCalled();
  });

  describe('edit mode', () => {
    it('is off by default and toggles on', () => {
      render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);
      expect(screen.queryByRole('button', { name: 'Width L' })).toBeNull();

      fireEvent.click(editLayout());
      expect(screen.getByRole('button', { name: 'Done' })).toBeDefined();
      expect(screen.getAllByRole('button', { name: 'Width L' }).length).toBe(3);
    });

    it('suppresses drill-through while editing', () => {
      const onOpen = vi.fn();
      const panels = [{ id: 'a', title: 'Releases', onOpen, render: () => <p>body</p> }];
      render(<PanelGrid surfaceKey="test:1" panels={panels} />);

      fireEvent.click(editLayout());
      // The header is no longer a button, so a click can't drill through.
      expect(screen.queryByRole('button', { name: /^Releases/ })).toBeNull();
      expect(onOpen).not.toHaveBeenCalled();
    });

    it('resizes a panel via its size chips and persists the span', async () => {
      render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);
      fireEvent.click(editLayout());

      // Third chip row belongs to 'budget'; grab the one inside that panel.
      const budgetL = panelEl('budget').querySelector('[aria-label="Width L"]');
      fireEvent.click(budgetL);

      await waitFor(() => expect(panelEl('budget').className).toContain('lg:col-span-3'));
      await waitFor(() => expect(saveLayout).toHaveBeenCalledWith('test:1', [
        { id: 'releases', span: 1, rows: 2, hidden: false },
        { id: 'submittals', span: 1, rows: 2, hidden: false },
        { id: 'budget', span: 3, rows: 2, hidden: false },
      ]));
    });

    it('removes a panel and adds it back from the available tray', async () => {
      render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);
      fireEvent.click(editLayout());

      fireEvent.click(screen.getByRole('button', { name: 'Remove Submittals' }));
      await waitFor(() => expect(renderedIds()).toEqual(['releases', 'budget']));

      fireEvent.click(screen.getByRole('button', { name: '+ Submittals' }));
      // Re-added in its original slot, not appended to the end.
      await waitFor(() => expect(renderedIds()).toEqual(['releases', 'submittals', 'budget']));
    });

    it('omits size chips for a panel pinned to one size', () => {
      const panels = [{
        id: 'a', title: 'Wide', sizes: [3], rowSizes: [2], render: () => <p>body</p>,
      }];
      render(<PanelGrid surfaceKey="test:1" panels={panels} />);
      fireEvent.click(editLayout());

      expect(screen.queryByRole('button', { name: /^Width / })).toBeNull();
      expect(screen.queryByRole('button', { name: /^Height / })).toBeNull();
      // Still removable, and still rendered at its pinned size.
      expect(screen.getByRole('button', { name: 'Remove Wide' })).toBeDefined();
      expect(panelEl('a').className).toContain('lg:col-span-3');
      expect(panelEl('a').className).toContain('row-span-2');
    });

    it('tells render() its current size so bigger can mean more content', async () => {
      // Size is a density control, not just geometry — a list panel must be able to show
      // more rows when the user makes it taller.
      const panels = [{
        id: 'a', title: 'Submittals',
        render: ({ span, rows }) => <p>{`w${span}h${rows}`}</p>,
      }];
      render(<PanelGrid surfaceKey="test:1" panels={panels} />);
      expect(screen.getByText('w1h2')).toBeDefined();

      fireEvent.click(editLayout());
      fireEvent.click(panelEl('a').querySelector('[aria-label="Height 4"]'));
      await waitFor(() => expect(screen.getByText('w1h4')).toBeDefined());

      fireEvent.click(panelEl('a').querySelector('[aria-label="Width L"]'));
      await waitFor(() => expect(screen.getByText('w3h4')).toBeDefined());
    });

    it('pins a KPI tile to 1x1 — movable and removable, but not resizable', () => {
      const panels = [{
        id: 'kpi_a', title: 'Total Releases', variant: 'kpi',
        sizes: [1], rowSizes: [1], render: () => <p>6</p>,
      }];
      render(<PanelGrid surfaceKey="test:1" panels={panels} />);
      fireEvent.click(editLayout());

      expect(screen.queryByRole('button', { name: /^Width / })).toBeNull();
      expect(screen.queryByRole('button', { name: /^Height / })).toBeNull();
      expect(screen.getByRole('button', { name: 'Remove Total Releases' })).toBeDefined();
      expect(panelEl('kpi_a').className).toContain('row-span-1');
    });

    it('only ever re-offers panels the caller declared (closed catalog)', async () => {
      vi.mocked(fetchLayout).mockResolvedValue([
        { id: 'releases', hidden: true },
        { id: 'ghost_widget', hidden: true }, // stale/injected id must not become addable
      ]);
      render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);
      fireEvent.click(editLayout());

      await waitFor(() => expect(screen.getByRole('button', { name: '+ Releases' })).toBeDefined());
      expect(screen.queryByRole('button', { name: /ghost/i })).toBeNull();
    });

    it('resizes a panel vertically via its height chips', async () => {
      render(<PanelGrid surfaceKey="test:1" panels={makePanels()} />);
      fireEvent.click(editLayout());

      const tall = panelEl('releases').querySelector('[aria-label="Height 4"]');
      fireEvent.click(tall);

      await waitFor(() => expect(panelEl('releases').className).toContain('row-span-4'));
      await waitFor(() => expect(saveLayout).toHaveBeenCalledWith('test:1', [
        { id: 'releases', span: 1, rows: 4, hidden: false },
        { id: 'submittals', span: 1, rows: 2, hidden: false },
        { id: 'budget', span: 1, rows: 2, hidden: false },
      ]));
    });
  });
});
