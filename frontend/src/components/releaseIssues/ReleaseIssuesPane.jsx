/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Issues tab of the release hub — the Release Issue & Error Register (roadmap T11).
 *   Issue list with open count + open estimated cost, a create form, and an issue detail with
 *   editable fields, photo/PDF evidence, and one timeline of comments (@mentions) + field changes.
 * exports:
 *   ReleaseIssuesPane: Issues tab body for one release
 * imports_from: [react, ../../services/releaseIssuesApi, ../../services/notificationApi,
 *   ../shared/MentionInput, ../../hooks/useBreakpoint]
 * imported_by: [frontend/src/components/ReleaseHubModal.jsx]
 * invariants:
 *   - Admin-only: the hub only renders this tab for admins, and every route is admin-gated.
 *   - Each issue is its own record — attachments and comments are fetched per issue, never pooled.
 *   - Allowed values come from GET /release-issues/options, never hard-coded here.
 *   - Estimated cost blank = Unknown/TBD (null), which is distinct from $0.
 *   - Department is a label only in v1 — no routing, no assignment (deferred).
 *   - Issue timestamps arrive as NAIVE UTC ISO strings (models._dt). They are parsed as UTC and
 *     shown in America/Denver — parsing them bare treats UTC as local and reads 6-7h late.
 *     (/brain/events differs: it is pre-converted to a Mountain wall-clock string server-side.)
 * updated_by_agent: 2026-09-15T00:00:00Z
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
    addIssueComment,
    createReleaseIssue,
    deleteIssueAttachment,
    fetchIssueOptions,
    getReleaseIssue,
    issueAttachmentFileUrl,
    listReleaseIssues,
    updateReleaseIssue,
    uploadIssueAttachment,
} from '../../services/releaseIssuesApi';
import { fetchMentionableUsers } from '../../services/notificationApi';
import MentionInput from '../shared/MentionInput';
import { useBreakpoint } from '../../hooks/useBreakpoint';

const ERROR_COLOR = 'var(--fl-red-bg)';

const PRIORITY_TINT = {
    low: { bg: 'var(--surface-2)', fg: 'var(--text-3)' },
    normal: { bg: 'var(--st-blue-bg)', fg: 'var(--st-blue-fg)' },
    high: { bg: 'var(--fl-amber-bg)', fg: 'var(--fl-amber-fg)' },
    critical: { bg: 'var(--fl-red-bg)', fg: 'var(--fl-red-fg)' },
};

const STATUS_TINT = {
    open: { bg: 'var(--accent-soft)', fg: 'var(--accent)' },
    under_review: { bg: 'var(--st-purple-bg)', fg: 'var(--st-purple-fg)' },
    in_progress: { bg: 'var(--st-blue-bg)', fg: 'var(--st-blue-fg)' },
    waiting_on_others: { bg: 'var(--fl-amber-bg)', fg: 'var(--fl-amber-fg)' },
    resolved: { bg: 'var(--st-green-bg)', fg: 'var(--st-green-fg)' },
    closed: { bg: 'var(--surface-2)', fg: 'var(--text-3)' },
};

const FIELD_LABELS = {
    title: 'Title',
    description: 'Description',
    department: 'Department',
    category: 'Category',
    priority: 'Priority',
    status: 'Status',
    estimated_cost: 'Estimated cost',
};

const EMPTY_FORM = {
    title: '',
    department: '',
    category: '',
    priority: 'normal',
    estimated_cost: '',
    description: '',
};

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });

const formatCost = (value) => (value == null || value === '' ? 'Unknown/TBD' : usd.format(Number(value)));

