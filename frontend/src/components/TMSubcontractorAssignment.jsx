/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Assign/unassign subcontractors sharing a T&M ticket — "PM/lead shares it to the
 *          person doing the work" (2026-07-22 ops meeting). A checkbox list of the roster,
 *          not a dropdown-plus-confirm-button: checking a box IS the assign/unassign action,
 *          so adding several subcontractors at once is just ticking several boxes. Only
 *          active, invite-accepted subcontractors are selectable; roster management itself
 *          lives on pages/SubcontractorAdmin.jsx, not here.
 * exports:
 *   TMSubcontractorAssignment: Self-contained section. Props: ticketId (null = create/staged
 *     mode), readOnly, stagedIds/onStage/onUnstage (create mode only — see invariants).
 * imports_from: [react, ../services/subcontractorAdminApi]
 * imported_by: [components/TMTicketFormModal.jsx]
 * invariants:
 *   - Edit mode (ticketId set): owns its own fetch/state, hits the assign/unassign API
 *     immediately per checkbox toggle, matches TMTicketAttachments.jsx.
 *   - Create mode (ticketId null): there's no ticket row yet to assign against, so toggling a
 *     checkbox is just a parent-controlled array edit (stagedIds/onStage/onUnstage) — no
 *     network call, no email, happens here. The parent creates the real assignments (which is
 *     what actually triggers the assignment-notification email — see command.py) via
 *     assignSubcontractor() only once the ticket itself is saved, mirroring the
 *     staged-attachment-upload pattern in TMTicketFormModal.jsx.
 */
import { useState, useEffect, useCallback } from 'react';
import {
    listTicketSubcontractors, listSubcontractors, assignSubcontractor, unassignSubcontractor,
} from '../services/subcontractorAdminApi';

export default function TMSubcontractorAssignment({ ticketId, readOnly, stagedIds, onStage, onUnstage }) {
    const isCreate = !ticketId;
    const [assignments, setAssignments] = useState([]);
    const [roster, setRoster] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busyId, setBusyId] = useState(null);
    const [error, setError] = useState(null);

    const load = useCallback(async () => {
        try {
            const [assignedData, rosterData] = await Promise.all([
                isCreate ? Promise.resolve({ subcontractors: [] }) : listTicketSubcontractors(ticketId),
                listSubcontractors(),
            ]);
            setAssignments(assignedData.subcontractors || []);
            setRoster(rosterData.subcontractors || []);
        } catch {
            setError('Failed to load subcontractor assignments');
        } finally {
            setLoading(false);
        }
    }, [ticketId, isCreate]);

    useEffect(() => { setLoading(true); load(); }, [load]);

    const assignedIds = new Set(isCreate ? (stagedIds || []) : assignments.map(a => a.subcontractor_id));
    const selectableRoster = roster.filter(s => s.is_active && s.invite_accepted);

    const toggle = async (sub, checked) => {
        if (isCreate) {
            checked ? onStage?.(sub.id) : onUnstage?.(sub.id);
            return;
        }
        setBusyId(sub.id); setError(null);
        try {
            if (checked) {
                await assignSubcontractor(ticketId, sub.id);
            } else {
                await unassignSubcontractor(ticketId, sub.id);
            }
            await load();
        } catch (err) {
            setError(err?.response?.data?.error || `Failed to ${checked ? 'assign' : 'unassign'} subcontractor`);
        } finally {
            setBusyId(null);
        }
    };

    return (
        <div>
            <h4 className="text-xs font-semibold text-gray-600 dark:text-slate-300 mb-1.5">
                Shared with{assignedIds.size > 0 ? ` (${assignedIds.size})` : ''}
            </h4>

            {error && (
                <div className="mb-1.5 text-xs text-red-600 dark:text-red-400">{error}</div>
            )}

            {loading ? (
                <div className="text-xs text-gray-400 dark:text-slate-500 py-1">Loading…</div>
            ) : selectableRoster.length === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-200 dark:border-slate-700 px-3 py-3 text-center text-xs text-gray-400 dark:text-slate-500">
                    No active subcontractors on the roster yet — invite one from the Subcontractors page.
                </div>
            ) : (
                <div className="space-y-1.5">
                    {selectableRoster.map(s => (
                        <label key={s.id}
                            className={`flex items-center gap-2.5 rounded-lg border border-gray-200 dark:border-slate-700 px-3 py-2 ${readOnly ? '' : 'cursor-pointer hover:bg-gray-50 dark:hover:bg-slate-700/50'}`}>
                            <input type="checkbox" checked={assignedIds.has(s.id)} disabled={readOnly || busyId === s.id}
                                onChange={e => toggle(s, e.target.checked)}
                                className="w-4 h-4 shrink-0" />
                            <div className="min-w-0 flex-1">
                                <div className="text-sm text-gray-900 dark:text-slate-100 truncate">{s.contact_name} — {s.company_name}</div>
                                <div className="text-xs text-gray-500 dark:text-slate-400 truncate">{s.email}</div>
                            </div>
                        </label>
                    ))}
                </div>
            )}
            {isCreate && !loading && selectableRoster.length > 0 && (
                <p className="mt-1.5 text-[11px] text-gray-400 dark:text-slate-500">
                    Checked subcontractors are notified once this ticket is created.
                </p>
            )}
        </div>
    );
}
