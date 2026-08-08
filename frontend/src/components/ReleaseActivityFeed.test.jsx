import { describe, it, expect } from 'vitest';
import { summarizeActivity, ACTIVITY_ACTIONS } from './ReleaseActivityFeed.jsx';

describe('summarizeActivity', () => {
    it('formats stage transitions with from → to', () => {
        const s = summarizeActivity({
            action: 'update_stage',
            user_name: 'Ryan',
            payload: { from: 'Cut Start', to: 'Cut Complete' },
        });
        expect(s).toEqual({ text: 'Stage Cut Start → Cut Complete', author: 'Ryan' });
    });

    it('formats ship date sets and clears', () => {
        expect(summarizeActivity({
            action: 'update_ship_date',
            user_name: 'Dave',
            payload: { from: null, to: '2026-07-28' },
        }).text).toBe('Ship date set to Jul 28, 2026');

        expect(summarizeActivity({
            action: 'update_ship_date',
            user_name: 'Dave',
            payload: { from: '2026-07-28', to: null },
        }).text).toBe('Ship date cleared');
    });

    it('formats start install hard dates and ASAP', () => {
        expect(summarizeActivity({
            action: 'update_start_install',
            user_name: 'Doug',
            payload: { from: null, to: '2026-08-01' },
        }).text).toBe('Start install set to Aug 1, 2026');

        expect(summarizeActivity({
            action: 'update_start_install',
            user_name: 'Doug',
            payload: { from: null, to: null, asap: true },
        }).text).toBe('Start install set to ASAP');
    });

    it('falls back to source when no user_name', () => {
        const s = summarizeActivity({
            action: 'update_stage',
            source: 'Trello',
            payload: { to: 'Paint Start' },
        });
        expect(s.author).toBe('Trello');
    });

    it('only treats date + stage actions as feed material', () => {
        expect(ACTIVITY_ACTIONS.has('update_notes')).toBe(false);
        expect(ACTIVITY_ACTIONS.has('update_fab_order')).toBe(false);
        expect(ACTIVITY_ACTIONS.has('update_stage')).toBe(true);
        expect(ACTIVITY_ACTIONS.has('update_ship_date')).toBe(true);
        expect(ACTIVITY_ACTIONS.has('update_start_install')).toBe(true);
        expect(ACTIVITY_ACTIONS.has('clear_hard_date')).toBe(true);
    });
});
