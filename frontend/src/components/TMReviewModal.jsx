/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Two-pane review modal for a T&M ticket — original document on the left,
 *          editable AI-extracted fields (with low-confidence highlighting) on the right.
 *          Confirm persists the reviewer's edits + release link; Reject discards the ticket.
 * exports:
 *   TMReviewModal: Portal modal. Props: isOpen, ticket, releaseCandidates, onClose, onSaved.
 * imports_from: [react, react-dom, ../services/tmApi]
 * imported_by: [pages/TMTickets.jsx]
 * invariants:
 *   - Read-only once ticket.status !== 'pending_review'; Confirm/Reject only render while pending.
 *   - Re-fetches release candidates whenever the job number field changes to a valid integer.
 *   - Closes on backdrop click and Escape, matching the other modals (ReleaseDetailModal, etc).
 */
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { confirmTicket, rejectTicket, getReleaseCandidates, ticketFileUrl } from '../services/tmApi';

const STATUS_LABEL = {
    pending_review: 'Pending review',
    confirmed: 'Confirmed',
    rejected: 'Rejected',
};

const STATUS_BADGE = {
    pending_review: 'bg-gray-100 text-gray-700 dark:bg-slate-700 dark:text-slate-300',
    confirmed: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    rejected: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
};

const emptyLabor = () => ({ name: '', company: '', classification: '', hours_reg: '', hours_ot: '', hours_dt: '', notes: '' });
const emptyMaterial = () => ({ description: '', quantity: '', unit: '', length: '', notes: '' });
const emptyEquipment = () => ({ description: '', quantity: '', hours: '', operator: '', notes: '' });

function isLowConfidence(ticket, key) {
    const c = ticket?.raw_extraction?.confidence?.[key];
    return typeof c === 'number' && c < 0.8;
}

function fieldClass(low, extra = '') {
    return `w-full px-3 py-2 text-sm rounded-lg border disabled:opacity-70 ${low
        ? 'border-amber-400 dark:border-amber-600 bg-amber-50 dark:bg-amber-900/20'
        : 'border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900'
        } text-gray-900 dark:text-slate-100 ${extra}`;
}

function ConfidenceHint({ low }) {
    if (!low) return null;
    return <span className="ml-1.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">check this</span>;
}

