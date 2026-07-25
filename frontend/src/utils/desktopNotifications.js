/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Chrome desktop Notification API helpers for opted-in users. Poll-driven only — requires Brain tab open (may be backgrounded). No Web Push.
 * exports:
 *   PREF_KEY, DESKTOP_ICON, isSupported, getPermission, getPreference, setPreference,
 *   requestPermission, shouldShowDesktop, showDesktopNotification,
 *   pickNewNotifications, buildDesktopPayload, navigateForNotification
 * imports_from: []
 * imported_by: [components/NotificationBell.jsx]
 * invariants:
 *   - requestPermission must only run from a user gesture (button click).
 *   - First-poll historical unread must not desktop-spam (caller skips first tick).
 *   - Opt-in requires BOTH Chrome permission === 'granted' AND localStorage preference 'on'.
 */

export const PREF_KEY = 'mhmw-desktop-notifications';
export const MAX_DESKTOP_BANNERS = 5;
/** Same banana mark as the browser favicon / FloatingBananas. */
export const DESKTOP_ICON = '/bananas-svgrepo-com.svg';

export function isSupported() {
    return typeof window !== 'undefined' && 'Notification' in window;
}

export function getPermission() {
    if (!isSupported()) return 'unsupported';
    return Notification.permission; // 'default' | 'granted' | 'denied'
}

/** @returns {'on' | 'off'} */
export function getPreference() {
    try {
        return localStorage.getItem(PREF_KEY) === 'on' ? 'on' : 'off';
    } catch {
        return 'off';
    }
}

export function setPreference(enabled) {
    try {
        localStorage.setItem(PREF_KEY, enabled ? 'on' : 'off');
    } catch {
        /* private mode / blocked storage — ignore */
    }
}

/**
 * Ask Chrome for notification permission. Call only from a click handler.
 * @returns {Promise<'granted' | 'denied' | 'default' | 'unsupported'>}
 */
export async function requestPermission() {
    if (!isSupported()) return 'unsupported';
    try {
        const result = await Notification.requestPermission();
        return result;
    } catch {
        return 'denied';
    }
}

/**
 * Whether we should fire OS desktop banners for newly arrived items.
 * Requires Chrome permission + in-app preference. Does NOT require the tab
 * to be hidden — OS banners fire even while Brain is focused (alongside toast).
 *
 * @param {{ permission?: string, preference?: 'on'|'off' }} [opts]
 */
export function shouldShowDesktop(opts = {}) {
    const permission = opts.permission ?? getPermission();
    const preference = opts.preference ?? getPreference();

    if (permission !== 'granted') return false;
    if (preference !== 'on') return false;
    return true;
}

/**
 * From a full notification list + last seen id, return newest unread items to banner.
 * Items are assumed ordered newest-first (API order).
 *
 * @param {Array<{ id: number, is_read?: boolean }>} notifications
 * @param {number|null} lastSeenId - highest id already considered; null = treat none as new
 * @param {number} [maxDetail=MAX_DESKTOP_BANNERS]
 * @returns {{ items: typeof notifications, overflow: number }}
 */
export function pickNewNotifications(notifications, lastSeenId, maxDetail = MAX_DESKTOP_BANNERS) {
    const floor = lastSeenId == null ? -Infinity : lastSeenId;
    const fresh = (notifications || []).filter(
        (n) => !n.is_read && typeof n.id === 'number' && n.id > floor,
    );
    // API is newest-first; keep that order for banners.
    const overflow = Math.max(0, fresh.length - maxDetail);
    const items = overflow > 0 ? fresh.slice(0, maxDetail) : fresh;
    return { items, overflow };
}

/**
 * Build title/body for a Notification row.
 * @param {{ type?: string, message?: string, board_item_title?: string }} notif
 */
export function buildDesktopPayload(notif) {
    const message = (notif.message || 'New notification').trim();
    let title = 'MHMW Brain';
    const type = notif.type || '';

    if (type === 'mention' || type === 'dwl_mention') {
        title = 'Mention';
    } else if (type.startsWith('checklist_')) {
        title = 'To-do';
    } else if (type === 'bb_review') {
        title = 'Drawing review';
    }

    let body = message;
    if (notif.board_item_title) {
        body = `${message} — ${notif.board_item_title}`;
    } else if (notif.submittal_title || notif.submittal_project_name) {
        const bits = [
            notif.submittal_project_number,
            notif.submittal_project_name,
            notif.submittal_title,
        ].filter(Boolean);
        if (bits.length) body = `${message} — ${bits.join(' · ')}`;
    } else if (notif.release_job_number != null && notif.release_number != null) {
        body = `${message} — ${notif.release_job_number}-${notif.release_number}`;
    }

    return { title, body };
}

/**
 * Show one OS notification. Returns the Notification instance or null.
 * onclick is attached by the caller (needs navigate/mark-read).
 */
export function showDesktopNotification({ id, title, body, data }) {
    if (!isSupported() || Notification.permission !== 'granted') return null;
    try {
        // Absolute URL so the OS notification process can load the banana off the page origin.
        const icon = typeof window !== 'undefined'
            ? new URL(DESKTOP_ICON, window.location.origin).href
            : DESKTOP_ICON;
        const n = new Notification(title, {
            body: body || '',
            tag: id != null ? `notif-${id}` : undefined,
            icon,
            data: data || { id },
        });
        return n;
    } catch (err) {
        // Surface in devtools — silent catch made failures invisible.
        console.warn('desktop_notification_failed', err);
        return null;
    }
}

/**
 * Shared deep-link routing for bell list clicks and desktop banner clicks.
 * @param {object} notif
 * @param {(path: string, opts?: object) => void} navigate - react-router navigate
 */
export function navigateForNotification(notif, navigate) {
    if (!notif || !navigate) return;

    if (notif.board_item_id) {
        navigate('/board', { state: { openItemId: notif.board_item_id } });
        return;
    }
    if (notif.submittal_id) {
        navigate(`/drafting-work-load?highlight=${encodeURIComponent(notif.submittal_id)}`);
        return;
    }
    if (notif.drawing_version_comment_id || notif.bb_drawing_review_id) {
        navigate('/job-log', {
            state: {
                openDrawing: {
                    releaseId: notif.release_id,
                    versionId: notif.drawing_version_id,
                    jobReleaseLabel: notif.release_job_number != null
                        ? `${notif.release_job_number}-${notif.release_number}`
                        : null,
                },
            },
        });
        return;
    }
    if (notif.checklist_item_id || (notif.type && String(notif.type).startsWith('checklist_'))) {
        navigate('/todos');
    }
}
