/**
 * @milehigh-header
 * schema_version: 1
 * purpose: In-app notification bell with 30s polling, toast popups on new mentions, opt-in Chrome desktop banners, and click-through to board/DWL/drawings/todos.
 * exports:
 *   NotificationBell: Default export — renders bell icon with unread badge, dropdown list, desktop opt-in, and toast stack
 * imports_from: [react, react-dom, react-router-dom, ../services/notificationApi, ../utils/desktopNotifications]
 * imported_by: [frontend/src/components/AppShell.jsx]
 * invariants:
 *   - Polls /brain/notifications/unread-count every 30 seconds; pauses are NOT visibility-gated (runs even in background tabs).
 *   - Toast auto-dismisses after 5s with a 300ms exit animation — changing timing requires matching CSS animation duration.
 *   - Desktop Notification.requestPermission only runs from the opt-in button (user gesture).
 *   - First poll never fires toast or desktop banners for historical unread — only count increases after load.
 *   - Desktop banners require Chrome permission + localStorage preference; fire on new arrivals even if tab is focused.
 *   - Rail variant portals the panel to document.body (rail has overflow:hidden + sticky ancestors);
 *     in-tree fixed positioning is clipped and stacks under the rail chrome.
 *   - Pod variant uses the in-tree absolute right-0 panel (same as topbar); mount it over the content
 *     corner — AppShell main when Left Sidebar Mode is on. Zero unread collapses to a plain bell pill.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { fetchNotifications, fetchUnreadCount, markNotificationRead, markAllRead } from '../services/notificationApi';
import {
    isSupported,
    getPermission,
    getPreference,
    setPreference,
    requestPermission,
    shouldShowDesktop,
    pickNewNotifications,
    buildDesktopPayload,
    showDesktopNotification,
    navigateForNotification,
} from '../utils/desktopNotifications';

/** Preferred panel height; actual max is clamped to remaining viewport space. */
const PANEL_W = 384; // w-96
const PANEL_MAX_H = 384; // max-h-96
const PANEL_GAP = 6;
const VIEWPORT_PAD = 8;

