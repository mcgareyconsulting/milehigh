import { describe, it, expect } from 'vitest';
import {
    ACTIVITY_ACTIONS,
    ISSUE_ACTIONS,
    issueEventSummary,
    summarizeActivity,
} from './ReleaseActivityFeed.jsx';

const issueTo = { issue_id: 7, display_id: '290-153-I1', title: 'Bent stair stringer' };

describe('issueEventSummary', () => {
    it('describes an opened issue with department and priority', () => {
        expect(issueEventSummary({
            action: 'create_issue',
            payload: { from: null, to: { ...issueTo, department: 'Fab', priority: 'High' } },
        })).toBe('Issue opened — 290-153-I1 “Bent stair stringer” (Fab · High)');
    });

    it('describes field changes, formatting cost and hiding description text', () => {
        const text = issueEventSummary({
            action: 'update_issue',
            payload: {
                from: null,
                to: {
                    ...issueTo,
                    changes: [
                        { field: 'status', from: 'Open', to: 'In Progress' },
                        { field: 'estimated_cost', from: null, to: '1200.00' },
                        { field: 'description', from: null, to: null },
                    ],
                },
            },
        });
        expect(text).toBe(
            'Issue 290-153-I1 “Bent stair stringer” — status Open → In Progress; '
            + 'estimated cost Unknown/TBD → $1,200.00; description edited',
        );
    });

    it('describes evidence added, with and without a filename', () => {
        expect(issueEventSummary({
            action: 'add_issue_attachment',
            payload: { from: null, to: { ...issueTo, filename: 'IMG_0412.jpg' } },
        })).toBe('Evidence added to issue 290-153-I1 “Bent stair stringer” — IMG_0412.jpg');

        expect(issueEventSummary({
            action: 'add_issue_attachment',
            payload: { from: null, to: { ...issueTo, filename: null } },
        })).toBe('Evidence added to issue 290-153-I1 “Bent stair stringer”');
    });

    it('returns null for non-issue actions', () => {
        expect(issueEventSummary({ action: 'update_stage', payload: { from: 'a', to: 'b' } })).toBeNull();
    });
});

describe('issue actions in the Activity rail', () => {
    it('are all members of ACTIVITY_ACTIONS', () => {
        for (const action of ISSUE_ACTIONS) expect(ACTIVITY_ACTIONS.has(action)).toBe(true);
    });

    it('flow through summarizeActivity with the author', () => {
        expect(summarizeActivity({
            action: 'create_issue',
            user_name: 'Ada Admin',
            payload: { from: null, to: { ...issueTo, department: 'Paint', priority: 'Low' } },
        })).toEqual({
            text: 'Issue opened — 290-153-I1 “Bent stair stringer” (Paint · Low)',
            author: 'Ada Admin',
        });
    });
});
