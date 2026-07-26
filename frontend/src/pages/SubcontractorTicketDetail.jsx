/**
 * @milehigh-header
 * schema_version: 1
 * purpose: A subcontractor's view of one assigned T&M ticket — read-only header context (job/
 *          date/location/GC/foreman/customer, set by the PM who seeded it), editable work
 *          description/labor/materials/equipment/signature while still a draft, and a Submit
 *          action that hands it back to the originator. Reuses LineItemTable from
 *          tmLineItems.jsx rather than forking it — the admin TMTicketFormModal.jsx's outer
 *          shell isn't reused (wired to admin-only endpoints/release-picker/modal-over-AppShell
 *          UX that doesn't apply here), but the field-agnostic line-item editor is identical.
 * exports:
 *   SubcontractorTicketDetail: Page component, rendered inside SubcontractorShell's Outlet.
 * imports_from: [react, react-router-dom, ../services/subcontractorTmApi, ../components/tmLineItems, ../components/tmFieldHelpers]
 * imported_by: [App.jsx]
 * invariants:
 *   - readOnly = ticket.status !== 'draft', matching TMTicketFormModal.jsx's same rule.
 *   - Photos/videos are view-only here — upload stays admin-only (see plan notes on the
 *     TMTicketAttachment.uploaded_by_user_id NOT NULL schema tension).
 */
import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    getAssignedTicket, updateAssignedTicket, submitAssignedTicket,
    listAssignedTicketAttachments, assignedTicketAttachmentFileUrl,
} from '../services/subcontractorTmApi';
import { LineItemTable } from '../components/tmLineItems';
import { emptyLabor, emptyMaterial, emptyEquipment, inputClass, labelClass } from '../components/tmFieldHelpers';

const STATUS_LABEL = {
    draft: 'Draft', submitted: 'Submitted', pending_approval: 'Pending approval',
    approved: 'Approved', co_generated: 'CO generated', co_sent: 'CO sent',
    co_approved: 'CO approved', invoiced: 'Invoiced',
};

const readOnlyValueClass = 'text-sm text-gray-900 dark:text-slate-100';

function ReadOnlyField({ label, value }) {
    return (
        <div className="min-w-0">
            <span className={labelClass}>{label}</span>
            <div className={readOnlyValueClass}>{value || '—'}</div>
        </div>
    );
}

