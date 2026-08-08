import { describe, it, expect } from 'vitest';
import { buildTimeline } from './ReleaseNotesRail.jsx';

const EVENTS = [
    {
        id: 10,
        action: 'update_notes',
        user_name: 'Dave Cruz',
        created_at: '2026-07-19T12:46:16',
        payload: { from: 'Fab has pack', to: 'Waiting on GC' },
    },
    {
        id: 9,
        action: 'update_stage',
        user_name: 'Ryan Lopez',
        created_at: '2026-07-18T09:10:00',
        payload: { from: 'Cut Start', to: 'Cut Complete' },
    },
    {
        id: 8,
        action: 'update_ship_date',
        user_name: 'Dave Cruz',
        created_at: '2026-07-17T11:00:00',
        payload: { from: null, to: '2026-07-28' },
    },
    {
        id: 7,
        action: 'update_notes',
        user_name: 'Ryan Lopez',
        created_at: '2026-07-02T09:10:00',
        payload: { from: '', to: 'Fab has pack' },
    },
    // No-op stage — must be dropped.
    {
        id: 6,
        action: 'update_stage',
        user_name: 'Ryan Lopez',
        created_at: '2026-07-16T09:10:00',
        payload: { from: 'Cut Start', to: 'Cut Start' },
    },
    // Fab order — not in the mixed feed.
    {
        id: 5,
        action: 'update_fab_order',
        user_name: 'Admin',
        created_at: '2026-07-15T09:10:00',
        payload: { from: 1, to: 2 },
    },
];

describe('buildTimeline', () => {
    it('intermingles notes and date/stage updates newest-first', () => {
        const items = buildTimeline(EVENTS, { currentNotes: 'Waiting on GC' });
        expect(items.map((i) => i.kind)).toEqual(['note', 'update', 'update', 'note']);
        expect(items[0].body).toBe('Waiting on GC');
        expect(items[0].current).toBe(true);
        expect(items[1].text).toBe('Stage Cut Start → Cut Complete');
        expect(items[2].updateKind).toBe('Ship');
        expect(items[3].body).toBe('Fab has pack');
    });

    it('drops no-ops and non-activity actions', () => {
        const items = buildTimeline(EVENTS);
        expect(items.find((i) => i.id === 6)).toBeUndefined();
        expect(items.find((i) => i.id === 5)).toBeUndefined();
    });

    it('surfaces the current field note when it is not in the event window', () => {
        const items = buildTimeline([], { currentNotes: 'Orphan note on the cell' });
        expect(items).toHaveLength(1);
        expect(items[0].body).toBe('Orphan note on the cell');
        expect(items[0].current).toBe(true);
    });
});