/** Parse a server timestamp; a naive ISO string (no Z / offset) is UTC. */
const parseServerTime = (iso) => {
    if (!iso) return null;
    const s = String(iso);
    const d = new Date(/(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(s) ? s : `${s}Z`);
    return isNaN(d) ? null : d;
};

const formatWhen = (iso) => {
    const d = parseServerTime(iso);
    if (!d) return '';
    return d.toLocaleString('en-US', {
        timeZone: 'America/Denver', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    });
};

const errorText = (err, fallback) => err?.response?.data?.error || err?.message || fallback;

const labelFor = (options, key, value) => {
    const found = (options?.[key] || []).find((o) => o.value === value);
    return found ? found.label : value;
};

const inputCls = 'w-full text-ink bg-surface border border-hairline rounded-md';
const inputStyle = { fontSize: 13.5, padding: '7px 9px' };
const mentionCls = `${inputCls} resize-y`;

function Chip({ tint, children, mono = false }) {
    return (
        <span
            className={`inline-block font-semibold whitespace-nowrap ${mono ? 'font-mono' : ''}`}
            style={{ fontSize: 11.5, padding: '2px 8px', borderRadius: 999, background: tint?.bg, color: tint?.fg }}
        >
            {children}
        </span>
    );
}

function FieldLabel({ children, required = false }) {
    return (
        <span className="block text-jl-label font-bold uppercase text-ink-3" style={{ marginBottom: 4 }}>
            {children}{required && <span style={{ color: ERROR_COLOR }}> *</span>}
        </span>
    );
}

function Select({ value, onChange, options, placeholder, disabled }) {
    return (
        <select
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            className={inputCls}
            style={inputStyle}
        >
            {placeholder != null && <option value="">{placeholder}</option>}
            {(options || []).map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
            ))}
        </select>
    );
}

function PrimaryButton({ children, disabled, onClick, type = 'button' }) {
    return (
        <button
            type={type}
            onClick={onClick}
            disabled={disabled}
            className="font-semibold border-0 cursor-pointer text-white disabled:opacity-50"
            style={{ fontSize: 12.5, padding: '6px 13px', borderRadius: 7, background: 'var(--accent)' }}
        >
            {children}
        </button>
    );
}

function GhostButton({ children, disabled, onClick }) {
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            className="text-ink-2 bg-transparent border-0 cursor-pointer font-medium disabled:opacity-50"
            style={{ fontSize: 12.5, padding: '6px 8px' }}
        >
            {children}
        </button>
    );
}

/** File picker that hands back an array of Files; accepts photos and PDFs. */
function AttachButton({ onFiles, disabled, label = 'Attach photo/PDF' }) {
    const ref = useRef(null);
    return (
        <>
            <input
                ref={ref}
                type="file"
                accept="image/*,application/pdf"
                multiple
                className="hidden"
                onChange={(e) => {
                    const files = Array.from(e.target.files || []);
                    e.target.value = '';
                    if (files.length) onFiles(files);
                }}
            />
            <button
                type="button"
                disabled={disabled}
                onClick={() => ref.current?.click()}
                className="font-semibold border border-hairline-strong bg-surface text-ink-2 hover:text-ink cursor-pointer disabled:opacity-50"
                style={{ fontSize: 12, padding: '4px 10px', borderRadius: 7 }}
            >
                {label}
            </button>
        </>
    );
}

function PendingFiles({ files, onRemove }) {
    if (!files.length) return null;
    return (
        <div className="flex flex-wrap" style={{ gap: 6, marginTop: 6 }}>
            {files.map((f, i) => (
                <span
                    key={`${f.name}-${i}`}
                    className="inline-flex items-center bg-surface-2 border border-hairline text-ink-2"
                    style={{ fontSize: 12, padding: '2px 8px', borderRadius: 999, gap: 6 }}
                >
                    {f.name}
                    <button
                        type="button"
                        onClick={() => onRemove(i)}
                        className="bg-transparent border-0 cursor-pointer text-ink-3"
                        aria-label={`Remove ${f.name}`}
                    >
                        ×
                    </button>
                </span>
            ))}
        </div>
    );
}

function AttachmentTile({ issueId, attachment, onDelete }) {
    const url = issueAttachmentFileUrl(issueId, attachment.id);
    return (
        <div className="relative border border-hairline rounded-md overflow-hidden bg-surface-2" style={{ width: 112 }}>
            <a href={url} target="_blank" rel="noopener noreferrer" className="block" title={attachment.original_filename || ''}>
                {attachment.is_pdf ? (
                    <div className="grid place-items-center text-ink-2 font-bold" style={{ height: 84, fontSize: 13 }}>PDF</div>
                ) : (
                    <img src={url} alt={attachment.original_filename || 'Issue photo'} className="block w-full object-cover" style={{ height: 84 }} loading="lazy" />
                )}
                <div className="truncate text-ink-3" style={{ fontSize: 11, padding: '3px 6px' }}>
                    {attachment.original_filename || (attachment.is_pdf ? 'Document.pdf' : 'Photo')}
                </div>
            </a>
            {onDelete && (
                <button
                    type="button"
                    onClick={() => onDelete(attachment)}
                    className="absolute grid place-items-center border-0 cursor-pointer text-white"
                    style={{ top: 3, right: 3, width: 20, height: 20, borderRadius: 999, background: 'rgba(10,16,28,.6)', fontSize: 13 }}
                    aria-label="Remove attachment"
                    title="Remove attachment"
                >
                    ×
                </button>
            )}
        </div>
    );
}

