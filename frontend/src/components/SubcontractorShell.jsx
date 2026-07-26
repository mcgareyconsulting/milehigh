/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Minimal layout + auth gate for subcontractor-facing pages — just a header (company
 *          name, logout) and an Outlet, nothing like AppShell's nav bar. Self-contained auth
 *          check (unlike AppShell, which relies on App.jsx's top-level isAuthenticated state)
 *          because subcontractor routes are a separate top-level route tree in App.jsx, not
 *          nested under the internal-staff AppShell.
 * exports:
 *   SubcontractorShell: Layout shell, renders child routes via Outlet once authenticated.
 * imports_from: [react, react-router-dom, ../utils/subcontractorAuth]
 * imported_by: [frontend/src/App.jsx]
 * invariants:
 *   - Redirects to /sub/login if checkSubcontractorAuth() returns null — never falls back to
 *     the internal /login page, keeping the two identity spaces visually separate too.
 */
import { useState, useEffect } from 'react';
import { useNavigate, Outlet } from 'react-router-dom';
import { checkSubcontractorAuth, subcontractorLogout } from '../utils/subcontractorAuth';

export default function SubcontractorShell() {
    const navigate = useNavigate();
    const [subcontractor, setSubcontractor] = useState(null);
    const [loading, setLoading] = useState(true);

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

    const handleLogout = async () => {
        await subcontractorLogout();
        navigate('/sub/login', { replace: true });
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[#f8fafc] dark:bg-slate-900">
                <div className="text-gray-600 dark:text-slate-400">Loading…</div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#f8fafc] dark:bg-slate-900">
            <header className="flex items-center justify-between gap-3 px-4 py-3 border-b border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                <div className="min-w-0">
                    <div className="text-sm font-semibold text-gray-900 dark:text-slate-100 truncate">{subcontractor?.company_name}</div>
                    <div className="text-xs text-gray-500 dark:text-slate-400 truncate">{subcontractor?.contact_name}</div>
                </div>
                <button onClick={handleLogout}
                    className="shrink-0 px-3 py-1.5 text-sm font-medium rounded-lg border border-gray-300 dark:border-slate-600 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-700">
                    Logout
                </button>
            </header>
            <Outlet />
        </div>
    );
}
