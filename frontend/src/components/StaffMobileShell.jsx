/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The EMPLOYEE phone shell for the /m/* routes: the same 56px top bar as the sub portal
 *          (To-Dos · Job Log · T&M) over the routed page, plus an account sheet (name, Desktop site,
 *          Log out). Rendered by AppShell in place of its desktop chrome when the path is /m/…, so
 *          it sits inside the same providers (ReleasesProvider, LocationProvider) and the staff
 *          release modal works unchanged.
 * exports:
 *   StaffMobileShell: Layout; child routes render via Outlet and get { unread, refreshUnread }.
 * imports_from: [react, react-router-dom, ../utils/auth, ../services/notificationApi, ./mobile/MobileTopBar,
 *                ../styles/sub-portal.css, @fontsource/lato]
 * imported_by: [components/AppShell.jsx]
 * invariants:
 *   - Staff routes only: the badge counts come from /brain/notifications (unread mentions +
 *     to-do pings among the newest 50) — never the sub endpoints.
 *   - Same .sub-* styles as the sub portal so the two phone experiences are one design.
 */
import { useCallback, useEffect, useState } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { checkAuth, logout } from '../utils/auth';
import { fetchNotifications, MENTION_TYPES, TODO_TYPES as STAFF_TODO_TYPES } from '../services/notificationApi';
import MobileTopBar from './mobile/MobileTopBar';
import '@fontsource/lato/400.css';
import '@fontsource/lato/700.css';
import '@fontsource/lato/900.css';
import '../styles/sub-portal.css';

const UNREAD_POLL_MS = 60000;
/** sessionStorage flag: this tab chose the desktop chrome at phone width. */
export const DESKTOP_OPT_OUT_KEY = 'mhmw-mobile-desktop-opt-out';
const EMPTY = { unread_count: 0, unread_todos: 0, unread_mentions: 0 };

const ICONS = {
    desktop: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="2" y="3" width="20" height="14" rx="2" /><path d="M8 21h8M12 17v4" /></svg>,
    out: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5M21 12H9" /></svg>,
};

function initialsOf(name) {
    const words = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!words.length) return '?';
    return (words.length === 1 ? words[0].slice(0, 2) : words[0][0] + words[1][0]).toUpperCase();
}

export default function StaffMobileShell() {
    const navigate = useNavigate();
    const [user, setUser] = useState(null);
    const [sheetOpen, setSheetOpen] = useState(false);
    const [unread, setUnread] = useState(EMPTY);

    useEffect(() => { checkAuth().then((u) => setUser(u || null)); }, []);

    const refreshUnread = useCallback(() => {
        fetchNotifications({ types: [...MENTION_TYPES, ...STAFF_TODO_TYPES], limit: 50 })
            .then((d) => {
                const rows = (d.notifications || []).filter((n) => !n.is_read);
                const todos = rows.filter((n) => STAFF_TODO_TYPES.includes(n.type)).length;
                const mentions = rows.filter((n) => MENTION_TYPES.includes(n.type)).length;
                setUnread({ unread_count: todos + mentions, unread_todos: todos, unread_mentions: mentions });
            })
            .catch(() => {});
    }, []);
    useEffect(() => {
        refreshUnread();
        const t = setInterval(() => { if (document.visibilityState === 'visible') refreshUnread(); }, UNREAD_POLL_MS);
        return () => clearInterval(t);
    }, [refreshUnread]);

    useEffect(() => {
        if (!sheetOpen) return undefined;
        const onKey = (e) => { if (e.key === 'Escape') setSheetOpen(false); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [sheetOpen]);

    const name = user ? `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.username : '';
    const tabs = [
        { to: '/m/todos', label: 'To-Dos', badge: unread.unread_count },
        { to: '/m/job-log', label: 'Job Log' },
        { to: '/m/tm-tickets', label: 'T&M' },
    ];

    return (
        <div className="sub-shell">
            <MobileTopBar tabs={tabs} onMenu={() => setSheetOpen(true)} />
            <main className="sub-page">
                <Outlet context={{ unread, refreshUnread, user }} />
            </main>
            {sheetOpen && (
                <>
                    <div className="sub-scrim" onClick={() => setSheetOpen(false)} aria-hidden="true" />
                    <section className="sub-sheet" role="dialog" aria-modal="true" aria-label="Account">
                        <div className="grab" />
                        <div className="who">
                            <div className="tile" aria-hidden="true">{initialsOf(name)}</div>
                            <div className="min-w-0"><b className="truncate">{name || 'MHMW'}</b><span>MHMW · signed in</span></div>
                            <button type="button" className="close" aria-label="Close" onClick={() => setSheetOpen(false)}>×</button>
                        </div>
                        <button type="button" className="row" onClick={() => { setSheetOpen(false); navigate('/m/todos?seg=mentions'); }}>
                            Notifications
                        </button>
                        <button type="button" className="row" onClick={() => {
                            try { sessionStorage.setItem(DESKTOP_OPT_OUT_KEY, '1'); } catch { /* ignore */ }
                            setSheetOpen(false); navigate('/job-log');
                        }}>
                            {ICONS.desktop} Desktop site
                        </button>
                        <button type="button" className="row danger" onClick={async () => { await logout(); window.location.href = '/login'; }}>
                            {ICONS.out} Log out
                        </button>
                    </section>
                </>
            )}
        </div>
    );
}
