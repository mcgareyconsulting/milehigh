import { describe, it, expect } from 'vitest';
import { buildTimeline } from './ReleaseNotesRail.jsx';

// Sentence events (photos, drawings, issues) used to route through the date row, which
// appended " cleared" to every one of them. They now get their own `sentence` kind.
describe('buildTimeline sentence events', () => {
    const events = [
        {
            id: 3,
            action: 'create_issue',
            user_name: 'Ada Admin',
            created_at: 'September 15, 2026 02:30:45 PM',
            payload: { from: null, to: { display_id: '290-153-I1', title: 'Bent', department: 'Fab', priority: 'High' } },
        },
        {
            id: 2,
            action: 'upload_photo',
            user_name: 'Dave Cruz',
            created_at: 'September 14, 2026 09:00:00 AM',
            payload: { from: null, to: { photo_id: 4, filename: 'weld.jpg' } },
        },
    ];

    const items = buildTimeline(events).filter((i) => i.kind !== 'note');

    it('emits a sentence item for issue and photo events', () => {
        expect(items.map((i) => i.kind)).toEqual(['sentence', 'sentence']);
    });

    it('carries the summary text without a "cleared" suffix', () => {
        const byId = Object.fromEntries(items.map((i) => [i.id, i]));
        expect(byId[3].text).toBe('Issue opened — 290-153-I1 “Bent” (Fab · High)');
        expect(byId[3].author).toBe('Ada Admin');
        expect(byId[2].text).toBe('Photo added — weld.jpg');
        for (const item of items) expect(item.text).not.toMatch(/cleared$/);
    });
});
