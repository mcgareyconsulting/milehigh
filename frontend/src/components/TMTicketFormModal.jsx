/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Create/edit modal for a native T&M ticket — a mobile-first form for the field
 *          header (job/date/location/GC/foreman), labor/materials/equipment line items,
 *          photo/video attachments, and signature name. Create makes a draft; Save persists
 *          edits to a draft; Void discards.
 * exports:
 *   TMTicketFormModal: Portal modal. Props: isOpen, ticket (null = create), releaseCandidates, onClose, onSaved.
 * imports_from: [react, react-dom, ../services/tmApi, ./TMTicketAttachments]
 * imported_by: [pages/TMTickets.jsx]
 * invariants:
 *   - ticket === null => create mode; ticket.status === 'draft' => editable; otherwise read-only.
 *   - Create mode STAGES attachments client-side (no ticket id yet) and uploads them
 *     sequentially, best-effort, after the ticket is created — mirrors NewItemModal.jsx.
 *     Edit mode uploads immediately via TMTicketAttachments, which owns its own fetch.
 *   - Re-fetches release candidates whenever the job number field changes to a valid integer.
 *   - Closes on backdrop click and Escape, matching the other modals (ReleaseDetailModal, etc).
 */
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { createTicket, updateTicket, voidTicket, getReleaseCandidates, uploadTicketAttachment } from '../services/tmApi';
import TMTicketAttachments from './TMTicketAttachments';

const isMediaFile = (file) => {
    const type = (file?.type || '').toLowerCase();
    if (type.startsWith('image/') || type.startsWith('video/')) return true;
    return /\.(png|jpe?g|gif|webp|bmp|heic|heif|tiff?|mp4|mov|webm|3gp|m4v)$/i.test(file?.name || '');
};

const STATUS_LABEL = {
    draft: 'Draft', submitted: 'Submitted', pending_approval: 'Pending approval',
    approved: 'Approved', co_generated: 'CO generated', co_sent: 'CO sent',
    co_approved: 'CO approved', invoiced: 'Invoiced', rejected: 'Rejected', void: 'Void',
};
const STATUS_BADGE = {
    draft: 'bg-gray-100 text-gray-700 dark:bg-slate-700 dark:text-slate-300',
    submitted: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300',
    pending_approval: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    approved: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    invoiced: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
    void: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    rejected: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
};

const emptyLabor = () => ({ name: '', company: '', classification: '', hours_reg: '', hours_ot: '', hours_dt: '', notes: '' });
const emptyMaterial = () => ({ description: '', quantity: '', unit: '', length: '', notes: '' });
const emptyEquipment = () => ({ description: '', quantity: '', hours: '', operator: '', notes: '' });

const inputClass = 'w-full px-3 py-2.5 sm:py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100 disabled:opacity-70';
const labelClass = 'block text-xs font-medium text-gray-600 dark:text-slate-300 mb-1';
// Comfortable tap targets (~44px) for primary actions on narrow phones (iPhone SE/e-tier
// and similar ~375-393px portrait widths), sized back down at the sm: breakpoint (640px+)
// where a mouse/trackpad is more likely.
const touchButtonClass = 'px-4 py-3 sm:py-2 text-sm font-medium rounded-lg';

