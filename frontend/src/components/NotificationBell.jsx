/**
 * @milehigh-header
 * schema_version: 1
 * purpose: In-app notification bell with 12s polling, toast popups on new mentions, and click-through to board items.
 * exports:
 *   NotificationBell: Default export — renders bell icon with unread badge, dropdown list, and toast stack
 * imports_from: [react, react-router-dom, ../services/notificationApi]
 * imported_by: [frontend/src/components/AppShell.jsx]
 * invariants:
 *   - Polls /brain/notifications/unread-count every 12 seconds; pauses are NOT visibility-gated (runs even in background tabs).
 *   - Toast auto-dismisses after 5s with a 300ms exit animation — changing timing requires matching CSS animation duration.
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchNotifications, fetchUnreadCount, markNotificationRead, markAllRead } from '../services/notificationApi';

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

export default function NotificationBell() {
    const [unreadCount, setUnreadCount] = useState(0);
    const [notifications, setNotifications] = useState([]);
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);
    const [toasts, setToasts] = useState([]);
    const prevUnreadRef = useRef(null);
    const ref = useRef(null);
    const navigate = useNavigate();

    // Poll unread count — 12s interval, trigger toast on increase
    useEffect(() => {
        let mounted = true;
        const poll = async () => {
            try {
                const count = await fetchUnreadCount();
                if (!mounted) return;

                // Show toast when count increases (skip first poll)
                if (prevUnreadRef.current !== null && count > prevUnreadRef.current) {
                    const newCount = count - prevUnreadRef.current;
                    const toastId = Date.now();
                    setToasts(prev => [...prev, {
                        id: toastId,
                        text: `${newCount} new notification${newCount > 1 ? 's' : ''}`,
                        exiting: false,
                    }]);
                    setTimeout(() => {
                        if (!mounted) return;
                        setToasts(prev => prev.map(t => t.id === toastId ? { ...t, exiting: true } : t));
                        setTimeout(() => {
                            if (!mounted) return;
                            setToasts(prev => prev.filter(t => t.id !== toastId));
                        }, 300);
                    }, 5000);
                }
                prevUnreadRef.current = count;
                setUnreadCount(count);
            } catch { /* ignore auth errors */ }
        };
        poll();
        const interval = setInterval(poll, 12000);
        return () => { mounted = false; clearInterval(interval); };
    }, []);

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
        setOpen(true);
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
            setNotifications(prev => prev.map(n => n.id === notif.id ? { ...n, is_read: true } : n));
            setUnreadCount(prev => Math.max(0, prev - 1));
        }
        setOpen(false);
        if (notif.board_item_id) {
            navigate('/board', { state: { openItemId: notif.board_item_id } });
        } else if (notif.submittal_id) {
            navigate(`/drafting-work-load?highlight=${encodeURIComponent(notif.submittal_id)}`);
        }
    };

    const handleMarkAllRead = async () => {
        await markAllRead();
        setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
        setUnreadCount(0);
    };

    const dismissToast = (toastId) => {
        setToasts(prev => prev.map(t => t.id === toastId ? { ...t, exiting: true } : t));
        setTimeout(() => {
            setToasts(prev => prev.filter(t => t.id !== toastId));
        }, 300);
    };

    const handleToastClick = (toastId) => {
        dismissToast(toastId);
        if (!open) handleOpen();
    };

    return (
        <div ref={ref} className="relative">
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

            {open && (
                <div className="absolute right-0 mt-2 w-96 max-h-96 overflow-y-auto bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-xl shadow-lg z-50">
                    <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 dark:border-slate-700">
                        <span className="text-sm font-semibold text-gray-900 dark:text-slate-100">Notifications</span>
                        {unreadCount > 0 && (
                            <button
                                onClick={handleMarkAllRead}
                                className="text-xs text-accent-500 hover:text-accent-600 font-medium"
                            >
                                Mark all read
                            </button>
                        )}
                    </div>

                    {loading ? (
                        <div className="px-4 py-6 text-center text-sm text-gray-400">Loading...</div>
                    ) : notifications.length === 0 ? (
                        <div className="px-4 py-6 text-center text-sm text-gray-400 dark:text-slate-500">No notifications</div>
                    ) : (
                        notifications.map(n => (
                            <button
                                key={n.id}
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
                    {toasts.map(toast => (
                        <button
                            key={toast.id}
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
