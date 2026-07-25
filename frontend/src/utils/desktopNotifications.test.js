import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
    PREF_KEY,
    isSupported,
    getPermission,
    getPreference,
    setPreference,
    shouldShowDesktop,
    pickNewNotifications,
    buildDesktopPayload,
    navigateForNotification,
} from './desktopNotifications.js';

/** In-memory localStorage stub — vitest may ship a non-functional localStorage. */
function installMemoryLocalStorage() {
    const store = new Map();
    const mem = {
        getItem: (k) => (store.has(k) ? store.get(k) : null),
        setItem: (k, v) => { store.set(String(k), String(v)); },
        removeItem: (k) => { store.delete(k); },
        clear: () => { store.clear(); },
    };
    vi.stubGlobal('localStorage', mem);
    return mem;
}

describe('desktopNotifications preference', () => {
    let mem;

    beforeEach(() => {
        mem = installMemoryLocalStorage();
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('defaults to off', () => {
        expect(getPreference()).toBe('off');
    });

    it('persists on/off', () => {
        setPreference(true);
        expect(mem.getItem(PREF_KEY)).toBe('on');
        expect(getPreference()).toBe('on');
        setPreference(false);
        expect(getPreference()).toBe('off');
    });
});

describe('shouldShowDesktop', () => {
    it('requires granted + preference on', () => {
        expect(shouldShowDesktop({
            permission: 'granted',
            preference: 'on',
        })).toBe(true);
    });

    it('is false when preference off', () => {
        expect(shouldShowDesktop({
            permission: 'granted',
            preference: 'off',
        })).toBe(false);
    });

    it('is false when permission not granted', () => {
        expect(shouldShowDesktop({
            permission: 'default',
            preference: 'on',
        })).toBe(false);
        expect(shouldShowDesktop({
            permission: 'denied',
            preference: 'on',
        })).toBe(false);
    });
});

describe('pickNewNotifications', () => {
    const list = [
        { id: 10, is_read: false, message: 'newest' },
        { id: 9, is_read: true, message: 'read' },
        { id: 8, is_read: false, message: 'mid' },
        { id: 7, is_read: false, message: 'old' },
    ];

    it('returns only unread with id > lastSeenId', () => {
        const { items, overflow } = pickNewNotifications(list, 7);
        expect(items.map((n) => n.id)).toEqual([10, 8]);
        expect(overflow).toBe(0);
    });

    it('with null lastSeenId treats all unread as candidates', () => {
        const { items } = pickNewNotifications(list, null);
        expect(items.map((n) => n.id)).toEqual([10, 8, 7]);
    });

    it('caps detail banners and reports overflow', () => {
        const many = Array.from({ length: 8 }, (_, i) => ({
            id: 100 - i,
            is_read: false,
        }));
        const { items, overflow } = pickNewNotifications(many, 0, 5);
        expect(items).toHaveLength(5);
        expect(overflow).toBe(3);
        expect(items[0].id).toBe(100);
    });
});

describe('buildDesktopPayload', () => {
    it('labels mentions', () => {
        const p = buildDesktopPayload({ type: 'mention', message: 'Bill mentioned you' });
        expect(p.title).toBe('Mention');
        expect(p.body).toContain('Bill mentioned you');
    });

    it('labels to-dos', () => {
        const p = buildDesktopPayload({ type: 'checklist_assigned', message: 'New to-do: Order bolts' });
        expect(p.title).toBe('To-do');
    });

    it('appends board title when present', () => {
        const p = buildDesktopPayload({
            type: 'mention',
            message: 'Bill mentioned you',
            board_item_title: 'Fix fab order',
        });
        expect(p.body).toContain('Fix fab order');
    });
});

describe('navigateForNotification', () => {
    it('routes board items', () => {
        const navigate = vi.fn();
        navigateForNotification({ board_item_id: 42 }, navigate);
        expect(navigate).toHaveBeenCalledWith('/board', { state: { openItemId: 42 } });
    });

    it('routes submittals to DWL', () => {
        const navigate = vi.fn();
        navigateForNotification({ submittal_id: 'abc' }, navigate);
        expect(navigate).toHaveBeenCalledWith('/drafting-work-load?highlight=abc');
    });

    it('routes drawing comments and bb_review to job-log', () => {
        const navigate = vi.fn();
        navigateForNotification({
            drawing_version_comment_id: 1,
            release_id: 9,
            drawing_version_id: 3,
            release_job_number: 480,
            release_number: 2,
        }, navigate);
        expect(navigate).toHaveBeenCalledWith('/job-log', {
            state: {
                openDrawing: {
                    releaseId: 9,
                    versionId: 3,
                    jobReleaseLabel: '480-2',
                },
            },
        });

        navigate.mockClear();
        navigateForNotification({
            bb_drawing_review_id: 5,
            release_id: 9,
            drawing_version_id: 3,
        }, navigate);
        expect(navigate).toHaveBeenCalledWith('/job-log', expect.any(Object));
    });

    it('routes checklist types to /todos', () => {
        const navigate = vi.fn();
        navigateForNotification({ checklist_item_id: 1 }, navigate);
        expect(navigate).toHaveBeenCalledWith('/todos');

        navigate.mockClear();
        navigateForNotification({ type: 'checklist_ready' }, navigate);
        expect(navigate).toHaveBeenCalledWith('/todos');
    });
});

describe('isSupported / getPermission with mocks', () => {
    const originalNotification = globalThis.Notification;

    afterEach(() => {
        if (originalNotification === undefined) {
            // eslint-disable-next-line no-global-assign
            delete globalThis.Notification;
        } else {
            globalThis.Notification = originalNotification;
        }
    });

    it('isSupported follows Notification presence', () => {
        globalThis.Notification = class {};
        expect(isSupported()).toBe(true);
        // eslint-disable-next-line no-global-assign
        delete globalThis.Notification;
        expect(isSupported()).toBe(false);
    });

    it('getPermission reads Notification.permission', () => {
        globalThis.Notification = { permission: 'granted' };
        expect(getPermission()).toBe('granted');
    });
});