function StatusBadge({ status }) {
    return (
        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${STATUS_BADGE[status] || STATUS_BADGE.draft}`}>
            {STATUS_LABEL[status] || status}
        </span>
    );
}

// Below sm: (640px — covers ~375-430px portrait phones like the iPhone SE/e-tier), a
// horizontally-scrolling table of 5-7 columns nested inside an already-scrolling modal is
// unusable on a touchscreen: ambiguous scroll direction, controls scrolled out of reach.
// So under sm: each row renders as a stacked card instead; the table returns at sm:+ where
// there's room for it. Both share the same columns/rows/onChange contract.
function LineItemCards({ columns, rows, onChange, onRemove }) {
    if (rows.length === 0) {
        return (
            <div className="rounded-lg border border-dashed border-gray-200 dark:border-slate-700 px-3 py-3 text-center text-xs text-gray-400 dark:text-slate-500">
                No rows
            </div>
        );
    }
    return (
        <div className="space-y-2">
            {rows.map((row, idx) => (
                <div key={idx} className="rounded-lg border border-gray-200 dark:border-slate-700 p-3 bg-gray-50/50 dark:bg-slate-900/30">
                    <div className="grid grid-cols-2 gap-2">
                        {columns.map(c => (
                            <div key={c.key} className={c.wide ? 'col-span-2' : ''}>
                                <label className="block text-[11px] font-medium text-gray-500 dark:text-slate-400 mb-0.5">{c.label}</label>
                                <input
                                    type={c.numeric ? 'number' : 'text'}
                                    value={row[c.key] ?? ''}
                                    onChange={e => onChange(idx, { [c.key]: e.target.value })}
                                    className="w-full px-2.5 py-2.5 text-sm rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100"
                                />
                            </div>
                        ))}
                    </div>
                    <button type="button" onClick={() => onRemove(idx)}
                        className="mt-2 w-full min-h-[40px] text-xs font-medium rounded-md border border-red-200 dark:border-red-900/50 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20">
                        Remove row
                    </button>
                </div>
            ))}
        </div>
    );
}

function LineItemTable({ title, readOnly, columns, rows, onChange, onAdd, onRemove }) {
    return (
        <div>
            <div className="flex items-center justify-between mb-1">
                <h4 className="text-xs font-semibold text-gray-600 dark:text-slate-300">{title}</h4>
                {!readOnly && (
                    <button type="button" onClick={onAdd}
                        className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700">
                        + Add row
                    </button>
                )}
            </div>

            {readOnly ? null : (
                <div className="sm:hidden">
                    <LineItemCards columns={columns} rows={rows} onChange={onChange} onRemove={onRemove} />
                </div>
            )}
            {readOnly && rows.length === 0 && (
                <div className="sm:hidden rounded-lg border border-dashed border-gray-200 dark:border-slate-700 px-3 py-3 text-center text-xs text-gray-400 dark:text-slate-500">
                    No rows
                </div>
            )}
            {readOnly && rows.length > 0 && (
                <div className="sm:hidden space-y-2">
                    {rows.map((row, idx) => (
                        <div key={idx} className="rounded-lg border border-gray-200 dark:border-slate-700 p-3 bg-gray-50/50 dark:bg-slate-900/30">
                            <div className="grid grid-cols-2 gap-2">
                                {columns.map(c => (
                                    <div key={c.key} className={c.wide ? 'col-span-2' : ''}>
                                        <span className="block text-[11px] font-medium text-gray-500 dark:text-slate-400 mb-0.5">{c.label}</span>
                                        <span className="block text-sm text-gray-900 dark:text-slate-100 truncate">{row[c.key] || '—'}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <div className="hidden sm:block overflow-x-auto rounded-lg border border-gray-200 dark:border-slate-700">
                <table className="min-w-full text-xs">
                    <thead className="bg-gray-50 dark:bg-slate-900/40">
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

export default function TMTicketFormModal({ isOpen, ticket, releaseCandidates: initialCandidates, onClose, onSaved }) {
    const [job, setJob] = useState('');
    const [dateOfWork, setDateOfWork] = useState('');
    const [customer, setCustomer] = useState('');
    const [location, setLocation] = useState('');
    const [gcCompany, setGcCompany] = useState('');
    const [gcContact, setGcContact] = useState('');
    const [foreman, setForeman] = useState('');
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
    // Create-mode only: files picked before the ticket exists, staged as {id, file, url}
    // and uploaded sequentially once the ticket is created (mirrors NewItemModal.jsx).
    const [stagedAttachments, setStagedAttachments] = useState([]);
    const stagedFileInputRef = useRef(null);
    const stagedCameraInputRef = useRef(null);

    const isCreate = !ticket;
    const readOnly = !!ticket && ticket.status !== 'draft';

    // Seed the form whenever the modal opens (blank for create, ticket values for edit/view).
    useEffect(() => {
        if (!isOpen) return;
        setJob(ticket?.job != null ? String(ticket.job) : '');
        setDateOfWork(ticket?.date_of_work || '');
        setCustomer(ticket?.customer || '');
        setLocation(ticket?.location || '');
        setGcCompany(ticket?.gc_company || '');
        setGcContact(ticket?.gc_contact_name || '');
        setForeman(ticket?.foreman_name || '');
        setWorkDescription(ticket?.work_description || '');
        setLabor((ticket?.labor || []).map(l => ({ ...emptyLabor(), ...l })));
        setMaterials((ticket?.materials || []).map(m => ({ ...emptyMaterial(), ...m })));
        setEquipment((ticket?.equipment || []).map(e => ({ ...emptyEquipment(), ...e })));
        setSignaturePresent(!!ticket?.signature_present);
        setSignatureName(ticket?.signature_name || '');
        setReleaseId(ticket?.release_id != null ? String(ticket.release_id) : '');
        setCandidates(initialCandidates || (ticket?.release ? [ticket.release] : []));
        setError(null);
        setStagedAttachments(prev => { prev.forEach(s => URL.revokeObjectURL(s.url)); return []; });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, ticket?.id]);

    // Keep a live ref of staged attachments so the unmount cleanup below can revoke
    // whatever's current without re-subscribing the effect on every staged-file change.
    const stagedAttachmentsRef = useRef(stagedAttachments);
    stagedAttachmentsRef.current = stagedAttachments;
    useEffect(() => () => {
        stagedAttachmentsRef.current.forEach(s => URL.revokeObjectURL(s.url));
    }, []);

    // Escape-to-close.
    useEffect(() => {
        if (!isOpen) return undefined;
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);

    // Re-fetch release candidates whenever the job number field changes to a valid integer.
    useEffect(() => {
        if (!isOpen) return undefined;
        const jobNum = parseInt(job, 10);
        if (!String(job).trim() || isNaN(jobNum)) return undefined;
        let cancelled = false;
        setCandidatesLoading(true);
        getReleaseCandidates(jobNum)
            .then(d => { if (!cancelled) setCandidates(d.candidates || []); })
            .catch(() => { if (!cancelled) setCandidates([]); })
            .finally(() => { if (!cancelled) setCandidatesLoading(false); });
        return () => { cancelled = true; };
    }, [isOpen, job]);

    if (!isOpen) return null;

    const updateRow = (setter, idx, patch) => setter(prev => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
    const addRow = (setter, factory) => setter(prev => [...prev, factory()]);
    const removeRow = (setter, idx) => setter(prev => prev.filter((_, i) => i !== idx));

    let stagedIdSeq = 0;
    const handleStagedFilePick = (e) => {
        const files = Array.from(e.target.files || []).filter(isMediaFile);
        e.target.value = '';
        if (!files.length) return;
        setStagedAttachments(prev => [
            ...prev,
            ...files.map(file => ({ id: `staged-${Date.now()}-${stagedIdSeq++}`, file, url: URL.createObjectURL(file) })),
        ]);
    };
    const removeStagedAttachment = (id) => {
        setStagedAttachments(prev => {
            const target = prev.find(s => s.id === id);
            if (target) URL.revokeObjectURL(target.url);
            return prev.filter(s => s.id !== id);
        });
    };

    const buildBody = () => ({
        job: String(job).trim() ? parseInt(job, 10) : null,
        date_of_work: dateOfWork || null,
        customer,
        location,
        gc_company: gcCompany,
        gc_contact_name: gcContact,
        foreman_name: foreman,
        work_description: workDescription,
        labor,
        materials,
        equipment,
        signature_present: signaturePresent,
        signature_name: signatureName,
        release_id: releaseId ? parseInt(releaseId, 10) : null,
    });

    const handleSave = async () => {
        setSaving(true); setError(null);
        try {
            if (isCreate) {
                const { ticket: created } = await createTicket(buildBody());
                // Best-effort, sequential (server assigns stable, ordered ids) — a flaky
                // attachment upload shouldn't lose the ticket record that already saved.
                for (const staged of stagedAttachments) {
                    try {
                        await uploadTicketAttachment(created.id, staged.file);
                    } catch (err) {
                        console.warn('Failed to upload staged attachment', staged.file.name, err);
                    }
                }
            } else {
                await updateTicket(ticket.id, buildBody());
            }
            onSaved?.();
            onClose();
        } catch (err) {
            setError(err?.response?.data?.error || `Failed to ${isCreate ? 'create' : 'save'} ticket`);
        } finally {
            setSaving(false);
        }
    };

    const handleVoid = async () => {
        if (!window.confirm('Void this ticket? It stays on record but is no longer active.')) return;
        setSaving(true); setError(null);
        try {
            await voidTicket(ticket.id);
            onSaved?.();
            onClose();
        } catch (err) {
            setError(err?.response?.data?.error || 'Failed to void ticket');
        } finally {
            setSaving(false);
        }
    };

    // Pinned header/footer + internally-scrolling body, NOT position:sticky inside a
    // fully-scrolling overlay. That combination (sticky descendants of an overflow-y:auto
    // ancestor inside a fixed-position overlay) has two failure modes we hit in practice:
    // align-items:center made content above the fold unreachable by scroll (desktop/tablet),
    // and on iOS Safari the sticky header intermittently detached/duplicated during scroll,
    // rendering fields above the modal card entirely. Capping the card at max-h and scrolling
    // only the body (a plain non-sticky flex child) sidesteps both — standard modal pattern.
    const modalContent = (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3 sm:p-4" onClick={onClose}>
            <div
                className="w-full max-w-2xl max-h-[90vh] flex flex-col rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-2xl overflow-hidden"
                onClick={e => e.stopPropagation()}
            >
                <div className="shrink-0 flex items-center justify-between gap-3 px-4 sm:px-5 py-4 border-b border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                    <div className="flex items-center gap-2 min-w-0">
                        <h2 className="text-lg font-bold text-gray-900 dark:text-slate-100 truncate">
                            {isCreate ? 'New T&M Ticket' : `T&M Ticket #${ticket.id}`}
                        </h2>
                        {!isCreate && <StatusBadge status={ticket.status} />}
                    </div>
                    <button onClick={onClose} aria-label="Close" className="shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-slate-200 text-2xl leading-none">×</button>
                </div>

                <div className="flex-1 overflow-y-auto">
                {error && (
                    <div className="mx-4 sm:mx-5 mt-4 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">{error}</div>
                )}
                {readOnly && (
                    <div className="mx-4 sm:mx-5 mt-4 px-3 py-2 rounded-lg bg-gray-50 border border-gray-200 text-gray-600 dark:bg-slate-900/40 dark:border-slate-700 dark:text-slate-300 text-sm">
                        This ticket is {(STATUS_LABEL[ticket.status] || ticket.status).toLowerCase()} — fields are read-only.
                    </div>
                )}

                <div className="space-y-4 p-4 sm:p-5">
                    {/* min-w-0 on every grid item below: grid tracks default to min-width:auto,
                        so a child with a large intrinsic content width (native <input
                        type=date>'s segmented mm/dd/yyyy + calendar-icon chrome is the worst
                        offender, especially on WebKit/iOS) can stretch its whole column past
                        the card's padding — min-w-0 lets the track (and the input's own
                        w-full) actually govern the width instead. */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="min-w-0">
                            <label className={labelClass}>Job number</label>
                            <input type="text" inputMode="numeric" value={job} disabled={readOnly}
                                onChange={e => setJob(e.target.value)} className={inputClass} />
                        </div>
                        <div className="min-w-0">
                            <label className={labelClass}>Date of work</label>
                            {/* Native <input type=date> doesn't support the placeholder attribute at
                                all, and Safari/iOS renders the empty control very differently from
                                Chrome (no "mm/dd/yyyy" hint, and historically less reliable about
                                respecting a parent's width) — so we render our own hint as an
                                absolutely-positioned overlay and make the native text transparent
                                when empty, rather than depending on any browser's own placeholder
                                rendering. overflow-hidden on the wrapper is a hard backstop: even if
                                a browser's native control chrome ignores width, it gets clipped to
                                the field's box instead of visibly bleeding past the modal. The
                                calendar icon stays visible either way — WebKit renders it via
                                ::-webkit-calendar-picker-indicator, a separate pseudo-element not
                                affected by the input's text color. */}
                            <div className="relative w-full min-w-0 overflow-hidden rounded-lg border border-gray-300 dark:border-slate-600">
                                <input type="date" value={dateOfWork || ''} disabled={readOnly}
                                    onChange={e => setDateOfWork(e.target.value)}
                                    className={`w-full px-3 py-2.5 sm:py-2 text-sm bg-white dark:bg-slate-900 disabled:opacity-70 ${dateOfWork ? 'text-gray-900 dark:text-slate-100' : 'text-transparent'}`} />
                                {!dateOfWork && (
                                    <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-gray-400 dark:text-slate-500">
                                        mm/dd/yyyy
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>

                    <div>
                        <label className={labelClass}>Release (optional)</label>
                        <select value={releaseId} disabled={readOnly}
                            onChange={e => setReleaseId(e.target.value)} className={inputClass}>
                            <option value="">None</option>
                            {candidates.map(c => (
                                <option key={c.id} value={c.id}>
                                    {c.job}-{c.release}{c.job_name ? ` — ${c.job_name}` : ''}{c.description ? ` (${c.description})` : ''}
                                </option>
                            ))}
                        </select>
                        {candidatesLoading && <p className="mt-1 text-[11px] text-gray-400 dark:text-slate-500">Loading releases…</p>}
                    </div>

                    <div>
                        <label className={labelClass}>Location / area of work</label>
                        <input type="text" value={location} disabled={readOnly}
                            onChange={e => setLocation(e.target.value)} className={inputClass} />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="min-w-0">
                            <label className={labelClass}>GC company</label>
                            <input type="text" value={gcCompany} disabled={readOnly}
                                onChange={e => setGcCompany(e.target.value)} className={inputClass} />
                        </div>
                        <div className="min-w-0">
                            <label className={labelClass}>GC contact</label>
                            <input type="text" value={gcContact} disabled={readOnly}
                                onChange={e => setGcContact(e.target.value)} className={inputClass} />
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="min-w-0">
                            <label className={labelClass}>Foreman</label>
                            <input type="text" value={foreman} disabled={readOnly}
                                onChange={e => setForeman(e.target.value)} className={inputClass} />
                        </div>
                        <div className="min-w-0">
                            <label className={labelClass}>Customer</label>
                            <input type="text" value={customer} disabled={readOnly}
                                onChange={e => setCustomer(e.target.value)} className={inputClass} />
                        </div>
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

                    {isCreate ? (
                        <div>
                            <div className="flex items-center gap-2 mb-1.5">
                                <h4 className="text-xs font-semibold text-gray-600 dark:text-slate-300">
                                    Photos &amp; videos{stagedAttachments.length > 0 ? ` (${stagedAttachments.length})` : ''}
                                </h4>
                                <div className="ml-auto flex items-center gap-1.5">
                                    <button type="button" onClick={() => stagedFileInputRef.current?.click()}
                                        className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700">
                                        + Add
                                    </button>
                                    <button type="button" onClick={() => stagedCameraInputRef.current?.click()}
                                        className="sm:hidden text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700">
                                        Camera
                                    </button>
                                </div>
                                <input ref={stagedFileInputRef} type="file" accept="image/*,video/*" multiple
                                    onChange={handleStagedFilePick} className="hidden" />
                                <input ref={stagedCameraInputRef} type="file" accept="image/*,video/*" capture="environment"
                                    onChange={handleStagedFilePick} className="hidden" />
                            </div>
                            {stagedAttachments.length === 0 ? (
                                <div className="rounded-lg border border-dashed border-gray-200 dark:border-slate-700 px-3 py-3 text-center text-xs text-gray-400 dark:text-slate-500">
                                    No photos or videos yet. Use Add or Camera — they upload once the ticket is created.
                                </div>
                            ) : (
                                <div className="grid grid-cols-3 gap-2">
                                    {stagedAttachments.map(s => (
                                        <div key={s.id} className="group relative">
                                            {s.file.type.startsWith('video/') ? (
                                                <div className="w-full h-20 flex flex-col items-center justify-center gap-0.5 rounded-md border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700">
                                                    <span className="text-lg">▶</span>
                                                    <span className="text-[10px] text-gray-500 dark:text-slate-400 truncate max-w-full px-1">{s.file.name}</span>
                                                </div>
                                            ) : (
                                                <img src={s.url} alt={s.file.name}
                                                    className="w-full h-20 object-cover rounded-md border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700" />
                                            )}
                                            <button type="button" onClick={() => removeStagedAttachment(s.id)}
                                                className="absolute top-1 right-1 w-6 h-6 flex items-center justify-center rounded-full bg-black/60 text-white text-sm hover:bg-red-600"
                                                title="Remove">
                                                &times;
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    ) : (
                        <TMTicketAttachments ticketId={ticket.id} readOnly={readOnly} />
                    )}

                    <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                        <label className="flex items-center gap-2.5 text-sm text-gray-700 dark:text-slate-200 py-1">
                            <input type="checkbox" checked={signaturePresent} disabled={readOnly}
                                onChange={e => setSignaturePresent(e.target.checked)}
                                className="w-5 h-5 shrink-0" />
                            Signature present
                        </label>
                        <input type="text" placeholder="Signature name" value={signatureName} disabled={readOnly}
                            onChange={e => setSignatureName(e.target.value)}
                            className={`${inputClass} flex-1 sm:min-w-[160px]`} />
                    </div>
                </div>
                </div>

                {!readOnly && (
                    // flex-col-reverse on narrow screens puts Cancel/Save (the buttons most
                    // taps target) visually above the destructive Void action, without
                    // reordering the DOM; sm:flex-row restores the left/right layout once
                    // there's room for it.
                    <div className="shrink-0 flex flex-col-reverse sm:flex-row sm:justify-between gap-2 px-4 sm:px-5 py-4 border-t border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                        <div className={isCreate ? 'hidden sm:block' : ''}>
                            {!isCreate && (
                                <button onClick={handleVoid} disabled={saving}
                                    className={`w-full sm:w-auto ${touchButtonClass} bg-red-500 hover:bg-red-600 text-white disabled:opacity-50`}>
                                    Void
                                </button>
                            )}
                        </div>
                        <div className="flex gap-2">
                            <button onClick={onClose} disabled={saving}
                                className={`flex-1 sm:flex-none ${touchButtonClass} border border-gray-300 dark:border-slate-600 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50`}>
                                Cancel
                            </button>
                            <button onClick={handleSave} disabled={saving}
                                className={`flex-1 sm:flex-none ${touchButtonClass} bg-green-600 hover:bg-green-700 text-white disabled:opacity-50`}>
                                {saving ? 'Saving…' : (isCreate ? 'Create ticket' : 'Save changes')}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );

    return createPortal(modalContent, document.body);
}