async function uploadAll(issueId, files, commentId = null) {
    const failures = [];
    for (const file of files) {
        try {
            await uploadIssueAttachment(issueId, file, commentId);
        } catch (err) {
            failures.push(`${file.name}: ${errorText(err, 'upload failed')}`);
        }
    }
    return failures;
}

function CreateIssueForm({ releaseId, options, users, onCreated, onCancel }) {
    const [form, setForm] = useState(EMPTY_FORM);
    const [files, setFiles] = useState([]);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);

    const set = (key) => (value) => setForm((f) => ({ ...f, [key]: value }));

    const submit = async (e) => {
        e?.preventDefault?.();
        if (!form.title.trim() || !form.department || !form.category || !form.description.trim()) {
            setError('Title, department, category and description are required.');
            return;
        }
        setSaving(true);
        setError(null);
        try {
            const detail = await createReleaseIssue(releaseId, {
                ...form,
                estimated_cost: form.estimated_cost.trim() === '' ? null : form.estimated_cost,
            });
            const failures = files.length ? await uploadAll(detail.issue.id, files) : [];
            onCreated(detail.issue.id, failures);
        } catch (err) {
            setError(errorText(err, 'Could not create the issue'));
            setSaving(false);
        }
    };

    return (
        <form onSubmit={submit} className="bg-surface border border-hairline rounded-lg" style={{ padding: 16 }}>
            <div className="font-bold text-ink" style={{ fontSize: 15, marginBottom: 12 }}>New issue</div>
            <div className="grid" style={{ gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
                <label className="block" style={{ gridColumn: '1 / -1' }}>
                    <FieldLabel required>Title</FieldLabel>
                    <input
                        value={form.title}
                        onChange={(e) => set('title')(e.target.value)}
                        maxLength={200}
                        className={inputCls}
                        style={inputStyle}
                        placeholder="Short summary of the problem"
                        disabled={saving}
                    />
                </label>
                <label className="block">
                    <FieldLabel required>Department</FieldLabel>
                    <Select value={form.department} onChange={set('department')} options={options.departments} placeholder="Select…" disabled={saving} />
                </label>
                <label className="block">
                    <FieldLabel required>Category</FieldLabel>
                    <Select value={form.category} onChange={set('category')} options={options.categories} placeholder="Select…" disabled={saving} />
                </label>
                <label className="block">
                    <FieldLabel>Priority</FieldLabel>
                    <Select value={form.priority} onChange={set('priority')} options={options.priorities} disabled={saving} />
                </label>
                <label className="block">
                    <FieldLabel>Estimated cost</FieldLabel>
                    <input
                        value={form.estimated_cost}
                        onChange={(e) => set('estimated_cost')(e.target.value)}
                        inputMode="decimal"
                        className={inputCls}
                        style={inputStyle}
                        placeholder="Blank = Unknown/TBD"
                        disabled={saving}
                    />
                </label>
                <div className="block" style={{ gridColumn: '1 / -1' }}>
                    <FieldLabel required>Description</FieldLabel>
                    <MentionInput
                        value={form.description}
                        onChange={set('description')}
                        onSubmit={() => {}}
                        users={users}
                        multiline
                        rows={4}
                        placeholder="What happened, where, and what it affects. @mention teammates to notify them."
                        disabled={saving}
                        className={mentionCls}
                    />
                    <p className="text-ink-3" style={{ fontSize: 11.5, marginTop: 4 }}>Shift+Enter for a new line.</p>
                </div>
            </div>
            <div style={{ marginTop: 12 }}>
                <AttachButton onFiles={(fs) => setFiles((prev) => [...prev, ...fs])} disabled={saving} />
                <PendingFiles files={files} onRemove={(i) => setFiles((prev) => prev.filter((_, j) => j !== i))} />
            </div>
            {error && <p style={{ color: ERROR_COLOR, fontSize: 12.5, marginTop: 10 }}>{error}</p>}
            <div className="flex items-center justify-end" style={{ gap: 8, marginTop: 14 }}>
                <GhostButton onClick={onCancel} disabled={saving}>Cancel</GhostButton>
                <PrimaryButton type="submit" disabled={saving}>{saving ? 'Saving…' : 'Create issue'}</PrimaryButton>
            </div>
        </form>
    );
}

/** One merged, oldest-first timeline of creation, field changes and comments. */
function buildTimeline(detail) {
    if (!detail) return [];
    const { issue, comments, changes, attachments } = detail;
    const byComment = new Map();
    for (const a of attachments) {
        if (a.comment_id == null) continue;
        if (!byComment.has(a.comment_id)) byComment.set(a.comment_id, []);
        byComment.get(a.comment_id).push(a);
    }
    const items = [
        { kind: 'created', at: issue.created_at, who: issue.created_by_name, key: 'created' },
        ...changes.map((c) => ({ kind: 'change', at: c.changed_at, who: c.changed_by_name, change: c, key: `ch-${c.id}` })),
        ...comments.map((c) => ({
            kind: 'comment', at: c.created_at, who: c.author_name, comment: c,
            attachments: byComment.get(c.id) || [], key: `co-${c.id}`,
        })),
    ];
    return items.sort((a, b) => (parseServerTime(a.at) || 0) - (parseServerTime(b.at) || 0));
}

function IssueDetail({ issueId, options, users, onBack, onChanged, showBack }) {
    const [detail, setDetail] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [busy, setBusy] = useState(false);
    const [editingText, setEditingText] = useState(false);
    const [textDraft, setTextDraft] = useState({ title: '', description: '' });
    const [costDraft, setCostDraft] = useState('');
    const [comment, setComment] = useState('');
    const [commentFiles, setCommentFiles] = useState([]);
    const [posting, setPosting] = useState(false);

    const load = useCallback(async () => {
        try {
            const data = await getReleaseIssue(issueId);
            setDetail(data);
            setCostDraft(data.issue.estimated_cost == null ? '' : String(data.issue.estimated_cost));
            setError(null);
        } catch (err) {
            setError(errorText(err, 'Could not load the issue'));
        } finally {
            setLoading(false);
        }
    }, [issueId]);

    useEffect(() => {
        setLoading(true);
        setEditingText(false);
        setComment('');
        setCommentFiles([]);
        load();
    }, [load]);

    const applyPatch = async (patch) => {
        setBusy(true);
        setError(null);
        try {
            const data = await updateReleaseIssue(issueId, patch);
            setDetail(data);
            setCostDraft(data.issue.estimated_cost == null ? '' : String(data.issue.estimated_cost));
            onChanged();
            return true;
        } catch (err) {
            setError(errorText(err, 'Could not save the change'));
            return false;
        } finally {
            setBusy(false);
        }
    };

    const saveCost = () => {
        const current = detail.issue.estimated_cost == null ? '' : String(detail.issue.estimated_cost);
        if (costDraft.trim() === current) return;
        applyPatch({ estimated_cost: costDraft.trim() === '' ? null : costDraft });
    };

    const saveText = async () => {
        const ok = await applyPatch({ title: textDraft.title, description: textDraft.description });
        if (ok) setEditingText(false);
    };

    const postComment = async () => {
        if (!comment.trim() && !commentFiles.length) return;
        setPosting(true);
        setError(null);
        try {
            const body = comment.trim() || `Attached ${commentFiles.length} file${commentFiles.length === 1 ? '' : 's'}`;
            const created = await addIssueComment(issueId, body);
            const failures = commentFiles.length ? await uploadAll(issueId, commentFiles, created.id) : [];
            setComment('');
            setCommentFiles([]);
            if (failures.length) setError(failures.join(' · '));
            await load();
            onChanged();
        } catch (err) {
            setError(errorText(err, 'Could not post the comment'));
        } finally {
            setPosting(false);
        }
    };

    const addFiles = async (files) => {
        setBusy(true);
        setError(null);
        const failures = await uploadAll(issueId, files);
        if (failures.length) setError(failures.join(' · '));
        await load();
        setBusy(false);
    };

    const removeAttachment = async (attachment) => {
        if (!window.confirm(`Remove ${attachment.original_filename || 'this attachment'} from the issue?`)) return;
        try {
            await deleteIssueAttachment(issueId, attachment.id);
            await load();
        } catch (err) {
            setError(errorText(err, 'Could not remove the attachment'));
        }
    };

    const timeline = useMemo(() => buildTimeline(detail), [detail]);

    if (loading && !detail) return <p className="text-ink-3 italic" style={{ fontSize: 13 }}>Loading issue…</p>;
    if (!detail) return <p style={{ color: ERROR_COLOR, fontSize: 13 }}>{error}</p>;

    const { issue, attachments } = detail;
    const issueLevelAttachments = attachments.filter((a) => a.comment_id == null);
    const descriptionEdited = issue.original_description !== issue.description;

    const displayValue = (field, value) => {
        if (value == null || value === '') return field === 'estimated_cost' ? 'Unknown/TBD' : '—';
        if (field === 'estimated_cost') return formatCost(value);
        const key = { department: 'departments', category: 'categories', priority: 'priorities', status: 'statuses' }[field];
        return key ? labelFor(options, key, value) : value;
    };

    return (
        <div className="flex flex-col" style={{ gap: 16 }}>
            {showBack && (
                <button type="button" onClick={onBack} className="self-start bg-transparent border-0 cursor-pointer font-semibold" style={{ color: 'var(--accent)', fontSize: 13, padding: 0 }}>
                    ← All issues
                </button>
            )}

            <div>
                <div className="flex items-center flex-wrap" style={{ gap: 8 }}>
                    <Chip mono tint={{ bg: 'var(--accent-soft)', fg: 'var(--accent)' }}>{issue.display_id}</Chip>
                    <Chip tint={STATUS_TINT[issue.status]}>{labelFor(options, 'statuses', issue.status)}</Chip>
                    <Chip tint={PRIORITY_TINT[issue.priority]}>{labelFor(options, 'priorities', issue.priority)}</Chip>
                    <span className="text-ink-3" style={{ fontSize: 12 }}>
                        Opened by {issue.created_by_name || 'unknown'} · {formatWhen(issue.created_at)}
                    </span>
                </div>
                {editingText ? (
                    <div style={{ marginTop: 10 }}>
                        <input
                            value={textDraft.title}
                            onChange={(e) => setTextDraft((d) => ({ ...d, title: e.target.value }))}
                            maxLength={200}
                            className={inputCls}
                            style={{ ...inputStyle, fontSize: 15, fontWeight: 700 }}
                            disabled={busy}
                        />
                        <div style={{ marginTop: 8 }}>
                            <MentionInput
                                value={textDraft.description}
                                onChange={(v) => setTextDraft((d) => ({ ...d, description: v }))}
                                onSubmit={() => {}}
                                users={users}
                                multiline
                                rows={4}
                                disabled={busy}
                                className={mentionCls}
                            />
                        </div>
                        <div className="flex justify-end" style={{ gap: 8, marginTop: 8 }}>
                            <GhostButton onClick={() => setEditingText(false)} disabled={busy}>Cancel</GhostButton>
                            <PrimaryButton onClick={saveText} disabled={busy}>{busy ? 'Saving…' : 'Save'}</PrimaryButton>
                        </div>
                    </div>
                ) : (
                    <>
                        <div className="flex items-start" style={{ gap: 10, marginTop: 8 }}>
                            <h3 className="text-ink flex-1 min-w-0" style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>{issue.title}</h3>
                            <GhostButton
                                onClick={() => {
                                    setTextDraft({ title: issue.title, description: issue.description });
                                    setEditingText(true);
                                }}
                            >
                                Edit
                            </GhostButton>
                        </div>
                        <p className="text-ink whitespace-pre-wrap break-words" style={{ fontSize: 13.5, marginTop: 6, lineHeight: 1.45 }}>
                            {issue.description}
                        </p>
                        {descriptionEdited && (
                            <details style={{ marginTop: 6 }}>
                                <summary className="text-ink-3 cursor-pointer" style={{ fontSize: 12 }}>Original description</summary>
                                <p className="text-ink-2 whitespace-pre-wrap break-words" style={{ fontSize: 13, marginTop: 4 }}>
                                    {issue.original_description}
                                </p>
                            </details>
                        )}
                    </>
                )}
            </div>

            <div className="grid" style={{ gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
                <label className="block">
                    <FieldLabel>Status</FieldLabel>
                    <Select value={issue.status} onChange={(v) => applyPatch({ status: v })} options={options.statuses} disabled={busy} />
                </label>
                <label className="block">
                    <FieldLabel>Priority</FieldLabel>
                    <Select value={issue.priority} onChange={(v) => applyPatch({ priority: v })} options={options.priorities} disabled={busy} />
                </label>
                <label className="block">
                    <FieldLabel>Department</FieldLabel>
                    <Select value={issue.department} onChange={(v) => applyPatch({ department: v })} options={options.departments} disabled={busy} />
                </label>
                <label className="block">
                    <FieldLabel>Category</FieldLabel>
                    <Select value={issue.category} onChange={(v) => applyPatch({ category: v })} options={options.categories} disabled={busy} />
                </label>
                <label className="block">
                    <FieldLabel>Estimated cost</FieldLabel>
                    <input
                        value={costDraft}
                        onChange={(e) => setCostDraft(e.target.value)}
                        onBlur={saveCost}
                        onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
                        inputMode="decimal"
                        placeholder="Unknown/TBD"
                        className={inputCls}
                        style={inputStyle}
                        disabled={busy}
                    />
                </label>
            </div>

            {error && <p style={{ color: ERROR_COLOR, fontSize: 12.5, margin: 0 }}>{error}</p>}

            <section>
                <div className="flex items-center" style={{ gap: 10, marginBottom: 8 }}>
                    <span className="text-jl-label font-bold uppercase text-ink-3">Evidence</span>
                    <span className="text-ink-3" style={{ fontSize: 12 }}>{issueLevelAttachments.length}</span>
                    <div className="flex-1" />
                    <AttachButton onFiles={addFiles} disabled={busy} label={busy ? 'Uploading…' : 'Add photo/PDF'} />
                </div>
                {issueLevelAttachments.length === 0 ? (
                    <p className="text-ink-3" style={{ fontSize: 12.5, margin: 0 }}>No photos or PDFs on this issue yet.</p>
                ) : (
                    <div className="flex flex-wrap" style={{ gap: 8 }}>
                        {issueLevelAttachments.map((a) => (
                            <AttachmentTile key={a.id} issueId={issue.id} attachment={a} onDelete={removeAttachment} />
                        ))}
                    </div>
                )}
            </section>

            <section>
                <span className="block text-jl-label font-bold uppercase text-ink-3" style={{ marginBottom: 8 }}>Timeline</span>
                <ol className="list-none m-0 p-0 flex flex-col" style={{ gap: 10 }}>
                    {timeline.map((item) => (
                        <li key={item.key} className="border-l-2 border-hairline" style={{ paddingLeft: 12 }}>
                            <div className="flex items-baseline flex-wrap" style={{ gap: 6 }}>
                                <span className="font-bold text-ink" style={{ fontSize: 13 }}>{item.who || 'Unknown'}</span>
                                <span className="text-ink-3" style={{ fontSize: 11.5 }}>{formatWhen(item.at)}</span>
                            </div>
                            {item.kind === 'created' && (
                                <div className="text-ink-2" style={{ fontSize: 13, marginTop: 2 }}>Opened this issue</div>
                            )}
                            {item.kind === 'change' && (
                                <div className="text-ink-2" style={{ fontSize: 13, marginTop: 2 }}>
                                    {item.change.field === 'description' || item.change.field === 'title' ? (
                                        <>Edited the {FIELD_LABELS[item.change.field].toLowerCase()}</>
                                    ) : (
                                        <>
                                            {FIELD_LABELS[item.change.field] || item.change.field}:{' '}
                                            <span className="text-ink-3 line-through">{displayValue(item.change.field, item.change.old_value)}</span>
                                            {' → '}
                                            <span className="font-semibold text-ink">{displayValue(item.change.field, item.change.new_value)}</span>
                                        </>
                                    )}
                                </div>
                            )}
                            {item.kind === 'comment' && (
                                <>
                                    <p className="text-ink whitespace-pre-wrap break-words" style={{ fontSize: 13.5, margin: '3px 0 0', lineHeight: 1.4 }}>
                                        {item.comment.body}
                                    </p>
                                    {item.attachments.length > 0 && (
                                        <div className="flex flex-wrap" style={{ gap: 8, marginTop: 6 }}>
                                            {item.attachments.map((a) => (
                                                <AttachmentTile key={a.id} issueId={issue.id} attachment={a} onDelete={removeAttachment} />
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}
                        </li>
                    ))}
                </ol>

                <div className="bg-surface border border-hairline rounded-lg" style={{ padding: 10, marginTop: 12 }}>
                    <MentionInput
                        value={comment}
                        onChange={setComment}
                        onSubmit={postComment}
                        users={users}
                        multiline
                        rows={2}
                        placeholder="Add a comment — @mention to notify. Enter to post, Shift+Enter for a new line."
                        disabled={posting}
                        className={mentionCls}
                    />
                    <PendingFiles files={commentFiles} onRemove={(i) => setCommentFiles((prev) => prev.filter((_, j) => j !== i))} />
                    <div className="flex items-center" style={{ gap: 8, marginTop: 8 }}>
                        <AttachButton onFiles={(fs) => setCommentFiles((prev) => [...prev, ...fs])} disabled={posting} />
                        <div className="flex-1" />
                        <PrimaryButton onClick={postComment} disabled={posting || (!comment.trim() && !commentFiles.length)}>
                            {posting ? 'Posting…' : 'Comment'}
                        </PrimaryButton>
                    </div>
                </div>
            </section>
        </div>
    );
}

export function ReleaseIssuesPane({ releaseId, initialIssueId = null, onSummary = null }) {
    const { isMobile } = useBreakpoint();
    const [options, setOptions] = useState(null);
    const [users, setUsers] = useState([]);
    const [issues, setIssues] = useState([]);
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [notice, setNotice] = useState(null);
    const [selectedId, setSelectedId] = useState(initialIssueId);
    const [creating, setCreating] = useState(false);
    const [showClosed, setShowClosed] = useState(true);
    // Hosts pass an inline callback; a ref keeps it out of refresh's deps so a
    // re-render of the hub never triggers a re-fetch.
    const onSummaryRef = useRef(onSummary);
    onSummaryRef.current = onSummary;

    const refresh = useCallback(async () => {
        try {
            const data = await listReleaseIssues(releaseId);
            setIssues(data.issues);
            setSummary(data.summary);
            onSummaryRef.current?.(data.summary);
            setError(null);
        } catch (err) {
            setError(errorText(err, 'Could not load issues'));
        } finally {
            setLoading(false);
        }
    }, [releaseId]);

    useEffect(() => {
        fetchIssueOptions().then(setOptions).catch((err) => setError(errorText(err, 'Could not load issue options')));
        fetchMentionableUsers().then(setUsers).catch(() => {});
    }, []);

    useEffect(() => {
        setLoading(true);
        refresh();
    }, [refresh]);

    useEffect(() => {
        if (initialIssueId != null) {
            setSelectedId(initialIssueId);
            setCreating(false);
        }
    }, [initialIssueId]);

    const closedSet = useMemo(() => new Set(options?.closed_statuses || []), [options]);
    const visibleIssues = showClosed ? issues : issues.filter((i) => !closedSet.has(i.status));

    if (!options) {
        return (
            <p className="text-ink-3 italic" style={{ fontSize: 13, padding: 18 }}>
                {error || 'Loading issues…'}
            </p>
        );
    }

    const listPane = (
        <div className="flex flex-col min-h-0" style={{ gap: 10 }}>
            <div className="flex items-center flex-wrap" style={{ gap: 10 }}>
                <span className="font-bold text-ink" style={{ fontSize: 15 }}>Issues</span>
                {summary && (
                    <span className="text-ink-2" style={{ fontSize: 12.5 }}>
                        <strong>{summary.open_count}</strong> open · <strong>{usd.format(summary.open_estimated_cost)}</strong> est.
                        {summary.open_unknown_cost_count > 0 && (
                            <span className="text-ink-3"> (+{summary.open_unknown_cost_count} TBD)</span>
                        )}
                    </span>
                )}
                <div className="flex-1" />
                <button
                    type="button"
                    onClick={() => { setCreating(true); setSelectedId(null); setNotice(null); }}
                    className="font-semibold border-0 cursor-pointer"
                    style={{ fontSize: 12.5, padding: '5px 11px', borderRadius: 999, background: 'var(--accent-soft)', color: 'var(--accent)' }}
                >
                    + New issue
                </button>
            </div>
            <label className="inline-flex items-center text-ink-3" style={{ gap: 6, fontSize: 12 }}>
                <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} />
                Show resolved &amp; closed
            </label>

            {loading && <p className="text-ink-3 italic" style={{ fontSize: 13 }}>Loading…</p>}
            {error && <p style={{ color: ERROR_COLOR, fontSize: 12.5 }}>{error}</p>}
            {!loading && visibleIssues.length === 0 && (
                <p className="text-ink-3" style={{ fontSize: 13 }}>
                    {issues.length === 0 ? 'No issues recorded on this release.' : 'No open issues.'}
                </p>
            )}

            <ul className="list-none m-0 p-0 flex flex-col" style={{ gap: 6 }}>
                {visibleIssues.map((issue) => {
                    const active = issue.id === selectedId && !creating;
                    const done = closedSet.has(issue.status);
                    return (
                        <li key={issue.id}>
                            <button
                                type="button"
                                onClick={() => { setSelectedId(issue.id); setCreating(false); setNotice(null); }}
                                className="w-full text-left border cursor-pointer rounded-lg"
                                style={{
                                    padding: '9px 11px',
                                    background: active ? 'var(--accent-soft)' : 'var(--surface)',
                                    borderColor: active ? 'var(--accent)' : 'var(--border)',
                                    opacity: done ? 0.7 : 1,
                                }}
                            >
                                <div className="flex items-center flex-wrap" style={{ gap: 6 }}>
                                    <span className="font-mono text-ink-3" style={{ fontSize: 11.5 }}>{issue.display_id}</span>
                                    <Chip tint={STATUS_TINT[issue.status]}>{labelFor(options, 'statuses', issue.status)}</Chip>
                                    <Chip tint={PRIORITY_TINT[issue.priority]}>{labelFor(options, 'priorities', issue.priority)}</Chip>
                                </div>
                                <div className="font-semibold text-ink truncate" style={{ fontSize: 13.5, marginTop: 4 }}>{issue.title}</div>
                                <div className="text-ink-3 truncate" style={{ fontSize: 12, marginTop: 2 }}>
                                    {labelFor(options, 'departments', issue.department)} · {labelFor(options, 'categories', issue.category)} · {formatCost(issue.estimated_cost)}
                                </div>
                            </button>
                        </li>
                    );
                })}
            </ul>
        </div>
    );

    const rightPane = creating ? (
        <CreateIssueForm
            releaseId={releaseId}
            options={options}
            users={users}
            onCancel={() => setCreating(false)}
            onCreated={async (issueId, failures) => {
                setCreating(false);
                setSelectedId(issueId);
                setNotice(failures.length ? `Issue created, but some files failed: ${failures.join(' · ')}` : null);
                await refresh();
            }}
        />
    ) : selectedId != null ? (
        <IssueDetail
            key={selectedId}
            issueId={selectedId}
            options={options}
            users={users}
            showBack={isMobile}
            onBack={() => setSelectedId(null)}
            onChanged={refresh}
        />
    ) : (
        <p className="text-ink-3" style={{ fontSize: 13 }}>
            Select an issue, or record a new one. Each issue keeps its own evidence, comments and history.
        </p>
    );

    if (isMobile) {
        const showRight = creating || selectedId != null;
        return (
            <div className="absolute inset-0 overflow-auto" style={{ padding: '14px 14px 22px' }}>
                {notice && <p style={{ color: ERROR_COLOR, fontSize: 12.5 }}>{notice}</p>}
                {showRight ? rightPane : listPane}
            </div>
        );
    }

    return (
        <div className="absolute inset-0 grid" style={{ gridTemplateColumns: 'minmax(260px, 340px) minmax(0, 1fr)' }}>
            <div className="overflow-auto border-r border-hairline bg-surface-2" style={{ padding: '14px 14px 22px' }}>
                {listPane}
            </div>
            <div className="overflow-auto" style={{ padding: '16px 20px 24px' }}>
                {notice && <p style={{ color: ERROR_COLOR, fontSize: 12.5, marginTop: 0 }}>{notice}</p>}
                {rightPane}
            </div>
        </div>
    );
}

export default ReleaseIssuesPane;
