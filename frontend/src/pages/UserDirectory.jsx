/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin-only user directory + permissions management. Lists First, Last,
 *          email, role split into Employees (users table) and Subcontractors
 *          (subcontractors table). Employee role is editable in place —
 *          Admin / Drafter / Default; subcontractors are read-only.
 * exports:
 *   UserDirectory: Page component, admin-gated client-side; server also requires admin.
 * imports_from: [react, ../services/directoryApi, ../utils/auth]
 * imported_by: [App.jsx]
 * invariants:
 *   - Renders an access message (no fetch) unless the authenticated user is_admin.
 *   - Roles are mutually exclusive (one of admin/drafter/default) and only apply to
 *     employees; the Subcontractor group has no permission control and is unaffected.
 *   - The signed-in admin's own row is not editable (the server rejects it too, so the
 *     disabled control is a courtesy, never the authorization).
 *   - Role changes save immediately and optimistically; a failed PATCH reverts the row
 *     and surfaces the server's message.
 *   - Mirrors SubcontractorAdmin's mobile-first card list (below sm:) / table (sm:+)
 *     and token classes (canvas, surface, hairline, ink, head-bg).
 *   - Desktop tables share one table-fixed colgroup so Employees and Subcontractors
 *     columns line up (auto-sized tables drifted).
 */
import { useState, useEffect } from 'react';
import { fetchDirectory, updateEmployeeRole } from '../services/directoryApi';
import { checkAuth } from '../utils/auth';

const ROLE_BADGE = {
    Admin: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
    Drafter: 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300',
    Default: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    Subcontractor: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
};

// Fallback if the server response predates the `roles` key.
const DEFAULT_ROLES = [
    { key: 'admin', label: 'Admin' },
    { key: 'drafter', label: 'Drafter' },
    { key: 'default', label: 'Default' },
];

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
    return ROLE_BADGE.Default;
}

function RoleBadge({ role }) {
    return (
        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${roleClass(role)}`}>
            {display(role)}
        </span>
    );
}

// The editable permission control. A bare <select> rather than a modal: role is the
// only writable field on the row, so a round-trip through a dialog buys nothing.
//
// The control carries its OWN role's tint, drawn from the same ROLE_BADGE palette the badge uses,
// so a directory of thirty people can be scanned for admins at a glance instead of read row by row.
// The tint is on the control, not the <option>s: option background/colour is honoured by Firefox
// and ignored by Safari and Chrome on macOS, so styling them would look broken for most of the
// company. Each option keeps a •-prefixed label instead, which every browser does render.
function RoleSelect({ row, roles, disabled, pending, onChange }) {
    const currentKey = row.role_key || 'default';
    const currentLabel = roles.find((r) => r.key === currentKey)?.label || row.role;
    return (
        <select
            aria-label={`Role for ${fullName(row)}`}
            className={`w-full max-w-[9rem] rounded-lg border border-hairline px-2 py-1 text-xs font-semibold
                        focus:outline-none focus:ring-2 focus:ring-accent-500 ${roleClass(currentLabel)}
                        ${disabled || pending ? 'opacity-60 cursor-not-allowed' : ''}`}
            value={currentKey}
            disabled={disabled || pending}
            title={disabled ? 'You cannot change your own role' : undefined}
            onChange={(e) => onChange(row, e.target.value)}
        >
            {roles.map((r) => (
                <option key={r.key} value={r.key}>{r.label}</option>
            ))}
        </select>
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

function DirectorySection({ title, rows, editableRoles, roles, currentUserId, pendingIds, onRoleChange }) {
    const renderRole = (row) => {
        if (!editableRoles) return <RoleBadge role={row.role} />;
        return (
            <RoleSelect
                row={row}
                roles={roles}
                disabled={row.id === currentUserId}
                pending={pendingIds.has(row.id)}
                onChange={onRoleChange}
            />
        );
    };

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
                                    {renderRole(row)}
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
                                            {renderRole(row)}
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
    const [currentUserId, setCurrentUserId] = useState(null);
    const [employees, setEmployees] = useState([]);
    const [subcontractors, setSubcontractors] = useState([]);
    const [roles, setRoles] = useState(DEFAULT_ROLES);
    const [pendingIds, setPendingIds] = useState(new Set());
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        checkAuth().then((user) => {
            setAuthorized(!!(user && user.is_admin));
            setCurrentUserId(user ? user.id : null);
        });
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
                if (data.roles && data.roles.length) setRoles(data.roles);
            })
            .catch(() => {
                if (!cancelled) setError('Failed to load users');
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => { cancelled = true; };
    }, [authorized]);

    const markPending = (id, on) => {
        setPendingIds((prev) => {
            const next = new Set(prev);
            if (on) next.add(id); else next.delete(id);
            return next;
        });
    };

    const handleRoleChange = async (row, roleKey) => {
        if (roleKey === row.role_key) return;
        const previous = { role: row.role, role_key: row.role_key };
        const label = (roles.find((r) => r.key === roleKey) || {}).label || roleKey;

        setError(null);
        markPending(row.id, true);
        // Optimistic: the select must not snap back to the old value while in flight.
        setEmployees((prev) => prev.map((e) => (
            e.id === row.id ? { ...e, role_key: roleKey, role: label } : e
        )));

        try {
            const updated = await updateEmployeeRole(row.id, roleKey);
            setEmployees((prev) => prev.map((e) => (
                e.id === row.id ? { ...e, ...updated } : e
            )));
        } catch (err) {
            setEmployees((prev) => prev.map((e) => (
                e.id === row.id ? { ...e, ...previous } : e
            )));
            setError(err?.response?.data?.error || 'Failed to update role');
        } finally {
            markPending(row.id, false);
        }
    };

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
                        <DirectorySection
                            title="Employees"
                            rows={employees}
                            editableRoles
                            roles={roles}
                            currentUserId={currentUserId}
                            pendingIds={pendingIds}
                            onRoleChange={handleRoleChange}
                        />
                        <DirectorySection
                            title="Subcontractors"
                            rows={subcontractors}
                            editableRoles={false}
                            roles={roles}
                            currentUserId={currentUserId}
                            pendingIds={pendingIds}
                            onRoleChange={handleRoleChange}
                        />
                    </>
                )}
            </div>
        </div>
    );
}
