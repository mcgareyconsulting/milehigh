/**
 * @milehigh-header
 * schema_version: 2
 * purpose: The subcontractor app shell — a PHONE-PORTRAIT layout: slim header (company, contact,
 *          overflow menu with T&M tickets + logout), the routed page, and a fixed bottom tab bar
 *          with the two surfaces a sub works from: To-Dos (their to-dos + @mentions) and Job Log
 *          (their crew's Timeline). Self-contained auth check (unlike AppShell, which relies on
 *          App.jsx's staff isAuthenticated) because /sub is a separate top-level route tree.
 * exports:
 *   SubcontractorShell: Layout shell; child routes render via Outlet once authenticated and
 *     receive { subcontractor, refreshUnread } through useOutletContext().
 * imports_from: [react, react-router-dom, ../utils/subcontractorAuth, ../services/subPortalApi]
 * imported_by: [frontend/src/App.jsx]
 * invariants:
 *   - Redirects to /sub/login if checkSubcontractorAuth() returns null — never the staff /login.
 *   - Two tabs only. T&M tickets stay reachable (overflow menu) but are not a tab: Bill's spec is a
 *     home page of to-dos + the timeline, and a third tab on a 375px-wide bar costs legibility.
 *   - The tab bar is position:fixed with safe-area padding so it clears the iPhone home indicator;
 *     the content area carries matching bottom padding so the last card is never hidden under it.
 *   - The unread badge polls the sub-scoped count (never the staff bell endpoint) and is refreshed
 *     eagerly by pages that mark things read, via the outlet context.
 *   - Colors are Job Log tokens (surface / hairline / ink) so the portal follows the app theme.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, Outlet, NavLink } from 'react-router-dom';
import { checkSubcontractorAuth, subcontractorLogout } from '../utils/subcontractorAuth';
import { subUnreadCount } from '../services/subPortalApi';

const UNREAD_POLL_MS = 60000;

function TabIcon({ name }) {
    if (name === 'todos') {
        return (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
            </svg>
        );
    }
    return (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" />
        </svg>
    );
}

export default function SubcontractorShell() {
    const navigate = useNavigate();
    const [subcontractor, setSubcontractor] = useState(null);
    const [loading, setLoading] = useState(true);
    const [menuOpen, setMenuOpen] = useState(false);
    const [unread, setUnread] = useState(0);
    const menuRef = useRef(null);

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

    // Close the overflow menu on outside tap.
    useEffect(() => {
        if (!menuOpen) return undefined;
        const onDown = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false); };
        document.addEventListener('pointerdown', onDown);
        return () => document.removeEventListener('pointerdown', onDown);
    }, [menuOpen]);

    const handleLogout = async () => {
        await subcontractorLogout();
        navigate('/sub/login', { replace: true });
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-canvas">
                <div className="text-ink-3">Loading…</div>
            </div>
        );
    }

    const tabClass = ({ isActive }) =>
        `flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-[11px] font-semibold select-none ${
            isActive ? 'text-accent-600 dark:text-accent-400' : 'text-ink-3'
        }`;

    return (
        <div className="min-h-screen bg-canvas text-ink flex flex-col">
            <header className="sticky top-0 z-30 flex items-center justify-between gap-3 px-4 py-2.5 border-b border-hairline bg-surface/95 backdrop-blur">
                <div className="min-w-0">
                    <div className="text-sm font-bold truncate">{subcontractor?.company_name}</div>
                    <div className="text-[11px] text-ink-3 truncate">
                        {subcontractor?.contact_name}
                        {subcontractor?.installer_team ? ` · ${subcontractor.installer_team}` : ' · no crew assigned'}
                    </div>
                </div>
                <div className="relative shrink-0" ref={menuRef}>
                    <button
                        type="button"
                        aria-label="Menu"
                        aria-expanded={menuOpen}
                        onClick={() => setMenuOpen(o => !o)}
                        className="w-10 h-10 -mr-2 flex items-center justify-center rounded-lg text-ink-2 active:bg-surface-2"
                    >
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <circle cx="12" cy="5" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="12" cy="19" r="2" />
                        </svg>
                    </button>
                    {menuOpen && (
                        <div className="absolute right-0 mt-1 w-48 rounded-xl border border-hairline bg-surface shadow-lg overflow-hidden z-40">
                            <button type="button" onClick={() => { setMenuOpen(false); navigate('/sub/tickets'); }}
                                className="w-full text-left px-4 py-3 text-sm text-ink active:bg-surface-2">
                                T&amp;M tickets
                            </button>
                            <button type="button" onClick={handleLogout}
                                className="w-full text-left px-4 py-3 text-sm text-ink border-t border-hairline active:bg-surface-2">
                                Log out
                            </button>
                        </div>
                    )}
                </div>
            </header>

            {/* Bottom padding clears the fixed tab bar (56px) plus the home-indicator inset. */}
            <main className="flex-1 min-h-0 flex flex-col" style={{ paddingBottom: 'calc(56px + env(safe-area-inset-bottom))' }}>
                <Outlet context={{ subcontractor, refreshUnread, unread }} />
            </main>

            <nav
                aria-label="Sections"
                className="fixed bottom-0 inset-x-0 z-30 flex border-t border-hairline bg-surface/95 backdrop-blur"
                style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
            >
                <NavLink to="/sub/todos" className={tabClass}>
                    <span className="relative">
                        <TabIcon name="todos" />
                        {unread > 0 && (
                            <span className="absolute -top-1 -right-2 min-w-[16px] h-4 px-1 rounded-full bg-red-600 text-white text-[10px] font-bold leading-4 text-center">
                                {unread > 99 ? '99+' : unread}
                            </span>
                        )}
                    </span>
                    To-Dos
                </NavLink>
                <NavLink to="/sub/job-log" className={tabClass}>
                    <TabIcon name="joblog" />
                    Job Log
                </NavLink>
            </nav>
        </div>
    );
}
