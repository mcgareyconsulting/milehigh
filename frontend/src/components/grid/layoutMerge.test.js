import { describe, it, expect } from 'vitest';
import { mergeLayout } from './layoutMerge';

const PANELS = [
  { id: 'a', title: 'A' },
  { id: 'b', title: 'B' },
  { id: 'c', title: 'C' },
];

const ids = layout => layout.map(l => l.id);

describe('mergeLayout', () => {
  it('returns canonical order at default size when nothing is saved', () => {
    expect(mergeLayout(PANELS, null)).toEqual([
      { id: 'a', span: 1, rows: 2, hidden: false },
      { id: 'b', span: 1, rows: 2, hidden: false },
      { id: 'c', span: 1, rows: 2, hidden: false },
    ]);
  });

  it('honors a saved reordering', () => {
    expect(ids(mergeLayout(PANELS, [{ id: 'c' }, { id: 'a' }, { id: 'b' }])))
      .toEqual(['c', 'a', 'b']);
  });

  it('honors saved size classes and hidden flags', () => {
    const merged = mergeLayout(PANELS, [
      { id: 'a', span: 3 },
      { id: 'b', span: 2, rows: 2, hidden: true },
      { id: 'c' },
    ]);
    expect(merged).toEqual([
      { id: 'a', span: 3, rows: 2, hidden: false },
      { id: 'b', span: 2, rows: 2, hidden: true },
      { id: 'c', span: 1, rows: 2, hidden: false },
    ]);
  });

  it('appends newly-added panels visible and at default size', () => {
    const merged = mergeLayout(PANELS, [{ id: 'c', span: 2 }, { id: 'a' }]);
    expect(merged).toEqual([
      { id: 'c', span: 2, rows: 2, hidden: false },
      { id: 'a', span: 1, rows: 2, hidden: false },
      { id: 'b', span: 1, rows: 2, hidden: false }, // new since save — must not appear hidden
    ]);
  });

  it('drops stale ids that no longer map to a panel', () => {
    expect(ids(mergeLayout(PANELS, [{ id: 'zz' }, { id: 'b' }, { id: 'a' }, { id: 'c' }])))
      .toEqual(['b', 'a', 'c']);
  });

  it('dedupes a corrupt saved layout', () => {
    expect(ids(mergeLayout(PANELS, [{ id: 'a' }, { id: 'a' }, { id: 'b' }])))
      .toEqual(['a', 'b', 'c']);
  });

  it('clamps a span the panel no longer allows', () => {
    // Panel 'a' only permits full width now; a saved span of 1 must not survive.
    const panels = [{ id: 'a', sizes: [3] }, { id: 'b' }];
    const merged = mergeLayout(panels, [{ id: 'a', span: 1 }, { id: 'b', span: 2 }]);
    expect(merged[0]).toEqual({ id: 'a', span: 3, rows: 2, hidden: false });
    expect(merged[1]).toEqual({ id: 'b', span: 2, rows: 2, hidden: false });
  });

  it('falls back to the first allowed size when the default is not permitted', () => {
    const panels = [{ id: 'a', span: 1, sizes: [2, 3] }];
    expect(mergeLayout(panels, null)).toEqual([{ id: 'a', span: 2, rows: 2, hidden: false }]);
  });

  it('honors a saved height and clamps one the panel no longer allows', () => {
    const panels = [{ id: 'a' }, { id: 'b', rowSizes: [1] }];
    const merged = mergeLayout(panels, [{ id: 'a', rows: 4 }, { id: 'b', rows: 3 }]);
    expect(merged[0].rows).toBe(4);
    expect(merged[1].rows).toBe(1); // 'b' is pinned to one row unit
  });

  it('uses the panel default height when nothing is saved', () => {
    const panels = [{ id: 'a', rows: 3 }, { id: 'b' }];
    const merged = mergeLayout(panels, null);
    expect(merged[0].rows).toBe(3);
    expect(merged[1].rows).toBe(2); // engine default
  });

  it('rejects an out-of-range saved height', () => {
    expect(mergeLayout([{ id: 'a' }], [{ id: 'a', rows: 99 }])[0].rows).toBe(2);
  });

  it('ignores junk entries', () => {
    expect(ids(mergeLayout(PANELS, [null, 42, { nope: true }, { id: 'b' }])))
      .toEqual(['b', 'a', 'c']);
  });

  it('upgrades a v1 bare-id layout in place', () => {
    // Layouts saved before size classes existed were plain strings.
    const merged = mergeLayout(PANELS, ['c', 'b', 'a']);
    expect(merged).toEqual([
      { id: 'c', span: 1, rows: 2, hidden: false },
      { id: 'b', span: 1, rows: 2, hidden: false },
      { id: 'a', span: 1, rows: 2, hidden: false },
    ]);
  });

  it('is safe on an empty canonical set', () => {
    expect(mergeLayout([], [{ id: 'a' }])).toEqual([]);
    expect(mergeLayout(undefined, undefined)).toEqual([]);
  });
});
