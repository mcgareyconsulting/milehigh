import { describe, it, expect } from 'vitest';
import { buildTimeline, groupByDay, dayBucket } from './ReleaseNotesRail.jsx';

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
    // Standalone fab (different minute from any stage).
    {
        id: 5,
        action: 'update_fab_order',
        user_name: 'Admin',
        created_at: '2026-07-15T09:10:00',
        payload: { from: 1, to: 2 },
    },
];

describe('buildTimeline', () => {
    it('intermingles notes, stage, ship, and fab newest-first', () => {
        const items = buildTimeline(EVENTS, { currentNotes: 'Waiting on GC' });
        // Newest-first: note 7/19, stage 7/18, ship 7/17, fab 7/15, note 7/2.
        expect(items.map((i) => i.kind)).toEqual(['note', 'stage', 'date', 'fab', 'note']);
        expect(items[0].body).toBe('Waiting on GC');
        expect(items[0].current).toBeUndefined();
        expect(items[1].kind).toBe('stage');
        expect(items[1].from).toBe('Cut Start');
        expect(items[1].to).toBe('Cut Complete');
        expect(items[2].kind).toBe('date');
        expect(items[2].valueLabel).toMatch(/Jul 28/);
        expect(items[3].kind).toBe('fab');
        expect(items[3].from).toBe(1);
        expect(items[3].to).toBe(2);
    });

    it('drops no-ops', () => {
        const items = buildTimeline(EVENTS);
        expect(items.find((i) => i.id === 6)).toBeUndefined();
    });

    it('merges same-user same-minute fab into stage', () => {
        const raw = [
            {
                id: 20,
                action: 'update_stage',
                user_name: 'David Servold',
                created_at: '2026-04-16T07:00:10',
                payload: { from: 'Paint complete', to: 'Shipping completed' },
            },
            {
                id: 21,
                action: 'update_fab_order',
                user_name: 'David Servold',
                created_at: '2026-04-16T07:00:40',
                payload: { from: 3, to: 1 },
            },
        ];
        const items = buildTimeline(raw);
        expect(items).toHaveLength(1);
        expect(items[0].kind).toBe('stage');
        expect(items[0].alsoFab).toEqual({ from: 3, to: 1 });
    });

    it('does not merge fab from a different user or minute', () => {
        const raw = [
            {
                id: 20,
                action: 'update_stage',
                user_name: 'David Servold',
                created_at: '2026-04-16T07:00:10',
                payload: { from: 'A', to: 'B' },
            },
            {
                id: 21,
                action: 'update_fab_order',
                user_name: 'Someone Else',
                created_at: '2026-04-16T07:00:40',
                payload: { from: 3, to: 1 },
            },
            {
                id: 22,
                action: 'update_fab_order',
                user_name: 'David Servold',
                created_at: '2026-04-16T08:00:00',
                payload: { from: 5, to: 4 },
            },
        ];
        const items = buildTimeline(raw);
        expect(items.filter((i) => i.kind === 'stage')).toHaveLength(1);
        expect(items.find((i) => i.kind === 'stage').alsoFab).toBeUndefined();
        expect(items.filter((i) => i.kind === 'fab')).toHaveLength(2);
    });

    it('surfaces the current field note when it is not in the event window', () => {
        const items = buildTimeline([], { currentNotes: 'Orphan note on the cell' });
        expect(items).toHaveLength(1);
        expect(items[0].body).toBe('Orphan note on the cell');
        expect(items[0].current).toBeUndefined();
    });

    it('backfills prior note text from payload.from when it has no own event', () => {
        // One overwrite only: previous body lived only in `from` (user's screenshot case).
        const raw = [
            {
                id: 99,
                action: 'update_notes',
                user_name: 'Daniel McGarey',
                created_at: '2026-08-08T16:42:00',
                payload: { from: 'Need clevis rods painted', to: 'Test' },
            },
        ];
        const items = buildTimeline(raw, { currentNotes: 'Test' });
        const noteBodies = items.filter((i) => i.kind === 'note').map((i) => i.body);
        expect(noteBodies).toEqual(['Test', 'Need clevis rods painted']);
        expect(items.find((i) => i.body === 'Need clevis rods painted').prior).toBe(true);
    });

    it('does not duplicate prior text already recorded as an older note event to', () => {
        const raw = [
            {
                id: 10,
                action: 'update_notes',
                user_name: 'Dave',
                created_at: '2026-07-19T12:00:00',
                payload: { from: 'Fab has pack', to: 'Waiting on GC' },
            },
            {
                id: 7,
                action: 'update_notes',
                user_name: 'Ryan',
                created_at: '2026-07-02T09:00:00',
                payload: { from: '', to: 'Fab has pack' },
            },
        ];
        const items = buildTimeline(raw);
        const noteBodies = items.filter((i) => i.kind === 'note').map((i) => i.body);
        // Both tos only — no synthetic "Fab has pack" from id 10's from.
        expect(noteBodies).toEqual(['Waiting on GC', 'Fab has pack']);
        expect(items.filter((i) => i.prior)).toHaveLength(0);
    });
});

describe('groupByDay / dayBucket', () => {
    it('formats day labels like TUE · APR 7', () => {
        // Local date constructor avoids UTC off-by-one.
        const d = new Date(2026, 3, 7, 8, 28); // Apr 7 2026
        const { label } = dayBucket(d.toISOString());
        expect(label).toMatch(/^[A-Z]{3} · [A-Z]{3} \d{1,2}$/);
        expect(label).toContain('APR');
        expect(label).toContain('7');
    });

    it('groups items under day dividers newest-first within build order', () => {
        const items = buildTimeline(EVENTS);
        const groups = groupByDay(items);
        expect(groups.length).toBeGreaterThanOrEqual(2);
        // First group's first item is the newest overall.
        expect(groups[0].items[0].id).toBe(items[0].id);
    });
});