export default function SubcontractorTicketDetail() {
    const { id } = useParams();
    const navigate = useNavigate();

    const [ticket, setTicket] = useState(null);
    const [attachments, setAttachments] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [saving, setSaving] = useState(false);

    const [workDescription, setWorkDescription] = useState('');
    const [labor, setLabor] = useState([]);
    const [materials, setMaterials] = useState([]);
    const [equipment, setEquipment] = useState([]);
    const [signaturePresent, setSignaturePresent] = useState(false);
    const [signatureName, setSignatureName] = useState('');

    const load = useCallback(async () => {
        setError(null);
        try {
            const [ticketData, attachmentData] = await Promise.all([
                getAssignedTicket(id),
                listAssignedTicketAttachments(id),
            ]);
            const t = ticketData.ticket;
            setTicket(t);
            setWorkDescription(t.work_description || '');
            setLabor((t.labor || []).map(l => ({ ...emptyLabor(), ...l })));
            setMaterials((t.materials || []).map(m => ({ ...emptyMaterial(), ...m })));
            setEquipment((t.equipment || []).map(e => ({ ...emptyEquipment(), ...e })));
            setSignaturePresent(!!t.signature_present);
            setSignatureName(t.signature_name || '');
            setAttachments(attachmentData.attachments || []);
        } catch {
            setError('Failed to load ticket');
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => { setLoading(true); load(); }, [load]);

    const readOnly = !ticket || ticket.status !== 'draft';

    const updateRow = (setter, idx, patch) => setter(prev => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
    const addRow = (setter, factory) => setter(prev => [...prev, factory()]);
    const removeRow = (setter, idx) => setter(prev => prev.filter((_, i) => i !== idx));

    const handleSave = async () => {
        setSaving(true); setError(null);
        try {
            await updateAssignedTicket(id, {
                work_description: workDescription, labor, materials, equipment,
                signature_present: signaturePresent, signature_name: signatureName,
            });
            await load();
        } catch (err) {
            setError(err?.response?.data?.error || 'Failed to save');
        } finally {
            setSaving(false);
        }
    };

    const handleSubmit = async () => {
        if (!window.confirm('Submit this ticket back to MHMW? You won’t be able to edit it after.')) return;
        setSaving(true); setError(null);
        try {
            await handleSave();
            await submitAssignedTicket(id);
            await load();
        } catch (err) {
            setError(err?.response?.data?.error || 'Failed to submit');
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-16">
                <span className="text-gray-500 dark:text-slate-400">Loading…</span>
            </div>
        );
    }

    if (!ticket) {
        return (
            <div className="flex-1 p-4 md:p-6 max-w-[800px] mx-auto w-full">
                <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">
                    {error || 'Ticket not found'}
                </div>
                <button onClick={() => navigate('/sub/tickets')} className="text-sm text-accent-600 dark:text-accent-400 hover:underline">
                    Back to tickets
                </button>
            </div>
        );
    }

    return (
        <div className="flex-1 w-full">
        <div className="p-4 md:p-6 max-w-[800px] mx-auto w-full">
            <button onClick={() => navigate('/sub/tickets')} className="text-sm text-accent-600 dark:text-accent-400 hover:underline mb-3">
                ← Back to tickets
            </button>

            <div className="flex items-center justify-between gap-3 mb-4">
                <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100">
                    {ticket.release ? `${ticket.release.job}-${ticket.release.release}` : (ticket.job ?? `Ticket #${ticket.id}`)}
                </h1>
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 text-gray-700 dark:bg-slate-700 dark:text-slate-300">
                    {STATUS_LABEL[ticket.status] || ticket.status}
                </span>
            </div>

            {error && (
                <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">{error}</div>
            )}
            {readOnly && (
                <div className="mb-4 px-3 py-2 rounded-lg bg-gray-50 border border-gray-200 text-gray-600 dark:bg-slate-900/40 dark:border-slate-700 dark:text-slate-300 text-sm">
                    This ticket is {(STATUS_LABEL[ticket.status] || ticket.status).toLowerCase()} — no longer editable.
                </div>
            )}

            <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3 p-3 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                    <ReadOnlyField label="Date of work" value={ticket.date_of_work} />
                    <ReadOnlyField label="Location" value={ticket.location} />
                    <ReadOnlyField label="GC company" value={ticket.gc_company} />
                    <ReadOnlyField label="GC contact" value={ticket.gc_contact_name} />
                    <ReadOnlyField label="Foreman" value={ticket.foreman_name} />
                    <ReadOnlyField label="Customer" value={ticket.customer} />
                </div>

                <div>
                    <label className={labelClass}>Work description</label>
                    <textarea rows={3} value={workDescription} disabled={readOnly}
                        onChange={e => setWorkDescription(e.target.value)} className={inputClass} />
                </div>

                <LineItemTable
                    title="Labor" readOnly={readOnly}
                    columns={[
                        { key: 'name', label: 'Name', wide: true },
                        { key: 'company', label: 'Company' },
                        { key: 'classification', label: 'Classification' },
                        { key: 'hours_reg', label: 'Reg', numeric: true },
                        { key: 'hours_ot', label: 'OT', numeric: true },
                        { key: 'hours_dt', label: 'DT', numeric: true },
                        { key: 'notes', label: 'Notes', wide: true },
                    ]}
                    rows={labor}
                    onChange={(idx, patch) => updateRow(setLabor, idx, patch)}
                    onAdd={() => addRow(setLabor, emptyLabor)}
                    onRemove={(idx) => removeRow(setLabor, idx)}
                />

                <LineItemTable
                    title="Materials" readOnly={readOnly}
                    columns={[
                        { key: 'description', label: 'Description', wide: true },
                        { key: 'quantity', label: 'Qty', numeric: true },
                        { key: 'unit', label: 'Unit' },
                        { key: 'length', label: 'Length' },
                        { key: 'notes', label: 'Notes', wide: true },
                    ]}
                    rows={materials}
                    onChange={(idx, patch) => updateRow(setMaterials, idx, patch)}
                    onAdd={() => addRow(setMaterials, emptyMaterial)}
                    onRemove={(idx) => removeRow(setMaterials, idx)}
                />

                <LineItemTable
                    title="Equipment" readOnly={readOnly}
                    columns={[
                        { key: 'description', label: 'Description', wide: true },
                        { key: 'quantity', label: 'Qty', numeric: true },
                        { key: 'hours', label: 'Hours', numeric: true },
                        { key: 'operator', label: 'Operator' },
                        { key: 'notes', label: 'Notes', wide: true },
                    ]}
                    rows={equipment}
                    onChange={(idx, patch) => updateRow(setEquipment, idx, patch)}
                    onAdd={() => addRow(setEquipment, emptyEquipment)}
                    onRemove={(idx) => removeRow(setEquipment, idx)}
                />

                <div>
                    <h4 className="text-xs font-semibold text-gray-600 dark:text-slate-300 mb-1.5">
                        Photos &amp; videos{attachments.length > 0 ? ` (${attachments.length})` : ''}
                    </h4>
                    {attachments.length === 0 ? (
                        <div className="rounded-lg border border-dashed border-gray-200 dark:border-slate-700 px-3 py-3 text-center text-xs text-gray-400 dark:text-slate-500">
                            No photos or videos on this ticket.
                        </div>
                    ) : (
                        <div className="grid grid-cols-3 gap-2">
                            {attachments.map(a => (
                                <a key={a.id} href={assignedTicketAttachmentFileUrl(id, a.id)} target="_blank" rel="noopener noreferrer">
                                    {a.is_video ? (
                                        <div className="w-full h-20 flex flex-col items-center justify-center gap-0.5 rounded-md border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700">
                                            <span className="text-lg">▶</span>
                                            <span className="text-[10px] text-gray-500 dark:text-slate-400 truncate max-w-full px-1">{a.original_filename || 'video'}</span>
                                        </div>
                                    ) : (
                                        <img src={assignedTicketAttachmentFileUrl(id, a.id)} alt={a.original_filename || 'photo'}
                                            className="w-full h-20 object-cover rounded-md border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700" />
                                    )}
                                </a>
                            ))}
                        </div>
                    )}
                </div>

                <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                    <label className="flex items-center gap-2.5 text-sm text-gray-700 dark:text-slate-200 py-1">
                        <input type="checkbox" checked={signaturePresent} disabled={readOnly}
                            onChange={e => setSignaturePresent(e.target.checked)} className="w-5 h-5 shrink-0" />
                        Signature present
                    </label>
                    <input type="text" placeholder="Signature name" value={signatureName} disabled={readOnly}
                        onChange={e => setSignatureName(e.target.value)}
                        className={`${inputClass} flex-1 sm:min-w-[160px]`} />
                </div>
            </div>
        </div>

            {/* sticky, NOT fixed: a fixed footer sits outside normal document flow and
                contributes nothing to scrollHeight, so it can permanently overlap trailing
                content no matter how much padding-bottom is guessed elsewhere on the page —
                exactly the bug reported here. sticky reserves its own real space in the flow,
                so the browser guarantees the signature field above it is always fully
                scrollable into view before the bar comes to rest below it. */}
            {!readOnly && (
                <div className="sticky bottom-0 border-t border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                    <div className="flex gap-2 p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] max-w-[800px] mx-auto w-full">
                        <button onClick={handleSave} disabled={saving}
                            className="flex-1 px-4 py-3 text-sm font-medium rounded-lg border border-gray-300 dark:border-slate-600 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50">
                            {saving ? 'Saving…' : 'Save'}
                        </button>
                        <button onClick={handleSubmit} disabled={saving}
                            className="flex-1 px-4 py-3 text-sm font-medium rounded-lg bg-green-600 hover:bg-green-700 text-white disabled:opacity-50">
                            Submit
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
