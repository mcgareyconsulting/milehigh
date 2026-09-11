/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Pull a release's Final PDF Pack out of Procore into its drawing versions.
 *   The nightly FC worker only links the submittal; this is the manual fetch of the pack
 *   itself — for the gaps the worker leaves and for testing the drawing pipeline on demand.
 * exports:
 *   ProcorePullDialog: props { isOpen, releaseId, label, onClose, onPulled }
 * imports_from: [react, react-dom, ../../services/jobsApi]
 * imported_by: [frontend/src/components/pdfViewer/PdfViewerPane.jsx]
 * invariants:
 *   - Read-only until the user presses Pull on a row; nothing is fetched from Procore on open
 *     beyond the candidate listing
 *   - A 409 (nothing linked) is a normal state, not an error: it offers the submittal-id box
 *   - Every listing is traced to the browser console; "Dump raw" adds Procore's own
 *     payloads, and a row's "probe" re-asks Procore about that one attachment's ids
 *   - A row shows only what a reviewer decides on: the Final PDF Pack tag, who returned it,
 *     and whether markups came through. The full evidence trail lives in the console dump
 *   - Roles come from the server's evidence — this file never re-labels from the filename
 * updated_by_agent: 2026-09-06T00:00:00Z
 */
import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { jobsApi } from '../../services/jobsApi';

// Role is decided server-side from evidence, never from the filename. See
// procore_pull._role_for; `role_evidence` says which fact carried it.
const ROLE = {
    final_pack: { text: 'Final PDF Pack', bg: 'var(--st-green-bg)', fg: 'var(--st-green-fg)' },
    approver_copy: { text: 'Approver copy', bg: 'var(--accent-soft)', fg: 'var(--accent)' },
    submitted: { text: 'Submitted set', bg: 'var(--surface-2)', fg: 'var(--text-3)' },
};

const RESOLVED_BY = {
    release_link: 'linked by the nightly FC worker',
    submittals_table: 'matched on job-release in our submittal mirror',
    override: 'submittal id you entered',
};

/**
 * Console trace of one listing. Opening the dialog leaves the resolved submittal and every
 * candidate in the console; "Dump raw" re-fetches with ?debug=1 and adds Procore's own
 * objects plus every JSON path that looks like a final-PDF label — which is how you find
 * where a name like "Final PDF Pack" is hiding when a row is labelled wrong.
 */
function logPayload(payload, releaseId) {
    if (typeof console === 'undefined' || !payload) return;
    const docs = payload.documents || [];
    console.groupCollapsed(
        `[Procore pull] release ${releaseId} · submittal ${payload.submittal?.submittal_id} · ${docs.length} document(s)`
    );
    console.log('submittal', payload.submittal);
    if (docs.length && console.table) {
        console.table(docs.map((d) => ({
            name: d.name,
            role: d.role,
            evidence: d.role_evidence,
            response_name: d.response_name,
            approver: d.approver_name,
            approver_id: d.approver_id,
            item_type: d.item_type,
            attachment_id: d.attachment_id,
            linked: d.is_release_linked,
            attached_as: d.attached ? `v${d.attached.version_number}` : null,
        })));
    }
    console.log('documents (full)', docs);

    if (payload.debug?.probe) {
        const probe = payload.debug.probe;
        console.groupCollapsed(`probe · attachment ${probe.attachment?.attachment_id}`);
        console.log('as the collector sees it', probe.attachment);
        if (probe.endpoints && console.table) {
            console.table(probe.endpoints.map((e) => ({
                url: e.url.replace('https://api.procore.com', ''),
                status: e.status,
                shape: e.shape?.type,
                mentions_attachment: e.mentions_attachment,
                mentions_approver: e.mentions_approver,
                response_names: (e.response_names || []).join(' | '),
                final_pdf_hits: (e.final_pdf_paths || []).length,
            })));
        }
        console.log('endpoints (full)', probe.endpoints);
        console.groupEnd();
    }

    if (payload.debug) {
        const dbg = payload.debug;
        console.groupCollapsed('raw Procore payloads');
        console.log('final-PDF-looking paths — submittal', dbg.final_pdf_paths?.submittal);
        console.log('final-PDF-looking paths — workflow_data', dbg.final_pdf_paths?.workflow_data);
        console.log('distributed_responses', dbg.distributed_responses);
        console.log('submittal.attachments', dbg.submittal_attachments);
        console.log('workflow_data.attachments', dbg.workflow_attachments);
        console.log('workflow_data.approvers', dbg.workflow_approvers);
        if (dbg.walked_files?.length && console.table) {
            // Where each file-ish object actually lives, and what response row it inherits.
            console.table(dbg.walked_files.map((f) => ({
                payload: f.payload,
                name: f.name,
                response_name: f.context?.response_name,
                approver_id: f.context?.approver_id,
                keys: (f.keys || []).join(', '),
            })));
        }
        console.log('top-level keys', {
            submittal: dbg.submittal_keys,
            workflow_data: dbg.workflow_keys,
        });
        console.groupEnd();
    }
    console.groupEnd();
}