function StatusBadge({ status }) {
    return (
        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${STATUS_BADGE[status] || STATUS_BADGE.pending_review}`}>
            {STATUS_LABEL[status] || status}
        </span>
    );
}

function LineItemTable({ title, low, readOnly, columns, rows, onChange, onAdd, onRemove }) {
    return (
        <div>
            <div className="flex items-center justify-between mb-1">
                <h4 className="text-xs font-semibold text-gray-600 dark:text-slate-300">
                    {title} <ConfidenceHint low={low} />
                </h4>
                {!readOnly && (
                    <button type="button" onClick={onAdd}
                        className="text-[11px] px-2 py-0.5 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700">
                        + Add row
                    </button>
                )}
            </div>
            <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-slate-700">
                <table className="min-w-full text-xs">
                    <thead className={low ? 'bg-amber-50 dark:bg-amber-900/20' : 'bg-gray-50 dark:bg-slate-900/40'}>
                        <tr>
                            {columns.map(c => (
                                <th key={c.key} className="px-2 py-1.5 text-left font-medium text-gray-500 dark:text-slate-400 whitespace-nowrap">{c.label}</th>
                            ))}
                            {!readOnly && <th className="px-2 py-1.5" />}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.length === 0 ? (
                            <tr>
                                <td colSpan={columns.length + (readOnly ? 0 : 1)} className="px-2 py-2 text-center text-gray-400 dark:text-slate-500">
                                    No rows
                                </td>
                            </tr>
                        ) : rows.map((row, idx) => (
                            <tr key={idx} className="border-t border-gray-100 dark:border-slate-800">
                                {columns.map(c => (
                                    <td key={c.key} className="px-1 py-1">
                                        <input
                                            type={c.numeric ? 'number' : 'text'}
                                            value={row[c.key] ?? ''}
                                            disabled={readOnly}
                                            onChange={e => onChange(idx, { [c.key]: e.target.value })}
                                            className="w-full min-w-[70px] px-1.5 py-1 text-xs rounded border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100 disabled:opacity-70"
                                        />
                                    </td>
                                ))}
                                {!readOnly && (
                                    <td className="px-1 py-1">
                                        <button type="button" onClick={() => onRemove(idx)} title="Remove row"
                                            className="text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 text-xs px-1">✕</button>
                                    </td>
                                )}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

export default function TMReviewModal({ isOpen, ticket, releaseCandidates: initialCandidates, onClose, onSaved }) {
    const [job, setJob] = useState('');
    const [dateOfWork, setDateOfWork] = useState('');
    const [customer, setCustomer] = useState('');
    const [workDescription, setWorkDescription] = useState('');
    const [labor, setLabor] = useState([]);
    const [materials, setMaterials] = useState([]);
    const [equipment, setEquipment] = useState([]);
    const [signaturePresent, setSignaturePresent] = useState(false);
    const [signatureName, setSignatureName] = useState('');
    const [releaseId, setReleaseId] = useState('');
    const [candidates, setCandidates] = useState([]);
    const [candidatesLoading, setCandidatesLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);

    const readOnly = !!ticket && ticket.status !== 'pending_review';

    // Seed the form whenever a (new) ticket is opened.
    useEffect(() => {
        if (!ticket) return;
        setJob(ticket.job != null ? String(ticket.job) : '');
        setDateOfWork(ticket.date_of_work || '');
        setCustomer(ticket.customer || '');
        setWorkDescription(ticket.work_description || '');
        setLabor((ticket.labor || []).map(l => ({ ...emptyLabor(), ...l })));
        setMaterials((ticket.materials || []).map(m => ({ ...emptyMaterial(), ...m })));
        setEquipment((ticket.equipment || []).map(e => ({ ...emptyEquipment(), ...e })));
        setSignaturePresent(!!ticket.signature_present);
        setSignatureName(ticket.signature_name || '');
        setReleaseId(ticket.release_id != null ? String(ticket.release_id) : '');
        setCandidates(initialCandidates || (ticket.release ? [ticket.release] : []));
        setError(null);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [ticket?.id]);

    // Escape-to-close.
    useEffect(() => {
        if (!isOpen) return undefined;
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);

    // Re-fetch release candidates whenever the job number field changes to a valid integer.
    useEffect(() => {
        const jobNum = parseInt(job, 10);
        if (!job.trim() || isNaN(jobNum)) return undefined;
        let cancelled = false;
        setCandidatesLoading(true);
        getReleaseCandidates(jobNum)
            .then(d => { if (!cancelled) setCandidates(d.candidates || []); })
            .catch(() => { if (!cancelled) setCandidates([]); })
            .finally(() => { if (!cancelled) setCandidatesLoading(false); });
        return () => { cancelled = true; };
    }, [job]);

    if (!isOpen || !ticket) return null;

    const mediaType = ticket.source_media_type || '';
    const isImage = mediaType.startsWith('image/');
    const fileUrl = ticketFileUrl(ticket.id);

    const updateRow = (setter, idx, patch) => setter(prev => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
    const addRow = (setter, factory) => setter(prev => [...prev, factory()]);
    const removeRow = (setter, idx) => setter(prev => prev.filter((_, i) => i !== idx));

    const handleConfirm = async () => {
        setSaving(true); setError(null);
        try {
            await confirmTicket(ticket.id, {
                job: job.trim() ? parseInt(job, 10) : null,
                date_of_work: dateOfWork || null,
                customer,
                work_description: workDescription,
                labor,
                materials,
                equipment,
                signature_present: signaturePresent,
                signature_name: signatureName,
                release_id: releaseId ? parseInt(releaseId, 10) : null,
            });
            onSaved?.();
            onClose();
        } catch (err) {
            setError(err?.response?.data?.error || 'Failed to confirm ticket');
        } finally {
            setSaving(false);
        }
    };

    const handleReject = async () => {
        if (!window.confirm('Reject this ticket? It will no longer show as pending review.')) return;
        setSaving(true); setError(null);
        try {
            await rejectTicket(ticket.id);
            onSaved?.();
            onClose();
        } catch (err) {
            setError(err?.response?.data?.error || 'Failed to reject ticket');
        } finally {
            setSaving(false);
        }
    };

    const modalContent = (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
            <div
                className="w-full max-w-6xl max-h-[92vh] overflow-y-auto rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-2xl"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-gray-200 dark:border-slate-700">
                    <div className="flex items-center gap-2 min-w-0">
                        <h2 className="text-lg font-bold text-gray-900 dark:text-slate-100 truncate">T&amp;M Ticket #{ticket.id}</h2>
                        <StatusBadge status={ticket.status} />
                    </div>
                    <button onClick={onClose} aria-label="Close" className="shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-slate-200 text-2xl leading-none">×</button>
                </div>

                {ticket.extract_error && (
                    <div className="mx-5 mt-4 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 dark:bg-amber-900/20 dark:border-amber-700 dark:text-amber-300 text-sm">
                        Automatic extraction failed — enter fields manually. <span className="opacity-75">{ticket.extract_error}</span>
                    </div>
                )}
                {error && (
                    <div className="mx-5 mt-4 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">{error}</div>
                )}
                {readOnly && (
                    <div className="mx-5 mt-4 px-3 py-2 rounded-lg bg-gray-50 border border-gray-200 text-gray-600 dark:bg-slate-900/40 dark:border-slate-700 dark:text-slate-300 text-sm">
                        This ticket is {(STATUS_LABEL[ticket.status] || ticket.status).toLowerCase()} — fields are read-only.
                    </div>
                )}

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 p-5">
                    {/* LEFT: original document preview */}
                    <div className="min-w-0">
                        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500 mb-2">Original document</h3>
                        <div className="rounded-lg border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-900/40 overflow-auto max-h-[45vh] lg:max-h-[75vh]">
                            {isImage ? (
                                <img src={fileUrl} alt={`T&M ticket #${ticket.id} document`} className="w-full h-auto" />
                            ) : (
                                <iframe
                                    title={`T&M ticket #${ticket.id} document`}
                                    src={fileUrl}
                                    className="w-full"
                                    style={{ height: '70vh', border: 'none' }}
                                />
                            )}
                        </div>
                        <p className="mt-1 text-[11px] text-gray-400 dark:text-slate-500 truncate">
                            {ticket.source_filename}{ticket.uploaded_by ? ` · uploaded by ${ticket.uploaded_by}` : ''}
                        </p>
                    </div>

                    {/* RIGHT: editable extracted fields */}
                    <div className="space-y-4 min-w-0">
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <label className="block text-xs font-medium text-gray-600 dark:text-slate-300 mb-1">
                                    Job number <ConfidenceHint low={isLowConfidence(ticket, 'job_number')} />
                                </label>
                                <input
                                    type="text" inputMode="numeric" value={job} disabled={readOnly}
                                    onChange={e => setJob(e.target.value)}
                                    className={fieldClass(isLowConfidence(ticket, 'job_number'))}
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-gray-600 dark:text-slate-300 mb-1">
                                    Date of work <ConfidenceHint low={isLowConfidence(ticket, 'date_of_work')} />
                                </label>
                                <input
                                    type="date" value={dateOfWork || ''} disabled={readOnly}
                                    onChange={e => setDateOfWork(e.target.value)}
                                    className={fieldClass(isLowConfidence(ticket, 'date_of_work'))}
                                />
                            </div>
                        </div>

                        <div>
                            <label className="block text-xs font-medium text-gray-600 dark:text-slate-300 mb-1">
                                Customer <ConfidenceHint low={isLowConfidence(ticket, 'customer')} />
                            </label>
                            <input
                                type="text" value={customer} disabled={readOnly}
                                onChange={e => setCustomer(e.target.value)}
                                className={fieldClass(isLowConfidence(ticket, 'customer'))}
                            />
                        </div>

                        <div>
                            <label className="block text-xs font-medium text-gray-600 dark:text-slate-300 mb-1">
                                Work description <ConfidenceHint low={isLowConfidence(ticket, 'work_description')} />
                            </label>
                            <textarea
                                rows={3} value={workDescription} disabled={readOnly}
                                onChange={e => setWorkDescription(e.target.value)}
                                className={fieldClass(isLowConfidence(ticket, 'work_description'))}
                            />
                        </div>

                        <div>
                            <label className="block text-xs font-medium text-gray-600 dark:text-slate-300 mb-1">Release (optional)</label>
                            <select
                                value={releaseId} disabled={readOnly}
                                onChange={e => setReleaseId(e.target.value)}
                                className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100 disabled:opacity-70"
                            >
                                <option value="">None</option>
                                {candidates.map(c => (
                                    <option key={c.id} value={c.id}>{c.job}-{c.release} — {c.job_name}</option>
                                ))}
                            </select>
                            {candidatesLoading && <p className="mt-1 text-[11px] text-gray-400 dark:text-slate-500">Loading releases…</p>}
                        </div>

                        <LineItemTable
                            title="Labor" low={isLowConfidence(ticket, 'labor')} readOnly={readOnly}
                            columns={[
                                { key: 'name', label: 'Name' },
                                { key: 'company', label: 'Company' },
                                { key: 'classification', label: 'Classification' },
                                { key: 'hours_reg', label: 'Reg', numeric: true },
                                { key: 'hours_ot', label: 'OT', numeric: true },
                                { key: 'hours_dt', label: 'DT', numeric: true },
                                { key: 'notes', label: 'Notes' },
                            ]}
                            rows={labor}
                            onChange={(idx, patch) => updateRow(setLabor, idx, patch)}
                            onAdd={() => addRow(setLabor, emptyLabor)}
                            onRemove={(idx) => removeRow(setLabor, idx)}
                        />

                        <LineItemTable
                            title="Materials" low={isLowConfidence(ticket, 'materials')} readOnly={readOnly}
                            columns={[
                                { key: 'description', label: 'Description' },
                                { key: 'quantity', label: 'Qty', numeric: true },
                                { key: 'unit', label: 'Unit' },
                                { key: 'length', label: 'Length' },
                                { key: 'notes', label: 'Notes' },
                            ]}
                            rows={materials}
                            onChange={(idx, patch) => updateRow(setMaterials, idx, patch)}
                            onAdd={() => addRow(setMaterials, emptyMaterial)}
                            onRemove={(idx) => removeRow(setMaterials, idx)}
                        />

                        <LineItemTable
                            title="Equipment" low={isLowConfidence(ticket, 'equipment')} readOnly={readOnly}
                            columns={[
                                { key: 'description', label: 'Description' },
                                { key: 'quantity', label: 'Qty', numeric: true },
                                { key: 'hours', label: 'Hours', numeric: true },
                                { key: 'operator', label: 'Operator' },
                                { key: 'notes', label: 'Notes' },
                            ]}
                            rows={equipment}
                            onChange={(idx, patch) => updateRow(setEquipment, idx, patch)}
                            onAdd={() => addRow(setEquipment, emptyEquipment)}
                            onRemove={(idx) => removeRow(setEquipment, idx)}
                        />

                        <div className="flex flex-wrap items-center gap-3">
                            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-slate-200">
                                <input
                                    type="checkbox" checked={signaturePresent} disabled={readOnly}
                                    onChange={e => setSignaturePresent(e.target.checked)}
                                />
                                Signature present
                                <ConfidenceHint low={isLowConfidence(ticket, 'signature')} />
                            </label>
                            <input
                                type="text" placeholder="Signature name" value={signatureName} disabled={readOnly}
                                onChange={e => setSignatureName(e.target.value)}
                                className={fieldClass(isLowConfidence(ticket, 'signature'), 'flex-1 min-w-[160px]')}
                            />
                        </div>
                    </div>
                </div>

                {!readOnly && (
                    <div className="flex justify-end gap-2 px-5 py-4 border-t border-gray-200 dark:border-slate-700">
                        <button
                            onClick={handleReject} disabled={saving}
                            className="px-4 py-2 text-sm font-medium rounded-lg bg-red-500 hover:bg-red-600 text-white disabled:opacity-50"
                        >
                            Reject
                        </button>
                        <button
                            onClick={handleConfirm} disabled={saving}
                            className="px-4 py-2 text-sm font-medium rounded-lg bg-green-600 hover:bg-green-700 text-white disabled:opacity-50"
                        >
                            {saving ? 'Saving…' : 'Confirm'}
                        </button>
                    </div>
                )}
            </div>
        </div>
    );

    return createPortal(modalContent, document.body);
}
