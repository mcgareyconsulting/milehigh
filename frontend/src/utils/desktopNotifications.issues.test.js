import { describe, it, expect, vi } from 'vitest';
import { navigateForNotification } from './desktopNotifications.js';

describe('navigateForNotification — release issue mentions', () => {
    it('opens the Job Log hub on the mentioned issue', () => {
        const navigate = vi.fn();
        navigateForNotification({ release_issue_id: 7, release_id: 55, release_issue_comment_id: 3 }, navigate);
        expect(navigate).toHaveBeenCalledWith('/job-log', {
            state: { openIssue: { releaseId: 55, issueId: 7 } },
        });
    });

    it('takes the issue route even though the notification also carries a release_id', () => {
        const navigate = vi.fn();
        navigateForNotification({ release_issue_id: 7, release_id: 55 }, navigate);
        expect(navigate).toHaveBeenCalledTimes(1);
        expect(navigate.mock.calls[0][1].state.openDrawing).toBeUndefined();
    });
});