export function ProcorePullDialog({
    isOpen,
    releaseId,
    label = '',
    onClose,
    /** (version) => void — the new drawing version, so the pane can select it. */
    onPulled = null,
}) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [needsSubmittal, setNeedsSubmittal] = useState(false);
    const [submittalId, setSubmittalId] = useState('');
    const [pulling, setPulling] = useState(null);   // attachment_id being pulled
    const [pulled, setPulled] = useState(null);     // last success, for the confirmation line

    const load = async (override = null, { debug = false, probe = null } = {}) => {
        setLoading(true);
        setError(null);
        try {
            const payload = await jobsApi.getReleaseProcoreDocuments(releaseId, {
                submittalId: override || null,
                debug,
                probe,
            });
            setData(payload);
            setNeedsSubmittal(false);
            logPayload(payload, releaseId);
        } catch (err) {
            setData(null);
            setError(err?.message || 'Failed to load Procore documents');
            // 409 = nothing resolved yet; the submittal-id box is the way through.
            setNeedsSubmittal(err?.statusCode === 409);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (!isOpen || releaseId == null) return;
        setPulled(null);
        setSubmittalId('');
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, releaseId]);

    useEffect(() => {
        if (!isOpen) return undefined;
        const onKey = (e) => {
            if (e.key !== 'Escape') return;
            e.stopPropagation();
            onClose?.();
        };
        window.addEventListener('keydown', onKey, true);
        return () => window.removeEventListener('keydown', onKey, true);
    }, [isOpen, onClose]);

    const pull = async (attachmentId) => {
        setPulling(attachmentId);
        setError(null);
        try {
            const result = await jobsApi.pullReleaseProcoreDocument(releaseId, attachmentId, {
                submittalId: data?.submittal?.resolved_by === 'override'
                    ? data.submittal.submittal_id
                    : null,
            });
            setPulled(result?.pulled || null);
            onPulled?.(result?.version || null);
            // Re-list so the row flips to "attached as vN".
            await load(data?.submittal?.resolved_by === 'override' ? data.submittal.submittal_id : null);
        } catch (err) {
            setError(err?.message || 'Pull failed');
        } finally {
            setPulling(null);
        }
    };

    if (!isOpen) return null;

    const documents = data?.documents || [];

    return createPortal(
        <div
            className="fixed inset-0 z-50 flex items-center justify-center"
            style={{ background: 'rgba(10,16,28,.55)', backdropFilter: 'blur(2px)' }}
            onClick={onClose}
        >
            <div
                className="bg-surface flex flex-col border border-hairline-strong"
                onClick={(e) => e.stopPropagation()}
                style={{
                    width: 'min(620px, 94vw)',
                    maxHeight: 'min(700px, 90dvh, 90vh)',
                    borderRadius: 14,
                    boxShadow: 'var(--shadow, 0 24px 60px rgba(15,26,48,.22))',
                }}
            >
                <div
                    className="shrink-0 flex items-start justify-between border-b border-hairline bg-surface-2"
                    style={{ padding: '14px 18px', borderRadius: '14px 14px 0 0' }}
                >
                    <div className="min-w-0">
                        <h2 className="font-bold text-ink truncate" style={{ fontSize: 17 }}>
                            Pull from Procore{label ? ` · ${label}` : ''}
                        </h2>
                        {!data?.submittal && (
                            <p className="text-ink-2" style={{ fontSize: 12.5, marginTop: 2 }}>
                                Finds the release’s Final PDF Pack and attaches it as a drawing version.
                            </p>
                        )}
                        {data?.submittal && (
                            <>
                                <p className="text-ink-2 truncate" style={{ fontSize: 13, marginTop: 3 }}>
                                    {data.submittal.title || `Submittal ${data.submittal.submittal_id}`}
                                </p>
                                <div className="flex items-center flex-wrap" style={{ gap: 6, marginTop: 5 }}>
                                    {[
                                        data.submittal.type,
                                        data.submittal.status,
                                        data.submittal.ball_in_court ? `BIC ${data.submittal.ball_in_court}` : null,
                                        data.submittal.rel ? `Rel ${data.submittal.rel}` : null,
                                    ].filter(Boolean).map((chip) => (
                                        <span
                                            key={chip}
                                            className="font-semibold"
                                            style={{
                                                fontSize: 11,
                                                padding: '1px 7px',
                                                borderRadius: 999,
                                                background: 'var(--surface)',
                                                color: 'var(--text-2)',
                                                boxShadow: 'inset 0 0 0 1px var(--border-strong)',
                                            }}
                                        >
                                            {chip}
                                        </span>
                                    ))}
                                </div>
                                <p className="text-ink-3" style={{ fontSize: 11.5, marginTop: 5 }}>
                                    #{data.submittal.submittal_id} · {RESOLVED_BY[data.submittal.resolved_by] || data.submittal.resolved_by}
                                    {data.submittal.procore_url && (
                                        <>
                                            {' · '}
                                            <a
                                                href={data.submittal.procore_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="font-semibold"
                                                style={{ color: 'var(--accent)' }}
                                            >
                                                open in Procore ↗
                                            </a>
                                        </>
                                    )}
                                </p>
                            </>
                        )}
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        className="grid place-items-center border border-hairline-strong rounded-[7px] bg-surface text-ink-2 hover:text-ink shrink-0"
                        style={{ width: 28, height: 28, marginLeft: 12 }}
                        aria-label="Close"
                    >
                        ×
                    </button>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto" style={{ padding: '14px 18px' }}>
                    {loading && <p className="text-ink-3 italic" style={{ fontSize: 13 }}>Asking Procore…</p>}

                    {!loading && error && (
                        <p
                            className="border border-hairline"
                            style={{
                                fontSize: 13,
                                padding: '10px 12px',
                                borderRadius: 8,
                                background: needsSubmittal ? 'var(--st-amber-bg)' : '#fef2f2',
                                color: needsSubmittal ? 'var(--st-amber-fg)' : 'var(--fl-red-bg)',
                            }}
                        >
                            {error}
                        </p>
                    )}

                    {!loading && pulled && (
                        <p
                            style={{
                                fontSize: 13,
                                padding: '10px 12px',
                                borderRadius: 8,
                                marginBottom: 12,
                                background: 'var(--st-green-bg)',
                                color: 'var(--st-green-fg)',
                            }}
                        >
                            ✓ Pulled {pulled.name || 'the drawing'}
                            {pulled.response_name ? ` (${pulled.response_name}` : ''}
                            {pulled.response_name && pulled.approver_name ? ` — ${pulled.approver_name}` : ''}
                            {pulled.response_name ? ')' : ''}
                            {' — '}
                            {pulled.render_fallback === 'raw_attachment'
                                ? 'clean copy — Procore would not render the marked-up version.'
                                : (pulled.carried_markup
                                    ? 'approver markups included.'
                                    : 'no markups reported by Procore.')}
                            {' It is now the newest version.'}
                        </p>
                    )}

                    {!loading && !error && documents.length === 0 && (
                        <p className="text-ink-3" style={{ fontSize: 13 }}>
                            That submittal has no downloadable drawing attachments. Procore can take
                            ~24h to publish the Final PDF Pack after approval.
                        </p>
                    )}

                    <ul className="space-y-2">
                        {documents.map((doc) => {
                            const role = ROLE[doc.role] || ROLE.submitted;
                            const busy = String(pulling) === String(doc.attachment_id);
                            const who = doc.approver_name || doc.created_by;
                            return (
                                <li
                                    key={doc.attachment_id}
                                    className="border bg-surface flex items-center gap-3"
                                    style={{
                                        borderRadius: 8,
                                        padding: '11px 12px',
                                        borderColor: doc.role === 'final_pack'
                                            ? 'var(--st-green-fg)' : 'var(--border)',
                                    }}
                                >
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="font-semibold text-ink truncate" style={{ fontSize: 13.5 }}>
                                                {doc.name || `Attachment ${doc.attachment_id}`}
                                            </span>
                                            <span
                                                className="font-semibold shrink-0"
                                                style={{
                                                    fontSize: 11,
                                                    padding: '1px 7px',
                                                    borderRadius: 999,
                                                    background: role.bg,
                                                    color: role.fg,
                                                }}
                                            >
                                                {doc.role === 'final_pack' ? `✓ ${role.text}` : role.text}
                                            </span>
                                            {doc.has_markup && (
                                                <span
                                                    className="font-semibold shrink-0"
                                                    style={{
                                                        fontSize: 11,
                                                        padding: '1px 7px',
                                                        borderRadius: 999,
                                                        background: 'var(--st-amber-bg)',
                                                        color: 'var(--st-amber-fg)',
                                                    }}
                                                    title="Approver markups are burned into the pulled file"
                                                >
                                                    marked up
                                                </span>
                                            )}
                                            {doc.attached && (
                                                <span
                                                    className="font-semibold shrink-0"
                                                    style={{
                                                        fontSize: 11,
                                                        padding: '1px 7px',
                                                        borderRadius: 999,
                                                        background: 'var(--accent-soft)',
                                                        color: 'var(--accent)',
                                                    }}
                                                >
                                                    v{doc.attached.version_number}
                                                </span>
                                            )}
                                        </div>
                                        {who && (
                                            <p className="text-ink-3" style={{ fontSize: 11.5, marginTop: 3 }}>
                                                {who}
                                            </p>
                                        )}
                                    </div>

                                    <div className="shrink-0 flex items-center" style={{ gap: 10 }}>
                                        <button
                                            type="button"
                                            onClick={() => load(
                                                submittalId.trim() || null,
                                                { probe: doc.attachment_id },
                                            )}
                                            disabled={loading}
                                            className="bg-transparent border-0 cursor-pointer disabled:opacity-50"
                                            style={{ fontSize: 11.5, color: 'var(--text-3)' }}
                                            title="Take this attachment's ids back to Procore and print what each endpoint returns"
                                        >
                                            probe
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => pull(doc.attachment_id)}
                                            disabled={busy || pulling != null}
                                            className="font-semibold text-white bg-accent-600 disabled:opacity-50"
                                            style={{ height: 28, padding: '0 12px', borderRadius: 7, border: 0, fontSize: 13 }}
                                        >
                                            {busy ? 'Pulling…' : (doc.attached ? 'Pull again' : 'Pull')}
                                        </button>
                                    </div>
                                </li>
                            );
                        })}
                    </ul>
                </div>

                {/* Gap/testing escape hatch: point the pull at any submittal by id. */}
                <div
                    className="shrink-0 border-t border-hairline bg-surface-2 flex items-center gap-2 flex-wrap"
                    style={{ padding: '10px 18px', borderRadius: '0 0 14px 14px' }}
                >
                    <label className="text-ink-3" style={{ fontSize: 12 }} htmlFor="pull-submittal-id">
                        Submittal id
                    </label>
                    <input
                        id="pull-submittal-id"
                        value={submittalId}
                        onChange={(e) => setSubmittalId(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter' && submittalId.trim()) load(submittalId.trim()); }}
                        placeholder={data?.submittal?.submittal_id || 'e.g. 1234567'}
                        className="border border-hairline-strong bg-surface text-ink"
                        style={{ height: 28, padding: '0 8px', borderRadius: 7, fontSize: 13, width: 150 }}
                    />
                    <button
                        type="button"
                        onClick={() => load(submittalId.trim() || null)}
                        disabled={loading}
                        className="border border-hairline-strong bg-surface text-ink-2 font-semibold hover:bg-surface disabled:opacity-50"
                        style={{ height: 28, padding: '0 11px', borderRadius: 7, fontSize: 13 }}
                    >
                        {submittalId.trim() ? 'Look up' : 'Refresh'}
                    </button>
                    <button
                        type="button"
                        onClick={() => load(submittalId.trim() || null, { debug: true })}
                        disabled={loading}
                        className="border border-hairline-strong bg-surface text-ink-3 font-semibold hover:bg-surface disabled:opacity-50"
                        style={{ height: 28, padding: '0 11px', borderRadius: 7, fontSize: 13 }}
                        title="Re-fetch with Procore's raw payloads and print them to the browser console"
                    >
                        Dump raw → console
                    </button>
                    <span className="text-ink-3" style={{ fontSize: 11.5 }}>
                        Overrides the link when the worker hasn’t found the pack yet.
                    </span>
                </div>
            </div>
        </div>,
        document.body,
    );
}

export default ProcorePullDialog;
