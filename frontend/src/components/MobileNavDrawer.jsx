/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Slide-in mobile/iPad drawer that exposes the AppShell nav links when the horizontal button row is collapsed.
 * exports:
 *   MobileNavDrawer: Drawer with nav links. Props: open, onClose, isAuthenticated, isAdmin, canSeeReport, locationEnabled, locationRequesting, onLocationToggle, onLogout, onLogin.
 * imports_from: [react, react-router-dom]
 * imported_by: [frontend/src/components/AppShell.jsx]
 * invariants:
 *   - Closes after every navigation to avoid stale drawer state on the new route.
 *   - Backdrop click closes drawer; ESC key also closes.
 */
import React, { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

const NAV_ITEMS = [
    { label: 'Map', path: '/jobsite-map' },
    { label: 'Job Log', path: '/job-log' },
    { label: 'Drafting WL', path: '/drafting-work-load' },
    { label: 'Timeline', path: '/pm-board' },
    { label: 'Events', path: '/events' },
    { label: 'To-Dos', path: '/todos' },
    { label: 'Install Schedule', path: '/install-schedule' },
];

// Rentals nav removed 2026-07-12 (company change) — route + backend intact.
const ADMIN_ITEMS = [
    { label: 'Meetings', path: '/meetings' },
    { label: 'Bug Tracker', path: '/board' },
    { label: 'Submittal Matching', path: '/admin/submittal-matching' },
];

export default function MobileNavDrawer({
    open,
    onClose,
    isAuthenticated,
    isAdmin,
    canSeeReport,
    locationEnabled,
    locationRequesting,
    onLocationToggle,
    onLogout,
    onLogin,
}) {
    const navigate = useNavigate();
    const location = useLocation();

    useEffect(() => {
        if (!open) return undefined;
        const onKey = (e) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [open, onClose]);

    if (!open) return null;

    const go = (path) => {
        navigate(path);
        onClose();
    };

    const isActive = (path) => location.pathname.startsWith(path);

    const itemClass = (active) => `w-full text-left px-4 py-3 rounded-lg text-sm font-medium transition-colors min-h-[44px] flex items-center ${
        active
            ? 'bg-accent-500 text-white'
            : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
    }`;

    return (
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 z-50 bg-black/40 min-[1440px]:hidden"
                onClick={onClose}
                aria-hidden="true"
            />
            {/* Drawer */}
            <aside
                className="fixed top-0 right-0 z-50 h-full w-72 max-w-[85vw] bg-white dark:bg-slate-800 shadow-xl border-l border-gray-200 dark:border-slate-600 min-[1440px]:hidden flex flex-col animate-slide-in-right"
                style={{ paddingTop: 'env(safe-area-inset-top)' }}
                role="dialog"
                aria-label="Navigation menu"
            >
                <div className="flex items-center justify-between h-14 px-4 border-b border-gray-200 dark:border-slate-600 flex-shrink-0">
                    <span className="text-lg font-bold bg-gradient-to-r from-accent-500 to-accent-600 dark:from-accent-300 dark:to-accent-400 bg-clip-text text-transparent">
                        MHMW Brain
                    </span>
                    <button
                        type="button"
                        onClick={onClose}
                        className="p-2 rounded-lg text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700"
                        aria-label="Close menu"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                <nav className="flex-1 overflow-y-auto p-3 space-y-1">
                    {/* Location toggle — at top so PMs in field reach it without scrolling */}
                    <button
                        type="button"
                        onClick={() => { onLocationToggle(); }}
                        disabled={locationRequesting}
                        className={`w-full text-left px-4 py-3 rounded-lg text-sm font-medium transition-colors min-h-[44px] flex items-center gap-2 ${
                            locationEnabled
                                ? 'bg-green-500 text-white hover:bg-green-600'
                                : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
                        } ${locationRequesting ? 'opacity-70 cursor-wait' : ''}`}
                    >
                        {locationRequesting
                            ? <><span className="inline-block w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />Requesting…</>
                            : locationEnabled
                                ? <>📍 Location on</>
                                : <>📍 Location</>
                        }
                    </button>

                    <div className="h-px bg-gray-200 dark:bg-slate-600 my-2" />

                    {NAV_ITEMS.map(item => (
                        <button
                            key={item.path}
                            type="button"
                            onClick={() => go(item.path)}
                            className={itemClass(isActive(item.path))}
                        >
                            {item.label}
                        </button>
                    ))}

                    {canSeeReport && (
                        <button
                            type="button"
                            onClick={() => go('/invoicing-report')}
                            className={itemClass(isActive('/invoicing-report'))}
                        >
                            Invoicing
                        </button>
                    )}

                    {isAdmin && ADMIN_ITEMS.map(item => (
                        <button
                            key={item.path}
                            type="button"
                            onClick={() => go(item.path)}
                            className={itemClass(isActive(item.path))}
                        >
                            {item.label}
                        </button>
                    ))}
                </nav>

                <div className="p-3 border-t border-gray-200 dark:border-slate-600 flex-shrink-0" style={{ paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom))' }}>
                    {isAuthenticated ? (
                        <button
                            type="button"
                            onClick={() => { onLogout(); onClose(); }}
                            className="w-full px-4 py-3 text-sm font-medium text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg transition-colors min-h-[44px]"
                        >
                            Logout
                        </button>
                    ) : (
                        <button
                            type="button"
                            onClick={() => { onLogin(); onClose(); }}
                            className="w-full px-4 py-3 text-sm font-medium text-white bg-accent-500 hover:bg-accent-600 rounded-lg shadow-md min-h-[44px]"
                        >
                            Log in
                        </button>
                    )}
                </div>
            </aside>
        </>
    );
}
