/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared shell for the admin Subs area. Collapses two formerly separate top-nav
 *   items under one "Subs" stub:
 *     - Subcontractors: invite + standing roster (SubcontractorAdmin)
 *     - Invoice Paid: installer invoice paid tracking (former standalone Subs page)
 *   Customer billing "Invoicing" stays a separate top-nav item and is NOT here.
 * exports:
 *   SubsLayout: Layout route with tab strip + <Outlet> for child pages.
 * imports_from: [react, react-router-dom, ../utils/auth]
 * imported_by: [App.jsx]
 * invariants:
 *   - Top-level nav label is always "Subs"; child pages own their page titles.
 *   - Both tabs are admin-only (mirrors the previous top-level gates).
 *   - Index / unknown child redirects to the first tab (Subcontractors).
 */
import { useEffect, useState } from 'react';
import { Navigate, NavLink, Outlet, useLocation } from 'react-router-dom';
import { checkAuth } from '../utils/auth';

const TABS = [
    {
        key: 'subcontractors',
        label: 'Subcontractors',
        path: '/subs/subcontractors',
        title: 'Invite and manage the subcontractor roster',
    },
    {
        key: 'invoice-paid',
        label: 'Invoice Paid',
        path: '/subs/invoice-paid',
        title: 'Installer invoice paid tracking by release',
    },
];

export default function SubsLayout() {
    const location = useLocation();
    const [authorized, setAuthorized] = useState(null); // null loading, bool result

    useEffect(() => {
        checkAuth().then((user) => setAuthorized(!!(user && user.is_admin)));
    }, []);

    if (authorized === null) {
        return (
            <div className="flex-1 flex items-center justify-center text-gray-600 dark:text-slate-400">
                Loading…
            </div>
        );
    }

    if (!authorized) {
        return (
            <div className="flex-1 flex items-center justify-center p-6 text-center text-gray-600 dark:text-slate-400">
                Subs is available to admins only.
            </div>
        );
    }

    const isIndexOrUnknown =
        location.pathname === '/subs' ||
        location.pathname === '/subs/' ||
        !TABS.some((t) => location.pathname.startsWith(t.path));

    if (isIndexOrUnknown) {
        return <Navigate to={TABS[0].path} replace />;
    }

    return (
        <div className="flex-1 min-h-0 flex flex-col">
            <div className="shrink-0 border-b border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                <div className="max-w-[1600px] mx-auto px-4 sm:px-6 flex items-center gap-1">
                    <nav className="flex gap-1" role="tablist" aria-label="Subs sections">
                        {TABS.map((tab) => (
                            <NavLink
                                key={tab.key}
                                to={tab.path}
                                role="tab"
                                title={tab.title}
                                className={({ isActive }) =>
                                    `px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                                        isActive
                                            ? 'border-accent-500 text-accent-600 dark:text-accent-300'
                                            : 'border-transparent text-gray-600 dark:text-slate-300 hover:text-gray-900 dark:hover:text-slate-100 hover:border-gray-300 dark:hover:border-slate-500'
                                    }`
                                }
                            >
                                {tab.label}
                            </NavLink>
                        ))}
                    </nav>
                </div>
            </div>
            <div className="flex-1 min-h-0 flex flex-col">
                <Outlet />
            </div>
        </div>
    );
}
