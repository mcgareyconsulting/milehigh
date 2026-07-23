// The catalog is data-driven, so the failure mode is a shape mismatch: a project missing a
// field one body dereferences renders `undefined` or throws. These sweep every panel body and
// every drill-through across every demo project, which is what catches that.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { buildProjectPanels, renderProjectModal, PROJECT_MODAL_TITLES } from './projectPanels.jsx';
import { DEMO_PROJECTS } from './demoProjects.js';

afterEach(cleanup);

const handlers = () => ({ onOpen: vi.fn(), onAction: vi.fn() });

describe('project panel catalog', () => {
  it('exposes a modal title for every panel', () => {
    const panels = buildProjectPanels(DEMO_PROJECTS[0], handlers());
    for (const p of panels) {
      expect(PROJECT_MODAL_TITLES[p.id], `no modal title for ${p.id}`).toBeDefined();
    }
  });

  it('keeps panel ids stable and unique — they are the layout persistence key', () => {
    const ids = buildProjectPanels(DEMO_PROJECTS[0], handlers()).map(p => p.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual([
      'submittals', 'releases', 'schedule', 'budget', 'tm', 'rentals', 'co',
      'rfi', 'punch', 'contacts', 'drawings', 'notes', 'todo',
    ]);
  });

  it('offers the same catalog for every project — data changes, layout does not', () => {
    const byProject = DEMO_PROJECTS.map(p => buildProjectPanels(p, handlers()).map(x => x.id));
    for (const ids of byProject) expect(ids).toEqual(byProject[0]);
  });

  for (const project of DEMO_PROJECTS) {
    describe(`#${project.number} ${project.name}`, () => {
      it('renders every panel body at every height without throwing', () => {
        for (const panel of buildProjectPanels(project, handlers())) {
          for (const rows of [1, 2, 3, 4]) {
            // isEmpty panels never call render() — PanelGrid shows `empty` instead.
            const node = panel.isEmpty ? panel.empty : panel.render({ span: panel.span || 1, rows });
            expect(() => render(<div>{node}</div>), `${panel.id} @ rows=${rows}`).not.toThrow();
            cleanup();
          }
        }
      });

      it('renders every drill-through without throwing', () => {
        for (const panel of buildProjectPanels(project, handlers())) {
          expect(() => render(<div>{renderProjectModal(panel.id, project)}</div>), panel.id)
            .not.toThrow();
          cleanup();
        }
      });

      it('never prints a literal undefined', () => {
        for (const panel of buildProjectPanels(project, handlers())) {
          const node = panel.isEmpty ? panel.empty : panel.render({ span: panel.span || 1, rows: 4 });
          const { container } = render(<div>{node}</div>);
          expect(container.textContent, `${panel.id} body`).not.toMatch(/undefined|NaN/);
          cleanup();
        }
      });
    });
  }

  it('shows more list rows as a panel gets taller', () => {
    const project = DEMO_PROJECTS[0];
    const releases = buildProjectPanels(project, handlers()).find(p => p.id === 'releases');

    const { container: short } = render(<div>{releases.render({ span: 1, rows: 1 })}</div>);
    const shortRows = short.textContent.match(/450-\d+/g) || [];
    cleanup();

    const { container: tall } = render(<div>{releases.render({ span: 1, rows: 4 })}</div>);
    const tallRows = tall.textContent.match(/450-\d+/g) || [];

    expect(tallRows.length).toBeGreaterThan(shortRows.length);
  });

  it('says what it is hiding rather than silently truncating', () => {
    const project = DEMO_PROJECTS[0];
    const submittals = buildProjectPanels(project, handlers()).find(p => p.id === 'submittals');
    render(<div>{submittals.render({ span: 1, rows: 1 })}</div>);
    expect(screen.getByText(/more — resize taller/)).toBeDefined();
  });

  it('drills through on the header handler and fires the action chip separately', () => {
    const h = handlers();
    const panels = buildProjectPanels(DEMO_PROJECTS[0], h);
    const submittals = panels.find(p => p.id === 'submittals');

    submittals.onOpen();
    expect(h.onOpen).toHaveBeenCalledWith('submittals');

    render(<div>{submittals.headerAction}</div>);
    fireEvent.click(screen.getByText('View All'));
    expect(h.onAction).toHaveBeenCalledWith('Submittals → View All');
    // The action chip must never also drill through.
    expect(h.onOpen).toHaveBeenCalledTimes(1);
  });

  // ── tiling ──────────────────────────────────────────────────────────────────────
  // Panel heights are quantized, so the default layout can leave visible holes: CSS grid
  // cannot start the full-width To-Do until every column has reached the same depth, and any
  // column that falls short is padded with empty cells. This replays the browser's sparse
  // auto-placement so a future catalog change fails here instead of on Bill's screen.
  function placeGrid(panels, columns = 3) {
    const filled = new Set();
    const key = (r, c) => `${r}:${c}`;
    let curR = 0;
    let curC = 0;
    let maxR = 0;

    for (const p of panels) {
      const w = Math.min(p.span || 1, columns);
      const h = p.rows || 2;
      let r = curR;
      let c = curC;
      for (;;) {
        if (c + w > columns) { r += 1; c = 0; continue; }
        let free = true;
        for (let dr = 0; dr < h && free; dr += 1) {
          for (let dc = 0; dc < w; dc += 1) {
            if (filled.has(key(r + dr, c + dc))) { free = false; break; }
          }
        }
        if (free) break;
        c += 1;
      }
      for (let dr = 0; dr < h; dr += 1) {
        for (let dc = 0; dc < w; dc += 1) filled.add(key(r + dr, c + dc));
      }
      maxR = Math.max(maxR, r + h);
      curR = r;
      curC = c + w;
    }

    const gaps = [];
    for (let r = 0; r < maxR; r += 1) {
      for (let c = 0; c < columns; c += 1) if (!filled.has(key(r, c))) gaps.push([r, c]);
    }
    return { gaps, rows: maxR };
  }

  it('tiles the default layout with no empty cells', () => {
    const panels = buildProjectPanels(DEMO_PROJECTS[0], handlers());
    const { gaps } = placeGrid(panels, 3);
    expect(gaps, `empty grid cells at ${JSON.stringify(gaps)}`).toEqual([]);
  });

  it('tiles identically for every project — heights are per-panel, not per-project', () => {
    const shapes = DEMO_PROJECTS.map(p =>
      buildProjectPanels(p, handlers()).map(x => `${x.id}:${x.span || 1}x${x.rows || 2}`).join(','));
    for (const s of shapes) expect(s).toBe(shapes[0]);
  });

  it('explains a blocked panel instead of faking numbers', () => {
    // Budget/T&M/CO have no backing model in app/models.py — a fabricated figure here would
    // read as real data on a page Bill reviews.
    const railyard = DEMO_PROJECTS.find(p => p.number === '944');
    const panels = buildProjectPanels(railyard, handlers());

    const budget = panels.find(p => p.id === 'budget');
    expect(budget.isEmpty).toBe(true);
    render(<div>{budget.empty}</div>);
    expect(screen.getByText(/no Pay App model exists yet/)).toBeDefined();

    // ...and the KPI strip agrees rather than inventing a total.
    const billed = railyard.kpis.find(k => k.id === 'billed');
    expect(billed.value).toBe('—');
    expect(billed.blocked).toBeTruthy();
  });
});