function timeAgo(dateStr) {
    const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
    if (seconds < 60) return 'just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

const BELL_ICON_PATH = "M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9";

/** Strip the embedded title from old-format messages when board_item_title is available. */
function getActionText(message, boardItemTitle) {
    if (!boardItemTitle) return message;
    return message.replace(/ in ".*"$/, '');
}

/**
 * @param variant 'topbar' (default) renders the round icon button the top bar
 *   has always used. 'rail' renders a full-width left-rail row and portals the
 *   dropdown to a fixed position beside the rail. 'pod' renders a floating
 *   pill intended to be absolutely positioned over the top-right corner of the
 *   content area — the in-tree `absolute right-0` panel is correct there.
 */
export default function NotificationBell({
    variant = 'topbar',
    expanded = false,
    itemHeight = 37,
    railWidth = 52,
    onHoverLabel = null,
    onLeaveLabel = null,
}) {
    const [unreadCount, setUnreadCount] = useState(0);
    const [notifications, setNotifications] = useState([]);
    const [open, setOpen] = useState(false);
    /** Rail panel placement: { left, top, maxHeight } in viewport coords. */
    const [railPanelPos, setRailPanelPos] = useState(null);
    const [loading, setLoading] = useState(false);
    const [toasts, setToasts] = useState([]);
    // Desktop opt-in UI state (re-read after enable/disable clicks)
    const [desktopPref, setDesktopPref] = useState(() => getPreference());
    const [desktopPerm, setDesktopPerm] = useState(() => getPermission());
    const [desktopBusy, setDesktopBusy] = useState(false);

    const prevUnreadRef = useRef(null);
    const lastSeenNotifIdRef = useRef(null);
    const ref = useRef(null);
    const panelRef = useRef(null);
    const navigate = useNavigate();

    const placeRailPanel = useCallback(() => {
        if (!ref.current) return;
        const rect = ref.current.getBoundingClientRect();
        const left = Math.max(VIEWPORT_PAD, railWidth + PANEL_GAP);
        const spaceBelow = window.innerHeight - rect.top - VIEWPORT_PAD;
        const spaceAbove = rect.bottom - VIEWPORT_PAD;
        // Prefer aligning to the trigger top (opens downward). If that leaves
        // less than half the preferred height, flip so the panel sits above.
        let top = rect.top;
        let maxHeight = Math.min(PANEL_MAX_H, spaceBelow);
        if (maxHeight < PANEL_MAX_H * 0.5 && spaceAbove > spaceBelow) {
            maxHeight = Math.min(PANEL_MAX_H, spaceAbove);
            top = Math.max(VIEWPORT_PAD, rect.bottom - maxHeight);
        } else {
            // Still clamp if the panel would extend past the bottom.
            if (top + maxHeight > window.innerHeight - VIEWPORT_PAD) {
                top = Math.max(VIEWPORT_PAD, window.innerHeight - VIEWPORT_PAD - maxHeight);
            }
        }
        setRailPanelPos({ left, top, maxHeight: Math.max(160, maxHeight) });
    }, [railWidth]);

    const refreshDesktopState = useCallback(() => {
        setDesktopPref(getPreference());
        setDesktopPerm(getPermission());
    }, []);

    const openFromDesktop = useCallback(async (notif) => {
        try {
            window.focus();
        } catch { /* ignore */ }
        if (notif?.id && !notif.is_read) {
            try {
                await markNotificationRead(notif.id);
                setUnreadCount((c) => Math.max(0, c - 1));
            } catch { /* ignore */ }
        }
        navigateForNotification(notif, navigate);
    }, [navigate]);

    const fireDesktopForNew = useCallback(async () => {
        if (!shouldShowDesktop()) return;
        // Wait until first poll has baselined existing unread — avoid historical spam.
        if (lastSeenNotifIdRef.current == null) return;
        try {
            const data = await fetchNotifications();
            const list = data.notifications || [];
            const { items, overflow } = pickNewNotifications(list, lastSeenNotifIdRef.current);

            if (list.length) {
                const maxId = Math.max(...list.map((n) => n.id).filter((id) => typeof id === 'number'));
                if (Number.isFinite(maxId)) {
                    lastSeenNotifIdRef.current = Math.max(lastSeenNotifIdRef.current, maxId);
                }
            }

            if (!items.length && overflow === 0) return;

            if (overflow > 0) {
                // Cap: one summary banner when a burst arrives.
                const total = items.length + overflow;
                const n = showDesktopNotification({
                    id: `burst-${Date.now()}`,
                    title: 'MHMW Brain',
                    body: `${total} new notifications`,
                });
                if (n) {
                    n.onclick = () => {
                        n.close();
                        try { window.focus(); } catch { /* ignore */ }
                    };
                }
            } else {
                for (const notif of items) {
                    const { title, body } = buildDesktopPayload(notif);
                    const n = showDesktopNotification({
                        id: notif.id,
                        title,
                        body,
                        data: notif,
                    });
                    if (n) {
                        n.onclick = () => {
                            n.close();
                            openFromDesktop(notif);
                        };
                    }
                }
            }
        } catch { /* ignore fetch errors */ }
    }, [openFromDesktop]);

    // Poll unread count — 30s interval, toast + desktop on increase
    useEffect(() => {
        let mounted = true;
        const poll = async () => {
            try {
                const count = await fetchUnreadCount();
                if (!mounted) return;

                // Baseline existing ids so we never desktop-spam historical unread.
                if (lastSeenNotifIdRef.current == null) {
                    try {
                        const data = await fetchNotifications();
                        if (!mounted) return;
                        const ids = (data.notifications || [])
                            .map((n) => n.id)
                            .filter((id) => typeof id === 'number');
                        lastSeenNotifIdRef.current = ids.length ? Math.max(...ids) : 0;
                    } catch {
                        // Leave null — desktop path no-ops until a successful baseline.
                    }
                }

                // Show toast / desktop when count increases (skip first poll)
                if (prevUnreadRef.current !== null && count > prevUnreadRef.current) {
                    const newCount = count - prevUnreadRef.current;
                    const toastId = Date.now();
                    setToasts((prev) => [...prev, {
                        id: toastId,
                        text: `${newCount} new notification${newCount > 1 ? 's' : ''}`,
                        exiting: false,
                    }]);
                    setTimeout(() => {
                        if (!mounted) return;
                        setToasts((prev) => prev.map((t) => t.id === toastId ? { ...t, exiting: true } : t));
                        setTimeout(() => {
                            if (!mounted) return;
                            setToasts((prev) => prev.filter((t) => t.id !== toastId));
                        }, 300);
                    }, 5000);

                    // Desktop banners when opted in (Chrome permission + in-app preference)
                    fireDesktopForNew();
                }
                prevUnreadRef.current = count;
                setUnreadCount(count);
            } catch { /* ignore auth errors */ }
        };
        poll();
        const interval = setInterval(poll, 30000);
        return () => { mounted = false; clearInterval(interval); };
    }, [fireDesktopForNew]);

    // Close on outside click — panel may be portaled outside `ref`.
    useEffect(() => {
        if (!open) return undefined;
        const handler = (e) => {
            const t = e.target;
            if (ref.current?.contains(t)) return;
            if (panelRef.current?.contains(t)) return;
            setOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    // Keep rail panel beside the bell on resize/scroll while open.
    useEffect(() => {
        if (!open || variant !== 'rail') return undefined;
        placeRailPanel();
        const onMove = () => placeRailPanel();
        window.addEventListener('resize', onMove);
        // Capture scroll on any scrollable ancestor (job log table, etc.).
        window.addEventListener('scroll', onMove, true);
        return () => {
            window.removeEventListener('resize', onMove);
            window.removeEventListener('scroll', onMove, true);
        };
    }, [open, variant, placeRailPanel, expanded, railWidth]);

    const handleOpen = async () => {
        if (open) { setOpen(false); return; }
        if (variant === 'rail') placeRailPanel();
        setOpen(true);
        refreshDesktopState();
        setLoading(true);
        try {
            const data = await fetchNotifications();
            setNotifications(data.notifications);
            setUnreadCount(data.unread_count);
        } catch { /* ignore */ }
        setLoading(false);
    };

    const handleClick = async (notif) => {
        if (!notif.is_read) {
            await markNotificationRead(notif.id);
            setNotifications((prev) => prev.map((n) => n.id === notif.id ? { ...n, is_read: true } : n));
            setUnreadCount((prev) => Math.max(0, prev - 1));
        }
        setOpen(false);
        navigateForNotification(notif, navigate);
    };

    const handleMarkAllRead = async () => {
        await markAllRead();
        setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
        setUnreadCount(0);
    };

    const handleEnableDesktop = async () => {
        if (!isSupported()) return;
        setDesktopBusy(true);
        try {
            // Prefer live permission — state can be stale after user changed Chrome settings.
            let perm = getPermission();
            if (perm === 'default') {
                perm = await requestPermission();
            }
            setDesktopPerm(perm);
            if (perm === 'granted') {
                setPreference(true);
                setDesktopPref('on');
                // Immediate proof that OS banners work (historical bell items do not re-fire).
                const n = showDesktopNotification({
                    id: `test-${Date.now()}`,
                    title: 'MHMW Brain',
                    body: 'Desktop alerts are on. New mentions and to-dos will pop up here.',
                });
                if (n) {
                    n.onclick = () => { n.close(); try { window.focus(); } catch { /* ignore */ } };
                }
            }
        } finally {
            setDesktopBusy(false);
        }
    };

    const handleDisableDesktop = () => {
        setPreference(false);
        setDesktopPref('off');
    };

    const handleTestDesktop = () => {
        if (!shouldShowDesktop()) return;
        const n = showDesktopNotification({
            id: `test-${Date.now()}`,
            title: 'MHMW Brain',
            body: 'Test alert — if you see this, desktop notifications are working.',
        });
        if (n) {
            n.onclick = () => { n.close(); try { window.focus(); } catch { /* ignore */ } };
        }
    };

    const dismissToast = (toastId) => {
        setToasts((prev) => prev.map((t) => t.id === toastId ? { ...t, exiting: true } : t));
        setTimeout(() => {
            setToasts((prev) => prev.filter((t) => t.id !== toastId));
        }, 300);
    };

    const handleToastClick = (toastId) => {
        dismissToast(toastId);
        if (!open) handleOpen();
    };

    const desktopSupported = isSupported();
    const desktopOn = desktopPref === 'on' && desktopPerm === 'granted';

    const isRail = variant === 'rail';
    const isPod = variant === 'pod';

    const panelBody = open ? (
        <div
            ref={panelRef}
            data-notif-panel
            className={
                isRail
                    ? 'fixed overflow-y-auto bg-surface border border-hairline rounded-xl shadow-lg z-[60]'
                    : 'absolute right-0 mt-2 w-96 max-h-96 overflow-y-auto bg-surface border border-hairline rounded-xl shadow-lg z-[60]'
            }
            style={
                isRail && railPanelPos
                    ? {
                        left: railPanelPos.left,
                        top: railPanelPos.top,
                        width: PANEL_W,
                        maxHeight: railPanelPos.maxHeight,
                        boxShadow: 'var(--shadow)',
                    }
                    : undefined
            }
        >
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-hairline sticky top-0 bg-surface z-10">
                <span className="text-sm font-semibold text-ink">Notifications</span>
                {unreadCount > 0 && (
                    <button
                        type="button"
                        onClick={handleMarkAllRead}
                        className="text-xs text-brand hover:opacity-80 font-medium"
                    >
                        Mark all read
                    </button>
                )}
            </div>

            {desktopSupported && (
                <div className="px-4 py-2 border-b border-hairline bg-surface-2">
                    {desktopPerm === 'denied' ? (
                        <p className="text-[11px] text-ink-3 leading-snug">
                            Desktop alerts blocked in Chrome. Use the lock icon in the address bar → Site settings → Notifications → Allow, then click Enable here.
                        </p>
                    ) : desktopOn ? (
                        <div className="flex items-center justify-between gap-2">
                            <p className="text-[11px] text-ink-2">
                                Desktop alerts on
                                <span className="text-ink-3"> · while Brain tab is open</span>
                            </p>
                            <div className="flex items-center gap-2 shrink-0">
                                <button
                                    type="button"
                                    onClick={handleTestDesktop}
                                    className="text-[11px] font-medium text-brand hover:opacity-80"
                                >
                                    Test
                                </button>
                                <button
                                    type="button"
                                    onClick={handleDisableDesktop}
                                    className="text-[11px] font-medium text-ink-3 hover:text-ink-2"
                                >
                                    Turn off
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="flex items-center justify-between gap-2">
                            <p className="text-[11px] text-ink-2 leading-snug">
                                {desktopPerm === 'granted'
                                    ? 'Chrome allows alerts — turn them on for Brain'
                                    : 'Get desktop alerts for new mentions and to-dos'}
                            </p>
                            <button
                                type="button"
                                onClick={handleEnableDesktop}
                                disabled={desktopBusy}
                                className="text-[11px] font-semibold text-brand hover:opacity-80 shrink-0 disabled:opacity-50"
                            >
                                {desktopBusy ? '…' : 'Enable'}
                            </button>
                        </div>
                    )}
                </div>
            )}

            {loading ? (
                <div className="px-4 py-6 text-center text-sm text-ink-3">Loading...</div>
            ) : notifications.length === 0 ? (
                <div className="px-4 py-6 text-center text-sm text-ink-3">No notifications</div>
            ) : (
                notifications.map((n) => (
                    <button
                        key={n.id}
                        type="button"
                        onClick={() => handleClick(n)}
                        className={`w-full text-left px-4 py-3 border-b border-hairline hover:bg-surface-2 transition-colors ${
                            !n.is_read ? 'bg-brand-soft' : ''
                        }`}
                    >
                        <div className="flex items-start gap-2">
                            {!n.is_read && (
                                <span className="mt-1.5 w-2 h-2 rounded-full bg-brand shrink-0" />
                            )}
                            <div className={`min-w-0 ${!n.is_read ? '' : 'ml-4'}`}>
                                <p className="text-xs font-medium text-ink">
                                    {getActionText(n.message, n.board_item_title)}
                                </p>
                                {n.board_item_title && (
                                    <p className="text-xs text-ink-3 mt-0.5 truncate">
                                        {n.board_item_title}
                                    </p>
                                )}
                                {n.submittal_id && (
                                    <p className="text-xs text-ink-3 mt-0.5 truncate">
                                        {[n.submittal_project_number, n.submittal_project_name, n.submittal_title].filter(Boolean).join(' · ') || `Submittal #${n.submittal_id}`}
                                    </p>
                                )}
                                {(n.drawing_version_comment_id || n.bb_drawing_review_id) && (
                                    <p className="text-xs text-ink-3 mt-0.5 truncate">
                                        {[
                                            n.release_job_number != null ? `${n.release_job_number}-${n.release_number}` : null,
                                            n.drawing_version_number
                                                ? `Drawing v${n.drawing_version_number}`
                                                : (n.bb_drawing_review_id ? 'Drawing review' : 'Drawing comment'),
                                        ].filter(Boolean).join(' · ')}
                                    </p>
                                )}
                                <p className="text-[10px] text-ink-3 mt-0.5">{timeAgo(n.created_at)}</p>
                            </div>
                        </div>
                    </button>
                ))
            )}
        </div>
    ) : null;

    return (
        <div ref={ref} className={isRail ? 'relative w-full shrink-0' : 'relative'}>
            {isPod ? (
                <button
                    type="button"
                    onClick={handleOpen}
                    aria-label="Notifications"
                    aria-expanded={open}
                    className="inline-flex items-center gap-2 rounded-full bg-surface border border-hairline
                               pl-2.5 pr-3 py-1.5 text-ink-2 transition-colors hover:bg-surface-2
                               focus:outline-none focus:ring-2 focus:ring-accent-500"
                    style={{ boxShadow: 'var(--shadow)' }}
                >
                    <span className="grid place-items-center shrink-0">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                            strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                            <path d="M6 9a6 6 0 1 1 12 0v5l2 3H4l2-3z M10 20a2 2 0 0 0 4 0" />
                        </svg>
                    </span>
                    {unreadCount > 0 && (
                        <>
                            <span
                                className="grid place-items-center font-bold text-white"
                                style={{
                                    background: '#e0483c', borderRadius: 999, fontSize: 11,
                                    minWidth: 19, height: 19, padding: '0 6px',
                                }}
                            >
                                {unreadCount > 99 ? '99+' : unreadCount}
                            </span>
                            <span className="text-xs font-semibold text-ink">new</span>
                        </>
                    )}
                </button>
            ) : isRail ? (
                <button
                    type="button"
                    onClick={handleOpen}
                    onMouseEnter={(e) => {
                        onHoverLabel?.(e, 'Notifications');
                        if (!open) e.currentTarget.style.background = 'var(--rail-hover)';
                    }}
                    onMouseLeave={(e) => {
                        onLeaveLabel?.();
                        if (!open) e.currentTarget.style.background = 'transparent';
                    }}
                    aria-label="Notifications"
                    aria-expanded={open}
                    className="relative w-full flex items-center rounded-lg transition-colors"
                    style={{
                        height: itemHeight,
                        justifyContent: expanded ? 'flex-start' : 'center',
                        padding: expanded ? '0 10px' : 0,
                        gap: expanded ? 12 : 0,
                        background: open ? 'var(--rail-active)' : 'transparent',
                        color: open ? 'var(--rail-fg-active)' : 'var(--rail-fg)',
                    }}
                >
                    <span className="shrink-0 relative grid place-items-center" style={{ width: 19, height: 19 }}>
                        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                            strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                            <path d="M6 9a6 6 0 1 1 12 0v5l2 3H4l2-3z M10 20a2 2 0 0 0 4 0" />
                        </svg>
                        {/* Collapsed rail: badge hangs off the top-right of the icon, not over it. */}
                        {!expanded && unreadCount > 0 && (
                            <span
                                className="absolute grid place-items-center font-bold text-white pointer-events-none"
                                style={{
                                    background: '#e0483c', borderRadius: 999, fontSize: 10,
                                    minWidth: 17, height: 17, padding: '0 5px',
                                    top: -7, right: -9,
                                    boxShadow: '0 0 0 2px var(--rail-bg)',
                                }}
                            >
                                {unreadCount > 99 ? '99+' : unreadCount}
                            </span>
                        )}
                    </span>
                    {expanded && (
                        <span className="truncate" style={{ fontSize: 12.5, fontWeight: 600 }}>Notifications</span>
                    )}
                    {expanded && <span className="flex-1" />}
                    {/* Expanded rail: badge sits at the end of the row label. */}
                    {expanded && unreadCount > 0 && (
                        <span
                            className="grid place-items-center font-bold text-white"
                            style={{
                                background: '#e0483c', borderRadius: 999, fontSize: 10,
                                minWidth: 17, height: 17, padding: '0 5px',
                            }}
                        >
                            {unreadCount > 99 ? '99+' : unreadCount}
                        </span>
                    )}
                </button>
            ) : (
                <button
                    type="button"
                    onClick={handleOpen}
                    className="relative p-2 rounded-lg text-ink-2 hover:bg-surface-2 focus:outline-none focus:ring-2 focus:ring-accent-500"
                    aria-label="Notifications"
                    aria-expanded={open}
                >
                    <span className="relative inline-flex">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={BELL_ICON_PATH} />
                        </svg>
                        {unreadCount > 0 && (
                            <span className="absolute -top-1.5 -right-2.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 text-[10px] font-bold text-white bg-red-500 rounded-full pointer-events-none">
                                {unreadCount > 99 ? '99+' : unreadCount}
                            </span>
                        )}
                    </span>
                </button>
            )}

            {/* Rail: portal out of overflow:hidden + sticky stacking. Topbar: in-tree absolute is fine. */}
            {isRail
                ? (panelBody && typeof document !== 'undefined' ? createPortal(panelBody, document.body) : null)
                : panelBody}

            {/* Toast notifications */}
            {toasts.length > 0 && (
                <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2">
                    {toasts.map((toast) => (
                        <button
                            key={toast.id}
                            type="button"
                            onClick={() => handleToastClick(toast.id)}
                            className={`flex items-center gap-3 px-4 py-3 bg-surface border border-hairline rounded-xl shadow-lg cursor-pointer hover:bg-surface-2 transition-colors ${
                                toast.exiting ? 'animate-slide-out-right' : 'animate-slide-in-right'
                            }`}
                        >
                            <svg className="w-5 h-5 text-brand shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={BELL_ICON_PATH} />
                            </svg>
                            <span className="text-sm text-ink">{toast.text}</span>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
