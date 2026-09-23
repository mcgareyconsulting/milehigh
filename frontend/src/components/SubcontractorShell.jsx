/**
 * @milehigh-header
 * schema_version: 3
 * purpose: The subcontractor app shell, Option A (docs: subs-mobile-option-a.md) — ONE 56px top bar
 *          holding the Brain logo (display only), a pill tab track with the three sections
 *          (To-Dos · Job Log · T&M) and a hamburger menu that opens the account sheet; the routed
 *          page scrolls under it. The sheet carries the company information that left the header:
 *          company, signed-in contact, the crew the account views as, a Notifications shortcut
 *          and Sign out.
 *          Self-contained auth check (unlike AppShell, which relies on App.jsx's staff
 *          isAuthenticated) because /sub is a separate top-level route tree.
 * exports:
 *   SubcontractorShell: Layout shell; child routes render via Outlet once authenticated and
 *     receive { subcontractor, refreshUnread, unread } through useOutletContext().
 * imports_from: [react, react-router-dom, ../utils/subcontractorAuth, ../services/subPortalApi,
 *                ../styles/sub-portal.css, @fontsource/lato]
 * imported_by: [frontend/src/App.jsx]
 * invariants:
 *   - Redirects to /sub/login if checkSubcontractorAuth() returns null — never the staff /login.
 *   - Fixed chrome is the 56px bar and nothing else: no bottom nav, no second header row. Page
 *     context (crew, window) lives in each page's title row, not in the bar.
 *   - The tab track and the sheet use the .sub-* classes from styles/sub-portal.css, which also
 *     rewrites the design tokens for this subtree — the portal is Lato + the spec palette in both
 *     themes; the staff app is untouched.
 *   - The red tab badge = unread to-do pings + unread mentions, from the sub-scoped count endpoint
 *     (never the staff bell), polled while visible and refreshed eagerly by pages that mark things
 *     read, via the outlet context. `unread` in the context is the {unread_count, unread_todos,
 *     unread_mentions} object so the To-Dos page can badge its two segments separately.
 *   - The sheet closes on scrim tap and Escape.
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate, Outlet, NavLink } from 'react-router-dom';
import { checkSubcontractorAuth, subcontractorLogout } from '../utils/subcontractorAuth';
import { subUnreadCount } from '../services/subPortalApi';
import '@fontsource/lato/400.css';
import '@fontsource/lato/700.css';
import '@fontsource/lato/900.css';
import '../styles/sub-portal.css';

const UNREAD_POLL_MS = 60000;

/** Two-letter tile for a company with no logo asset ("McGarey Construction" -> "MC"). */
function initialsOf(name) {
    const words = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!words.length) return '?';
    return (words.length === 1 ? words[0].slice(0, 2) : words[0][0] + words[1][0]).toUpperCase();
}

const ICONS = {
    todos: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="3" /><path d="M8 12l3 3 5-6" /></svg>,
    joblog: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></svg>,
    tm: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h5" /></svg>,
    menu: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>,
    bell: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>,
    out: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5M21 12H9" /></svg>,
};

function AccountSheet({ subcontractor, onClose, onLogout, onNotifications }) {
    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [onClose]);

    return (
        <>
            <div className="sub-scrim" onClick={onClose} aria-hidden="true" />
            <section className="sub-sheet" role="dialog" aria-modal="true" aria-label="Account">
                <div className="grab" />
                <div className="who">
                    <div className="tile" aria-hidden="true">{initialsOf(subcontractor?.company_name)}</div>
                    <div className="min-w-0">
                        <b className="truncate">{subcontractor?.company_name}</b>
                        <span>{subcontractor?.contact_name} · signed in</span>
                    </div>
                    <button type="button" className="close" aria-label="Close" onClick={onClose}>×</button>
                </div>
                <div className="viewing">
                    <div>
                        <small>Viewing as</small>
                        <b>{subcontractor?.installer_team || 'No crew assigned'}</b>
                    </div>
                </div>
                <button type="button" className="row" onClick={onNotifications}>
                    {ICONS.bell} Notifications
                </button>
                <button type="button" className="row danger" onClick={onLogout}>
                    {ICONS.out} Sign out
                </button>
            </section>
        </>
    );
}

export default function SubcontractorShell() {
    const navigate = useNavigate();
    const [subcontractor, setSubcontractor] = useState(null);
    const [loading, setLoading] = useState(true);
    const [sheetOpen, setSheetOpen] = useState(false);
    const [unread, setUnread] = useState({ unread_count: 0, unread_todos: 0, unread_mentions: 0 });

    useEffect(() => {
        checkSubcontractorAuth().then(sub => {
            if (!sub) {
                navigate('/sub/login', { replace: true });
                return;
            }
            setSubcontractor(sub);
            setLoading(false);
        });
    }, [navigate]);

    const refreshUnread = useCallback(() => {
        subUnreadCount().then(setUnread).catch(() => {});
    }, []);

    useEffect(() => {
        if (loading) return undefined;
        refreshUnread();
        const t = setInterval(() => {
            if (document.visibilityState === 'visible') refreshUnread();
        }, UNREAD_POLL_MS);
        return () => clearInterval(t);
    }, [loading, refreshUnread]);

    const closeSheet = useCallback(() => setSheetOpen(false), []);
    const handleLogout = async () => {
        await subcontractorLogout();
        navigate('/sub/login', { replace: true });
    };
    const goNotifications = () => {
        setSheetOpen(false);
        navigate('/sub/todos?seg=mentions');
    };

    if (loading) {
        return (
            <div className="sub-shell items-center justify-center">
                <div className="text-ink-3">Loading…</div>
            </div>
        );
    }

    const tabClass = ({ isActive }) => `sub-tab${isActive ? ' active' : ''}`;

    return (
        <div className="sub-shell">
            <header className="sub-topbar">
                {/* The Brain logo, display only. Company / account details live behind the menu. */}
                <img className="sub-logo" src="/logo.jpg" alt="MHMW Brain" />
                <nav className="sub-tabs" aria-label="Sections">
                    <NavLink to="/sub/todos" className={tabClass}>
                        {ICONS.todos}<span>To-Dos</span>
                        {unread.unread_count > 0 && (
                            <span className="sub-tab-badge" aria-label={`${unread.unread_count} unread`}>
                                {unread.unread_count > 99 ? '99+' : unread.unread_count}
                            </span>
                        )}
                    </NavLink>
                    <NavLink to="/sub/job-log" className={tabClass}>
                        {ICONS.joblog}<span>Job Log</span>
                    </NavLink>
                    <NavLink to="/sub/tickets" className={tabClass}>
                        {ICONS.tm}<span>T&amp;M</span>
                    </NavLink>
                </nav>
                <button type="button" className="sub-menu-btn" aria-label="Menu" onClick={() => setSheetOpen(true)}>
                    {ICONS.menu}
                </button>
            </header>

            <main className="sub-page">
                <Outlet context={{ subcontractor, refreshUnread, unread }} />
            </main>

            {sheetOpen && (
                <AccountSheet
                    subcontractor={subcontractor}
                    onClose={closeSheet}
                    onLogout={handleLogout}
                    onNotifications={goNotifications}
                />
            )}
        </div>
    );
}
