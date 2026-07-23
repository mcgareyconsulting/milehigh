/**
 * @milehigh-header
 * schema_version: 2
 * purpose: The K2 configurable grid engine — a customizable dashboard shell. Panels drag to
 *   reorder (snapping to grid columns), resize in both axes to fixed size classes, and can be removed
 *   and re-added, all persisted per user per surface. One shell, three consumers: the Projects
 *   page (D1, project-scoped), Employee Home (D2, user-scoped), and the metrics grid. Callers
 *   hand it a canonical list of panel descriptors (the "box contract"); the grid owns layout,
 *   drag, resize and persistence, and nothing else — panel bodies are entirely the caller's.
 * exports:
 *   PanelGrid: the grid shell
 * imports_from: [react, @dnd-kit/core, @dnd-kit/sortable, ./Panel, ./useGridLayout, ./layoutMerge]
 * imported_by: [pages/GridDemo.jsx, pages/ProjectDetail.jsx (D1), pages/EmployeeHome.jsx (D2)]
 * invariants:
 *   - Panel ids must be stable across renders — they are the persistence key.
 *   - Normal mode drags from the ⠿ handle only, so headers stay clickable; edit mode drags
 *     from anywhere and suppresses drill-through.
 *
 * Box contract (one entry of `panels`):
 *   {
 *     id:           string      // stable, unique — the persistence key
 *     title:        string
 *     dot?:         'blue'|'green'|'yellow'|'orange'|'red'|'purple'|'pink'|'teal'|'gray'
 *     span?:        1 | 2 | 3   // DEFAULT width class; the user's choice overrides it
 *     sizes?:       number[]    // allowed width classes (default [1,2,3]); [n] pins the width
 *     rows?:        1..4        // DEFAULT height in grid row units (default 2)
 *     rowSizes?:    number[]    // allowed height classes (default [1,2,3,4]); [n] pins it
 *     variant?:     'kpi'       // compact stat tile — no header chrome
 *     onOpen?:      () => void  // drill-through: header click opens the detail modal
 *     headerAction?: ReactNode  // right-aligned slot ("+ Add Note"); never opens the modal
 *     render:       ({span, rows}) => ReactNode   // panel body, told its current size
 *     isEmpty?:     boolean     // render the empty state instead of the body
 *     empty?:       ReactNode   // custom empty state
 *   }
 *
 * Two conventions the consumers share (see density.js):
 *   - Size means CONTENT DENSITY, not just geometry. A list panel should show more rows at a
 *     bigger size; `render` is handed {span, rows} for exactly that. Use listCapacity(rows).
 *   - A KPI/stat tile pins itself with sizes:[1], rowSizes:[1] — a single number has no
 *     denser state, so its resize chips disappear and only move/remove remain.
 *
 * The panel list is a CLOSED catalog: users choose from what the caller supplies and cannot
 * add anything else. The tray only ever re-offers panels the caller already declared.
 *
 * Theming: `theme="dark"` switches the shell to the palette in docs/projects-page-mockup.html.
 * Colours live in gridTheme.css as --k2-* tokens; nothing here or in Panel.jsx names one
 * directly, so the same engine can serve a dark Projects page and light surfaces elsewhere.
 */
import { useMemo, useState } from 'react';
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import { SortablePanel } from './Panel';
import { useGridLayout } from './useGridLayout';
import './gridTheme.css';

const COLUMN_CLASS = {
  2: 'grid-cols-1 md:grid-cols-2',
  3: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3',
  4: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-4',
};

// Heights are quantized to this row unit instead of following content, so panels line up in
// bands rather than drifting to whatever each body happens to measure. A panel taller than
// its span scrolls internally (see Panel.jsx). Rendered height = rows*UNIT + (rows-1)*gap.
const ROW_UNIT_PX = 96;

export default function PanelGrid({
  surfaceKey,
  panels,
  columns = 3,
  className = '',
  editable = true,
  theme = 'light',
}) {
  const { visible, hidden, reorder, setSpan, setRows, hide, show, reset } = useGridLayout(surfaceKey, panels);
  const [editing, setEditing] = useState(false);

  const byId = useMemo(() => new Map(panels.map(p => [p.id, p])), [panels]);
  const visibleIds = useMemo(() => visible.map(l => l.id), [visible]);

  const sensors = useSensors(
    // A small activation distance keeps a click on the handle from registering as a drag.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  function handleDragEnd({ active, over }) {
    if (over && active.id !== over.id) reorder(active.id, over.id);
  }

  return (
    <div className={`k2-surface ${theme === 'dark' ? 'k2-dark' : ''}`}>
      {editable && (
        <div className="flex items-center justify-between gap-3 mb-2">
          {/* The mockup's `.drag-hint` strip — it's the only thing telling a first-time user
              the ⠿ handle does anything, so it stays visible outside edit mode. */}
          <p className="text-[11px] text-[var(--k2-handle)] min-w-0 truncate">
            {editing
              ? '↔ width · ↕ height — on list panels, bigger shows more rows'
              : '⠿  Drag cards to rearrange your layout — positions are saved automatically'}
          </p>
          <div className="flex items-center gap-3 shrink-0">
            {editing && (
              <button
                type="button"
                onClick={reset}
                className="text-xs text-[var(--k2-muted)] hover:text-[var(--k2-accent)] transition-colors"
              >
                Reset layout
              </button>
            )}
            <button
              type="button"
              onClick={() => setEditing(e => !e)}
              className={`text-[11px] font-semibold px-2.5 py-1 rounded-md transition-colors ${
                editing
                  ? 'bg-[var(--k2-accent-strong)] text-white'
                  : 'bg-[var(--k2-chip)] text-[var(--k2-accent)] hover:bg-[var(--k2-accent-strong)] hover:text-white'
              }`}
            >
              {editing ? 'Done' : 'Edit layout'}
            </button>
          </div>
        </div>
      )}

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={visibleIds} strategy={rectSortingStrategy}>
          <div
            style={{ gridAutoRows: `${ROW_UNIT_PX}px` }}
            className={`grid ${COLUMN_CLASS[columns] || COLUMN_CLASS[3]} gap-3 ${className}`}
          >
            {visible.map(entry => {
              const panel = byId.get(entry.id);
              if (!panel) return null;
              return (
                <SortablePanel
                  key={panel.id}
                  panel={panel}
                  span={entry.span}
                  rows={entry.rows}
                  editing={editing}
                  onSetSpan={s => setSpan(panel.id, s)}
                  onSetRows={r => setRows(panel.id, r)}
                  onHide={() => hide(panel.id)}
                />
              );
            })}
          </div>
        </SortableContext>
      </DndContext>

      {/* Removed widgets live here in edit mode, ready to be added back. */}
      {editing && (
        <div className="mt-4 rounded-[10px] border border-dashed border-[var(--k2-border)] p-3">
          <p className="text-[10px] font-bold uppercase tracking-[0.5px] text-[var(--k2-muted)] mb-2">
            Available widgets
          </p>
          {hidden.length === 0 ? (
            <p className="text-[11px] text-[var(--k2-muted)]">
              All widgets are on the dashboard. Remove one with ✕ to park it here.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {hidden.map(entry => {
                const panel = byId.get(entry.id);
                if (!panel) return null;
                return (
                  <button
                    key={entry.id}
                    type="button"
                    onClick={() => show(entry.id)}
                    className="px-2.5 py-1 rounded-md text-[11px] font-semibold
                      bg-[var(--k2-chip)] text-[var(--k2-accent)]
                      hover:bg-[var(--k2-accent-strong)] hover:text-white transition-colors"
                  >
                    + {panel.title}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
