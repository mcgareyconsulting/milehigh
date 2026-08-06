/**
 * @milehigh-header
 * schema_version: 1
 * purpose: In-app notification bell with 30s polling, toast popups on new mentions, opt-in Chrome desktop banners, and click-through to board/DWL/drawings/todos.
 * exports:
 *   NotificationBell: Default export — renders bell icon with unread badge, dropdown list, desktop opt-in, and toast stack
 * imports_from: [react, react-router-dom, ../services/notificationApi, ../utils/desktopNotifications]
 * imported_by: [frontend/src/components/AppShell.jsx]
 * invariants:
 *   - Polls /brain/notifications/unread-count every 30 seconds; pauses are NOT visibility-gated (runs even in background tabs).
 *   - Toast auto-dismisses after 5s with a 300ms exit animation — changing timing requires matching CSS animation duration.
 *   - Desktop Notification.requestPermission only runs from the opt-in button (user gesture).
 *   - First poll never fires toast or desktop banners for historical unread — only count increases after load.
 *   - Desktop banners require Chrome permission + localStorage preference; fire on new arrivals even if tab is focused.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
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
 *   dropdown to a fixed position beside the rail — the rail clips its children,
 *   so an in-tree `absolute right-0` panel would be both cut off and pointed
 *   the wrong way off the left edge of the screen.
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
    const [panelTop, setPanelTop] = useState(0);
    const [loading, setLoading] = useState(false);
    const [toasts, setToasts] = useState([]);
    // Desktop opt-in UI state (re-read after enable/disable clicks)
    const [desktopPref, setDesktopPref] = useState(() => getPreference());
    const [desktopPerm, setDesktopPerm] = useState(() => getPermission());
    const [desktopBusy, setDesktopBusy] = useState(false);

    const prevUnreadRef = useRef(null);
    const lastSeenNotifIdRef = useRef(null);
    const ref = useRef(null);
    const navigate = useNavigate();

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

    // Close on outside click
    useEffect(() => {
        const handler = (e) => {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const handleOpen = async () => {
        if (open) { setOpen(false); return; }
        // Rail variant pins the panel beside the rail rather than under the
        // trigger, so it needs the row's viewport position at open time.
        if (variant === 'rail' && ref.current) {
            setPanelTop(ref.current.getBoundingClientRect().top);
        }
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

    // `position: fixed` (not a portal) is enough to escape the rail's overflow
    // clipping — no ancestor establishes a containing block via transform.
    const panelPositionClass = isRail
        ? 'fixed w-96 max-h-96 overflow-y-auto'
        : 'absolute right-0 mt-2 w-96 max-h-96 overflow-y-auto';
    const panelPositionStyle = isRail ? { left: railWidth + 6, top: panelTop } : undefined;

    return (
        <div ref={ref} className={isRail ? 'relative w-full shrink-0' : 'relative'}>
            {isRail ? (
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
                    <span className="shrink-0 grid place-items-center" style={{ width: 19, height: 19 }}>
                        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                            strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                            <path d="M6 9a6 6 0 1 1 12 0v5l2 3H4l2-3z M10 20a2 2 0 0 0 4 0" />
                        </svg>
                    </span>
                    {expanded && (
                        <span className="truncate" style={{ fontSize: 12.5, fontWeight: 600 }}>Notifications</span>
                    )}
                    {expanded && <span className="flex-1" />}
                    {unreadCount > 0 && (
                        <span
                            className="grid place-items-center font-bold text-white"
                            style={{
                                background: '#e0483c', borderRadius: 999, fontSize: 10,
                                minWidth: 17, height: 17, padding: '0 5px',
                                position: expanded ? 'static' : 'absolute',
                                top: expanded ? undefined : 4,
                                right: expanded ? undefined : 9,
                                boxShadow: expanded ? 'none' : '0 0 0 2px var(--rail-bg)',
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
                    className="relative p-2 rounded-lg text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-accent-500"
                    aria-label="Notifications"
                >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={BELL_ICON_PATH} />
                    </svg>
                    {unreadCount > 0 && (
                        <span className="absolute -top-0.5 -right-0.5 inline-flex items-center justify-center w-4.5 h-4.5 min-w-[18px] px-1 text-[10px] font-bold text-white bg-red-500 rounded-full">
                            {unreadCount > 99 ? '99+' : unreadCount}
                        </span>
                    )}
                </button>
            )}

            {open && (
                <div
                    className={`${panelPositionClass} bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-xl shadow-lg z-50`}
                    style={panelPositionStyle}
                >
                    <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 dark:border-slate-700">
                        <span className="text-sm font-semibold text-gray-900 dark:text-slate-100">Notifications</span>
                        {unreadCount > 0 && (
                            <button
                                type="button"
                                onClick={handleMarkAllRead}
                                className="text-xs text-accent-500 hover:text-accent-600 font-medium"
                            >
                                Mark all read
                            </button>
                        )}
                    </div>

                    {desktopSupported && (
                        <div className="px-4 py-2 border-b border-gray-100 dark:border-slate-700 bg-gray-50/80 dark:bg-slate-900/40">
                            {desktopPerm === 'denied' ? (
                                <p className="text-[11px] text-gray-500 dark:text-slate-400 leading-snug">
                                    Desktop alerts blocked in Chrome. Use the lock icon in the address bar → Site settings → Notifications → Allow, then click Enable here.
                                </p>
                            ) : desktopOn ? (
                                <div className="flex items-center justify-between gap-2">
                                    <p className="text-[11px] text-gray-600 dark:text-slate-300">
                                        Desktop alerts on
                                        <span className="text-gray-400 dark:text-slate-500"> · while Brain tab is open</span>
                                    </p>
                                    <div className="flex items-center gap-2 shrink-0">
                                        <button
                                            type="button"
                                            onClick={handleTestDesktop}
                                            className="text-[11px] font-medium text-accent-500 hover:text-accent-600"
                                        >
                                            Test
                                        </button>
                                        <button
                                            type="button"
                                            onClick={handleDisableDesktop}
                                            className="text-[11px] font-medium text-gray-500 hover:text-gray-700 dark:text-slate-400 dark:hover:text-slate-200"
                                        >
                                            Turn off
                                        </button>
                                    </div>
                                </div>
                            ) : (
                                <div className="flex items-center justify-between gap-2">
                                    <p className="text-[11px] text-gray-600 dark:text-slate-300 leading-snug">
                                        {desktopPerm === 'granted'
                                            ? 'Chrome allows alerts — turn them on for Brain'
                                            : 'Get desktop alerts for new mentions and to-dos'}
                                    </p>
                                    <button
                                        type="button"
                                        onClick={handleEnableDesktop}
                                        disabled={desktopBusy}
                                        className="text-[11px] font-semibold text-accent-500 hover:text-accent-600 shrink-0 disabled:opacity-50"
                                    >
                                        {desktopBusy ? '…' : 'Enable'}
                                    </button>
                                </div>
                            )}
                        </div>
                    )}

                    {loading ? (
                        <div className="px-4 py-6 text-center text-sm text-gray-400">Loading...</div>
                    ) : notifications.length === 0 ? (
                        <div className="px-4 py-6 text-center text-sm text-gray-400 dark:text-slate-500">No notifications</div>
                    ) : (
                        notifications.map((n) => (
                            <button
                                key={n.id}
                                type="button"
                                onClick={() => handleClick(n)}
                                className={`w-full text-left px-4 py-3 border-b border-gray-50 dark:border-slate-700 hover:bg-gray-50 dark:hover:bg-slate-700 transition-colors ${
                                    !n.is_read ? 'bg-accent-50/50 dark:bg-accent-900/20' : ''
                                }`}
                            >
                                <div className="flex items-start gap-2">
                                    {!n.is_read && (
                                        <span className="mt-1.5 w-2 h-2 rounded-full bg-accent-500 shrink-0" />
                                    )}
                                    <div className={`min-w-0 ${!n.is_read ? '' : 'ml-4'}`}>
                                        <p className="text-xs font-medium text-gray-800 dark:text-slate-200">
                                            {getActionText(n.message, n.board_item_title)}
                                        </p>
                                        {n.board_item_title && (
                                            <p className="text-xs text-gray-500 dark:text-slate-400 mt-0.5 truncate">
                                                {n.board_item_title}
                                            </p>
                                        )}
                                        {n.submittal_id && (
                                            <p className="text-xs text-gray-500 dark:text-slate-400 mt-0.5 truncate">
                                                {[n.submittal_project_number, n.submittal_project_name, n.submittal_title].filter(Boolean).join(' · ') || `Submittal #${n.submittal_id}`}
                                            </p>
                                        )}
                                        {(n.drawing_version_comment_id || n.bb_drawing_review_id) && (
                                            <p className="text-xs text-gray-500 dark:text-slate-400 mt-0.5 truncate">
                                                {[
                                                    n.release_job_number != null ? `${n.release_job_number}-${n.release_number}` : null,
                                                    n.drawing_version_number
                                                        ? `Drawing v${n.drawing_version_number}`
                                                        : (n.bb_drawing_review_id ? 'Drawing review' : 'Drawing comment'),
                                                ].filter(Boolean).join(' · ')}
                                            </p>
                                        )}
                                        <p className="text-[10px] text-gray-400 dark:text-slate-500 mt-0.5">{timeAgo(n.created_at)}</p>
                                    </div>
                                </div>
                            </button>
                        ))
                    )}
                </div>
            )}

            {/* Toast notifications */}
            {toasts.length > 0 && (
                <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2">
                    {toasts.map((toast) => (
                        <button
                            key={toast.id}
                            type="button"
                            onClick={() => handleToastClick(toast.id)}
                            className={`flex items-center gap-3 px-4 py-3 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-xl shadow-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-slate-700 transition-colors ${
                                toast.exiting ? 'animate-slide-out-right' : 'animate-slide-in-right'
                            }`}
                        >
                            <svg className="w-5 h-5 text-accent-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={BELL_ICON_PATH} />
                            </svg>
                            <span className="text-sm text-gray-800 dark:text-slate-200">{toast.text}</span>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
