/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin-only user directory — first T2 pass. Lists First, Last, email, role
 *          split into Employees (users table) and Subcontractors (subcontractors table).
 *          Read-only; invite / permissions / reset / block come later.
 * exports:
 *   UserDirectory: Page component, admin-gated client-side; server also requires admin.
 * imports_from: [react, ../services/directoryApi, ../utils/auth]
 * imported_by: [App.jsx]
 * invariants:
 *   - Renders an access message (no fetch) unless the authenticated user is_admin.
 *   - Mirrors SubcontractorAdmin's mobile-first card list (below sm:) / table (sm:+)
 *     and token classes (canvas, surface, hairline, ink, head-bg).
 *   - Desktop tables share one table-fixed colgroup so Employees and Subcontractors
 *     columns line up (auto-sized tables drifted).
 */
import { useState, useEffect } from 'react';
import { fetchDirectory } from '../services/directoryApi';
import { checkAuth } from '../utils/auth';

const ROLE_BADGE = {
    Admin: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
    Drafter: 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300',
    Employee: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    Subcontractor: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
};

function display(value) {
    return value ? value : '—';
}

function fullName(row) {
    const parts = [row.first_name, row.last_name].filter(Boolean);
    return parts.length ? parts.join(' ') : '—';
}

function roleClass(role) {
    if (ROLE_BADGE[role]) return ROLE_BADGE[role];
    if (role && role.includes('Admin')) return ROLE_BADGE.Admin;
    if (role && role.includes('Drafter')) return ROLE_BADGE.Drafter;
    return ROLE_BADGE.Employee;
}

function RoleBadge({ role }) {
    return (
        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${roleClass(role)}`}>
            {display(role)}
        </span>
    );
}

// Shared so Employees and Subcontractors don't independently auto-size and
// drift (same reason Subs.jsx uses one table-fixed layout).
const COLGROUP = (
    <colgroup>
        <col style={{ width: '22%' }} />
        <col style={{ width: '22%' }} />
        <col />
        <col style={{ width: '10rem' }} />
    </colgroup>
);

function DirectorySection({ title, rows }) {
    return (
        <section className="mb-8">
            <div className="flex items-baseline gap-2 mb-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-3">{title}</h2>
                <span className="text-[11px] text-ink-3">{rows.length}</span>
            </div>

            {rows.length === 0 ? (
                <div className="rounded-xl border border-dashed border-hairline-strong p-8 text-center text-sm text-ink-3">
                    No {title.toLowerCase()} yet.
                </div>
            ) : (
                <>
                    <div className="sm:hidden space-y-2">
                        {rows.map((row) => (
                            <div key={row.id} className="rounded-xl border border-hairline bg-surface p-3">
                                <div className="flex items-center justify-between gap-2 mb-1.5">
                                    <span className="text-sm font-semibold text-ink">
                                        {fullName(row)}
                                    </span>
                                    <RoleBadge role={row.role} />
                                </div>
                                <div className="text-xs text-ink-3">{display(row.email)}</div>
                            </div>
                        ))}
                    </div>

                    <div className="hidden sm:block overflow-x-auto rounded-xl border border-hairline bg-surface">
                        <table className="w-full text-sm table-fixed">
                            {COLGROUP}
                            <thead className="bg-head-bg">
                                <tr>
                                    <th className="px-3 py-2 text-left font-semibold text-ink-3">First</th>
                                    <th className="px-3 py-2 text-left font-semibold text-ink-3">Last</th>
                                    <th className="px-3 py-2 text-left font-semibold text-ink-3">Email</th>
                                    <th className="px-3 py-2 text-left font-semibold text-ink-3">Role</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((row) => (
                                    <tr key={row.id} className="border-t border-hairline">
                                        <td className="px-3 py-2 text-ink truncate">{display(row.first_name)}</td>
                                        <td className="px-3 py-2 text-ink truncate">{display(row.last_name)}</td>
                                        <td className="px-3 py-2 text-ink-2 truncate">{display(row.email)}</td>
                                        <td className="px-3 py-2 whitespace-nowrap">
                                            <RoleBadge role={row.role} />
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </>
            )}
        </section>
    );
}

export default function UserDirectory() {
    const [authorized, setAuthorized] = useState(null);
    const [employees, setEmployees] = useState([]);
    const [subcontractors, setSubcontractors] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        checkAuth().then((user) => setAuthorized(!!(user && user.is_admin)));
    }, []);

    useEffect(() => {
        if (!authorized) return undefined;
        let cancelled = false;
        setLoading(true);
        setError(null);
        fetchDirectory()
            .then((data) => {
                if (cancelled) return;
                setEmployees(data.employees || []);
                setSubcontractors(data.subcontractors || []);
            })
            .catch(() => {
                if (!cancelled) setError('Failed to load users');
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => { cancelled = true; };
    }, [authorized]);

    if (authorized === null) {
        return (
            <div className="w-full min-h-[calc(100vh_-_var(--app-chrome-h))] bg-canvas p-6 text-ink-3">
                Loading…
            </div>
        );
    }
    if (!authorized) {
        return (
            <div className="w-full min-h-[calc(100vh_-_var(--app-chrome-h))] bg-canvas p-6 text-ink-2">
                Users is available to admins only.
            </div>
        );
    }

    return (
        <div className="w-full min-h-[calc(100vh_-_var(--app-chrome-h))] bg-canvas">
            <div className="flex-1 p-4 md:p-6 max-w-[1200px] mx-auto w-full">
                <h1 className="text-xl font-bold text-ink mb-4">Users</h1>

                {error && (
                    <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">
                        {error}
                    </div>
                )}

                {loading ? (
                    <div className="flex items-center justify-center py-16">
                        <span className="text-ink-3">Loading…</span>
                    </div>
                ) : (
                    <>
                        <DirectorySection title="Employees" rows={employees} />
                        <DirectorySection title="Subcontractors" rows={subcontractors} />
                    </>
                )}
            </div>
        </div>
    );
}
