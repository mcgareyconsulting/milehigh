/**
 * @milehigh-header
 * schema_version: 2
 * purpose: State + persistence for the K2 configurable grid engine. Owns a surface's layout —
 *   panel order, per-panel width AND height size classes, and hidden/shown — seeding from localStorage (instant,
 *   no flash), overlaying the server copy when it arrives (cross-device), reconciling both
 *   against the canonical panel set, and writing back on change (optimistic locally, debounced
 *   to the server). Persistence is best-effort by design: if /brain/layout is unreachable the
 *   grid still drags, resizes and remembers — it just stops following the user across devices.
 * exports:
 *   useGridLayout(surfaceKey, panels): {layout, visible, hidden, isLoaded,
 *                                       reorder, setSpan, setRows, hide, show, reset}
 * imports_from: [react, ./layoutMerge, ../../services/layoutApi]
 * imported_by: [components/grid/PanelGrid.jsx]
 * invariants:
 *   - `layout` always has exactly one entry per canonical panel (see mergeLayout).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { mergeLayout } from './layoutMerge';
import { fetchLayout, saveLayout } from '../../services/layoutApi';

const LS_PREFIX = 'brain_grid_layout:';
const SAVE_DEBOUNCE_MS = 600;

function readLocal(surfaceKey) {
  try {
    const raw = window.localStorage.getItem(LS_PREFIX + surfaceKey);
    const parsed = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null; // private mode / corrupt entry — treat as "no saved layout"
  }
}

function writeLocal(surfaceKey, layout) {
  try {
    window.localStorage.setItem(LS_PREFIX + surfaceKey, JSON.stringify(layout));
  } catch {
    /* storage full or blocked — the in-memory layout still works for this session */
  }
}

const sameLayout = (a, b) =>
  a.length === b.length &&
  a.every((x, i) => x.id === b[i].id && x.span === b[i].span && x.rows === b[i].rows && x.hidden === b[i].hidden);

/**
 * @param {string} surfaceKey - identifies this grid instance, e.g. "projects:560",
 *   "employee_home", "metrics". Project-scoped grids must include the binding so one
 *   project's arrangement doesn't overwrite another's.
 * @param {Array} panels - canonical panel descriptors in default order.
 */
export function useGridLayout(surfaceKey, panels) {
  // Stable identity so effects don't re-fire when the caller rebuilds the array inline
  // (the common case). Keyed on the parts that affect reconciliation, not panel bodies.
  const canonicalKey = panels
    .map(p => `${p.id}:${p.span || 1}:${p.rows || 2}:${(p.sizes || []).join('')}:${(p.rowSizes || []).join('')}`)
    .join('|');
  const canonical = useMemo(() => panels, [canonicalKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const [layout, setLayoutState] = useState(() => mergeLayout(canonical, readLocal(surfaceKey)));

  const [isLoaded, setIsLoaded] = useState(false);
  const saveTimer = useRef(null);
  // Suppresses the save that would otherwise fire when the server's own layout lands.
  const skipNextSave = useRef(true);

  // Re-reconcile whenever the panel set changes (a panel added/removed at runtime).
  useEffect(() => {
    setLayoutState(prev => {
      const next = mergeLayout(canonical, prev);
      return sameLayout(next, prev) ? prev : next;
    });
  }, [canonical]);

  // Pull the server copy once per surface; it wins over localStorage when present.
  useEffect(() => {
    let cancelled = false;
    setIsLoaded(false);
    skipNextSave.current = true;

    fetchLayout(surfaceKey)
      .then(serverLayout => {
        if (cancelled || !serverLayout.length) return;
        const merged = mergeLayout(canonical, serverLayout);
        // Adopting the server's own layout is a state change, which would otherwise
        // schedule a save — every page load writing back what it just read. Re-arm the
        // guard here (not just at effect start) because this runs after the mount pass
        // has already consumed it.
        skipNextSave.current = true;
        setLayoutState(merged);
        writeLocal(surfaceKey, merged);
      })
      .catch(() => {
        /* offline or endpoint missing — keep the localStorage-seeded layout */
      })
      .finally(() => {
        if (!cancelled) setIsLoaded(true);
      });

    return () => { cancelled = true; };
  }, [surfaceKey, canonical]);

  // Persist on change: localStorage immediately, server debounced.
  useEffect(() => {
    if (skipNextSave.current) {
      skipNextSave.current = false;
      return;
    }
    writeLocal(surfaceKey, layout);

    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      saveLayout(surfaceKey, layout).catch(() => {
        /* best-effort; localStorage already holds it */
      });
    }, SAVE_DEBOUNCE_MS);

    return () => { if (saveTimer.current) clearTimeout(saveTimer.current); };
  }, [layout, surfaceKey]);

  const update = useCallback(fn => {
    setLayoutState(prev => mergeLayout(canonical, fn(prev)));
  }, [canonical]);

  /** Move a panel to sit where another one is (drag-and-drop reorder). */
  const reorder = useCallback((activeId, overId) => {
    update(prev => {
      const from = prev.findIndex(l => l.id === activeId);
      const to = prev.findIndex(l => l.id === overId);
      if (from === -1 || to === -1 || from === to) return prev;
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
  }, [update]);

  const setSpan = useCallback((id, span) => {
    update(prev => prev.map(l => (l.id === id ? { ...l, span } : l)));
  }, [update]);

  const setRows = useCallback((id, rows) => {
    update(prev => prev.map(l => (l.id === id ? { ...l, rows } : l)));
  }, [update]);

  const hide = useCallback(id => {
    update(prev => prev.map(l => (l.id === id ? { ...l, hidden: true } : l)));
  }, [update]);

  const show = useCallback(id => {
    update(prev => prev.map(l => (l.id === id ? { ...l, hidden: false } : l)));
  }, [update]);

  /** Drop the customization and go back to the page's default arrangement. */
  const reset = useCallback(() => {
    setLayoutState(mergeLayout(canonical, null));
  }, [canonical]);

  const visible = useMemo(() => layout.filter(l => !l.hidden), [layout]);
  const hidden = useMemo(() => layout.filter(l => l.hidden), [layout]);

  return { layout, visible, hidden, isLoaded, reorder, setSpan, setRows, hide, show, reset };
}
