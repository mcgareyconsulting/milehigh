/**
 * Fullscreen PDF markup modal — renders a release's drawing version with
 * pdf.js's built-in AnnotationEditor (pen + text), and saves the result as
 * the next version via POST /brain/releases/<id>/drawing.
 *
 * Tablet-friendly: native pointer events, large toolbar hit targets,
 * touch-action: none on the canvas wrapper to suppress scroll/pinch hijack.
 */
import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import * as pdfjsLib from 'pdfjs-dist';
import { EventBus, PDFLinkService, PDFViewer } from 'pdfjs-dist/web/pdf_viewer.mjs';
import 'pdfjs-dist/web/pdf_viewer.css';
import workerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
import { API_BASE_URL } from '../utils/api';

if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
}

// Stable, content-based fingerprint for an annotation. pdf.js IDs are not
// reliable across saveDocument(), so we identify by (subtype + page +
// rounded rect + content sample). Used to map carried-over annotations to
// the version they first appeared in.
function fingerprintAnnotation(ann, pageNum) {
    const rect = (ann.rect || []).map((n) => Math.round(n)).join(',');
    let extra = '';
    if (ann.subtype === 'FreeText') {
        extra = (ann.contents || '').slice(0, 200);
    } else if (ann.subtype === 'Ink' && Array.isArray(ann.inkLists)) {
        const pts = ann.inkLists.flat().slice(0, 24)
            .map((p) => `${Math.round(p.x)},${Math.round(p.y)}`).join(';');
        extra = pts;
    }
    return `p${pageNum}:${ann.subtype}:${rect}:${extra}`;
}

const COLORS = ['#FF0000', '#000000', '#1F77B4', '#2CA02C', '#FFD500'];

const TOOL = {
    // pdf.js's PDFViewer rejects DISABLE (-1) — initializing with it prevents
    // the editor UIManager from being created, breaking later switches to
    // INK/FREETEXT. Use NONE here and suppress annotation interaction with
    // CSS (data-tool="hand" on the container disables pointer events on the
    // editor layer) when the user picks Hand.
    HAND: pdfjsLib.AnnotationEditorType.NONE,
    INK: pdfjsLib.AnnotationEditorType.INK,
    FREETEXT: pdfjsLib.AnnotationEditorType.FREETEXT,
};

export function PdfMarkupModal({
    isOpen,
    releaseId,
    versionId,
    mode = 'edit',
    onClose,
    onSaved,
}) {
    const containerRef = useRef(null);
    const viewerStateRef = useRef({
        pdfDocument: null,
        pdfViewer: null,
        eventBus: null,
        loadingTask: null,
    });

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [saving, setSaving] = useState(false);
    const [tool, setTool] = useState(TOOL.HAND);
    const [color, setColor] = useState(COLORS[0]);
    const [fontSize, setFontSize] = useState(16);
    const [note, setNote] = useState('');
    const [dirty, setDirty] = useState(false);
    const [ticks, setTicks] = useState([]);  // scrollbar ticks for each annotation

    const isEdit = mode === 'edit';

    // Load PDF + initialize viewer
    useEffect(() => {
        if (!isOpen || !releaseId) return;
        let cancelled = false;
        const container = containerRef.current;
        if (!container) return;

        setLoading(true);
        setError(null);
        setDirty(false);
        setTool(TOOL.HAND);
        setTicks([]);
        setNote('');  // optional save-note resets every time the editor opens

        const init = async () => {
            try {
                const filePath = versionId
                    ? `${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions/${versionId}/file`
                    : null;
                const url = filePath ?? `${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions/latest/file`;
                const resp = await fetch(url, { credentials: 'include' });
                if (!resp.ok) throw new Error(`HTTP ${resp.status} loading PDF`);
                const data = new Uint8Array(await resp.arrayBuffer());
                if (cancelled) return;

                const eventBus = new EventBus();
                const linkService = new PDFLinkService({ eventBus });
                const pdfViewer = new PDFViewer({
                    container,
                    eventBus,
                    linkService,
                    annotationEditorMode: TOOL.HAND,
                });
                linkService.setViewer(pdfViewer);

                eventBus.on('pagesinit', () => {
                    // 'page-fit' shows the whole page; 'auto' / 'page-width' often
                    // over-zoom wide FC drawings on big screens.
                    pdfViewer.currentScaleValue = 'page-fit';
                });
                eventBus.on('annotationeditorstateschanged', () => {
                    setDirty(true);
                });

                const refreshTicks = async () => {
                    const doc = viewerStateRef.current.pdfDocument;
                    const viewer = viewerStateRef.current.pdfViewer;
                    const containerEl = containerRef.current;
                    if (!doc || !viewer || !containerEl) return;
                    const collected = [];
                    for (let pageNum = 1; pageNum <= doc.numPages; pageNum++) {
                        let page;
                        try { page = await doc.getPage(pageNum); } catch { continue; }
                        const pageView = viewer.getPageView(pageNum - 1);
                        if (!pageView || !pageView.viewport || !pageView.div) continue;
                        const viewport = pageView.viewport;
                        const pageOffsetTop = pageView.div.offsetTop;
                        let annots;
                        try { annots = await page.getAnnotations({ intent: 'display' }); } catch { continue; }
                        const originMap = viewerStateRef.current.originByFingerprint || new Map();
                        const currentVer = viewerStateRef.current.currentVersionNumber;
                        for (const ann of annots) {
                            if (!['FreeText', 'Ink', 'Stamp'].includes(ann.subtype)) continue;
                            const [x1, y1, x2, y2] = viewport.convertToViewportRectangle(ann.rect);
                            const top = Math.min(y1, y2);
                            const fp = fingerprintAnnotation(ann, pageNum);
                            const versionNumber = originMap.has(fp) ? originMap.get(fp) : currentVer;
                            collected.push({
                                id: `p${pageNum}-${ann.id || `${x1},${y1}`}`,
                                page: pageNum,
                                absoluteY: pageOffsetTop + top,
                                type: ann.subtype,
                                versionNumber,
                            });
                        }
                    }
                    const scrollHeight = containerEl.scrollHeight || 1;
                    setTicks(collected.map((t) => ({
                        ...t,
                        proportion: Math.max(0, Math.min(1, t.absoluteY / scrollHeight)),
                    })));
                };

                eventBus.on('pagesloaded', () => { refreshTicks(); });
                // Recompute after a zoom change once the new scale's pages are laid out
                eventBus.on('scalechanging', () => { setTimeout(refreshTicks, 100); });

                // Cheap version-meta lookup BEFORE setDocument so the current
                // version number is set when pagesloaded fires.
                viewerStateRef.current.originByFingerprint = new Map();
                viewerStateRef.current.currentVersionNumber = null;
                let lineageChain = [];
                try {
                    const versionsResp = await fetch(
                        `${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions`,
                        { credentials: 'include' },
                    );
                    if (versionsResp.ok) {
                        const versionsData = await versionsResp.json();
                        const allVersions = versionsData?.versions || [];
                        const byId = new Map(allVersions.map((v) => [v.id, v]));
                        const currentMeta = byId.get(versionId);
                        viewerStateRef.current.currentVersionNumber = currentMeta?.version_number ?? null;
                        const safety = new Set();
                        let cur = currentMeta;
                        while (cur && !safety.has(cur.id)) {
                            safety.add(cur.id);
                            lineageChain.unshift(cur);
                            cur = cur.source_version_id ? byId.get(cur.source_version_id) : null;
                        }
                    }
                } catch (metaErr) {
                    console.warn('Failed to load version metadata:', metaErr);
                }

                const loadingTask = pdfjsLib.getDocument({ data });
                viewerStateRef.current.loadingTask = loadingTask;
                const pdfDocument = await loadingTask.promise;
                if (cancelled) return;

                pdfViewer.setDocument(pdfDocument);
                linkService.setDocument(pdfDocument, null);

                viewerStateRef.current.pdfDocument = pdfDocument;
                viewerStateRef.current.pdfViewer = pdfViewer;
                viewerStateRef.current.eventBus = eventBus;

                setLoading(false);

                // Background lineage walk: fingerprint each ancestor's
                // annotations so carried-over ticks can be stamped with their
                // origin version. Re-runs refreshTicks when done.
                (async () => {
                    for (const v of lineageChain) {
                        if (cancelled) return;
                        if (v.id === versionId) continue;
                        try {
                            const r = await fetch(
                                `${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions/${v.id}/file`,
                                { credentials: 'include' },
                            );
                            if (!r.ok) continue;
                            const bytes = new Uint8Array(await r.arrayBuffer());
                            const ancDoc = await pdfjsLib.getDocument({ data: bytes }).promise;
                            for (let p = 1; p <= ancDoc.numPages; p++) {
                                const pg = await ancDoc.getPage(p);
                                const anns = await pg.getAnnotations({ intent: 'display' });
                                for (const a of anns) {
                                    if (!['FreeText', 'Ink', 'Stamp'].includes(a.subtype)) continue;
                                    const fp = fingerprintAnnotation(a, p);
                                    if (!viewerStateRef.current.originByFingerprint.has(fp)) {
                                        viewerStateRef.current.originByFingerprint.set(fp, v.version_number);
                                    }
                                }
                            }
                            ancDoc.destroy();
                        } catch (ancErr) {
                            console.warn(`Lineage scan failed for version ${v.id}:`, ancErr);
                        }
                    }
                    if (!cancelled) refreshTicks();
                })();
            } catch (err) {
                if (cancelled) return;
                setError(err?.message || 'Failed to load drawing');
                setLoading(false);
            }
        };

        init();

        return () => {
            cancelled = true;
            const state = viewerStateRef.current;
            try { state.loadingTask?.destroy?.(); } catch { /* noop */ }
            try { state.pdfViewer?.cleanup?.(); } catch { /* noop */ }
            try { state.pdfDocument?.destroy?.(); } catch { /* noop */ }
            viewerStateRef.current = { pdfDocument: null, pdfViewer: null, eventBus: null, loadingTask: null };
        };
    }, [isOpen, releaseId, versionId]);

    // Apply tool changes to the viewer
    useEffect(() => {
        const pdfViewer = viewerStateRef.current.pdfViewer;
        if (!pdfViewer || !isEdit) return;
        try {
            pdfViewer.annotationEditorMode = { mode: tool };
        } catch {
            // pdfViewer not yet ready — ignored, will retry on next state change.
        }
    }, [tool, isEdit]);

    // Apply color changes. The right API in pdf.js 4.x is dispatching
    // 'switchannotationeditorparams' on the EventBus — there is no
    // pdfViewer.annotationEditorParams setter. The UI manager applies the
    // value to the selected editor AND updates the default for next-created.
    useEffect(() => {
        const eventBus = viewerStateRef.current.eventBus;
        if (!eventBus || !isEdit) return;
        const params = pdfjsLib.AnnotationEditorParamsType;
        try {
            if (tool === TOOL.INK && params?.INK_COLOR != null) {
                eventBus.dispatch('switchannotationeditorparams', { type: params.INK_COLOR, value: color });
            } else if (tool === TOOL.FREETEXT && params?.FREETEXT_COLOR != null) {
                eventBus.dispatch('switchannotationeditorparams', { type: params.FREETEXT_COLOR, value: color });
            }
        } catch { /* swallow */ }
    }, [color, tool, isEdit]);

    // Apply font size changes. Same dispatch pattern as color.
    useEffect(() => {
        const eventBus = viewerStateRef.current.eventBus;
        if (!eventBus || !isEdit || tool !== TOOL.FREETEXT) return;
        const params = pdfjsLib.AnnotationEditorParamsType;
        try {
            if (params?.FREETEXT_SIZE != null) {
                eventBus.dispatch('switchannotationeditorparams', { type: params.FREETEXT_SIZE, value: fontSize });
            }
        } catch { /* swallow */ }
    }, [fontSize, tool, isEdit]);

    // Esc-to-close
    useEffect(() => {
        if (!isOpen) return;
        const onKey = (e) => {
            if (e.key === 'Escape') tryClose();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, dirty]);

    const adjustZoom = (delta) => {
        const pdfViewer = viewerStateRef.current.pdfViewer;
        if (!pdfViewer) return;
        const current = pdfViewer.currentScale || 1;
        const next = Math.min(8, Math.max(0.25, current * delta));
        pdfViewer.currentScale = next;
    };

    const fitToPage = () => {
        const pdfViewer = viewerStateRef.current.pdfViewer;
        if (!pdfViewer) return;
        pdfViewer.currentScaleValue = 'page-fit';
    };

    const fitToWidth = () => {
        const pdfViewer = viewerStateRef.current.pdfViewer;
        if (!pdfViewer) return;
        pdfViewer.currentScaleValue = 'page-width';
    };

    const tryClose = () => {
        if (dirty && isEdit) {
            const ok = window.confirm('Discard unsaved markup?');
            if (!ok) return;
        }
        onClose?.();
    };

    const handleSave = async () => {
        const pdfDocument = viewerStateRef.current.pdfDocument;
        if (!pdfDocument || saving) return;
        setSaving(true);
        try {
            const bytes = await pdfDocument.saveDocument();
            const fd = new FormData();
            fd.append('file', new Blob([bytes], { type: 'application/pdf' }), 'markup.pdf');
            if (versionId != null) fd.append('source_version_id', String(versionId));
            if (note.trim()) fd.append('note', note.trim());

            const resp = await fetch(`${API_BASE_URL}/brain/releases/${releaseId}/drawing`, {
                method: 'POST',
                body: fd,
                credentials: 'include',
            });
            if (!resp.ok) {
                const errBody = await resp.text();
                throw new Error(`Save failed (${resp.status}): ${errBody.slice(0, 200)}`);
            }
            const newVersion = await resp.json();
            setDirty(false);
            onSaved?.(newVersion);
            onClose?.();
        } catch (err) {
            setError(err?.message || 'Save failed');
        } finally {
            setSaving(false);
        }
    };

    if (!isOpen) return null;

    const toolBtn = (label, value, ariaLabel) => (
        <button
            type="button"
            onClick={() => setTool(value)}
            aria-label={ariaLabel || label}
            className={`px-4 py-3 min-w-[56px] min-h-[44px] rounded-md text-sm font-semibold border ${
                tool === value
                    ? 'bg-accent-600 text-white border-accent-600'
                    : 'bg-white text-gray-800 border-gray-300 hover:bg-gray-100'
            }`}
        >
            {label}
        </button>
    );

    return createPortal(
        <div className="fixed inset-0 z-50 flex flex-col bg-gray-900 bg-opacity-95">
            {/* Hide pdf.js's floating per-editor delete/altText buttons — they
                land in odd spots; users delete annotations with Backspace/Delete. */}
            <style>{`
                .pdfViewer .editToolbar,
                .pdfViewer button.delete,
                .pdfViewer button.altText { display: none !important; }

                /* Outer wrapper of a text annotation = drag/move zone (edge of box).
                   Inner .internal contenteditable = text-edit zone. The outer div
                   has padding so there's an actual ring around the text where the
                   cursor reads as "move". */
                .annotationEditorLayer .freeTextEditor { cursor: move !important; }
                .annotationEditorLayer .freeTextEditor > .internal { cursor: text !important; }

                /* Hand mode: existing annotations stay visible but become
                   non-interactive (no select/drag/edit). Pen/Text re-enable. */
                [data-tool="hand"] .annotationEditorLayer,
                [data-tool="hand"] .annotationEditorLayer * {
                    pointer-events: none !important;
                }

                /* Suppress pdf.js's hover popup for saved annotations — it
                   surfaces a yellow tooltip with the annotation's contents
                   that misrenders for rotated FreeText. The annotation itself
                   is still visible, just no hover bubble. */
                .annotationLayer .popupAnnotation,
                .annotationLayer .popup,
                .annotationLayer .popupWrapper {
                    display: none !important;
                }
            `}</style>
            <div className="flex items-center gap-2 px-3 py-2 bg-white border-b border-gray-200 shadow-sm flex-wrap">
                <span className="font-semibold text-gray-800 mr-2">Drawing markup</span>
                <div className="flex items-center gap-1 mr-2">
                    <button
                        type="button"
                        onClick={() => adjustZoom(0.8)}
                        className="px-3 py-3 min-w-[44px] min-h-[44px] rounded-md text-sm font-semibold border bg-white text-gray-800 border-gray-300 hover:bg-gray-100"
                        aria-label="Zoom out"
                        title="Zoom out"
                    >−</button>
                    <button
                        type="button"
                        onClick={() => adjustZoom(1.25)}
                        className="px-3 py-3 min-w-[44px] min-h-[44px] rounded-md text-sm font-semibold border bg-white text-gray-800 border-gray-300 hover:bg-gray-100"
                        aria-label="Zoom in"
                        title="Zoom in"
                    >+</button>
                    <button
                        type="button"
                        onClick={fitToPage}
                        className="px-3 py-3 min-h-[44px] rounded-md text-sm font-semibold border bg-white text-gray-800 border-gray-300 hover:bg-gray-100"
                        title="Fit page"
                    >Fit</button>
                    <button
                        type="button"
                        onClick={fitToWidth}
                        className="px-3 py-3 min-h-[44px] rounded-md text-sm font-semibold border bg-white text-gray-800 border-gray-300 hover:bg-gray-100"
                        title="Fit width"
                    >Width</button>
                </div>
                {isEdit && (
                    <>
                        {toolBtn('Hand', TOOL.HAND, 'Move/select')}
                        {toolBtn('Pen', TOOL.INK)}
                        {toolBtn('Text', TOOL.FREETEXT)}
                        {tool === TOOL.FREETEXT && (
                            <div className="flex items-center gap-1 ml-2">
                                <button
                                    type="button"
                                    onClick={() => setFontSize((s) => Math.max(8, s - 2))}
                                    className="px-3 py-3 min-w-[44px] min-h-[44px] rounded-md text-sm font-semibold border bg-white text-gray-800 border-gray-300 hover:bg-gray-100"
                                    title="Smaller text"
                                    aria-label="Decrease font size"
                                >A−</button>
                                <span className="px-2 text-sm text-gray-700 select-none min-w-[36px] text-center">{fontSize}</span>
                                <button
                                    type="button"
                                    onClick={() => setFontSize((s) => Math.min(96, s + 2))}
                                    className="px-3 py-3 min-w-[44px] min-h-[44px] rounded-md text-sm font-semibold border bg-white text-gray-800 border-gray-300 hover:bg-gray-100"
                                    title="Larger text"
                                    aria-label="Increase font size"
                                >A+</button>
                            </div>
                        )}
                        <div className="flex items-center gap-1 ml-2">
                            {COLORS.map((c) => (
                                <button
                                    key={c}
                                    type="button"
                                    onClick={() => setColor(c)}
                                    aria-label={`Color ${c}`}
                                    className={`w-9 h-9 rounded-full border-2 ${color === c ? 'border-accent-600 ring-2 ring-accent-300' : 'border-gray-300'}`}
                                    style={{ backgroundColor: c }}
                                />
                            ))}
                        </div>
                        <input
                            type="text"
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                            placeholder="Note (optional)"
                            className="ml-2 px-3 py-2 border border-gray-300 rounded-md text-sm w-56"
                        />
                        <button
                            type="button"
                            onClick={handleSave}
                            disabled={saving || loading}
                            className="ml-2 px-4 py-3 min-h-[44px] bg-accent-600 text-white rounded-md font-semibold disabled:opacity-60"
                        >
                            {saving ? 'Saving…' : 'Save version'}
                        </button>
                    </>
                )}
                <button
                    type="button"
                    onClick={tryClose}
                    className="ml-auto px-4 py-3 min-h-[44px] bg-white text-gray-800 border border-gray-300 rounded-md font-semibold hover:bg-gray-100"
                >
                    Close
                </button>
            </div>

            {error && (
                <div className="px-4 py-2 bg-red-100 text-red-800 text-sm border-b border-red-200">
                    {error}
                </div>
            )}

            <div className="flex-1 relative bg-gray-700">
                <div
                    ref={containerRef}
                    className="absolute inset-0 overflow-auto"
                    style={{ touchAction: 'none', position: 'absolute' }}
                    data-tool={tool === TOOL.HAND ? 'hand' : tool === TOOL.INK ? 'pen' : 'text'}
                >
                    <div className="pdfViewer" />
                </div>

                {/* Annotation ticks overlaid on the right edge of the scroll track.
                    Click jumps the scroll container to that annotation. */}
                {ticks.length > 0 && (
                    <div
                        className="absolute top-0 bottom-0 right-0 pointer-events-none"
                        style={{ width: '44px', backgroundColor: 'rgba(0,0,0,0.25)' }}
                        title={`${ticks.length} annotation${ticks.length === 1 ? '' : 's'} in this version`}
                    >
                        {ticks.map((t) => {
                            const tickColor = t.type === 'FreeText' ? '#FFD500' : (t.type === 'Ink' ? '#FF3B30' : '#1F77B4');
                            const versionLabel = t.versionNumber != null ? `v${t.versionNumber}` : '';
                            return (
                                <button
                                    key={t.id}
                                    type="button"
                                    onClick={() => {
                                        const c = containerRef.current;
                                        if (!c) return;
                                        c.scrollTo({ top: Math.max(0, t.absoluteY - 60), behavior: 'smooth' });
                                    }}
                                    className="absolute right-1 pointer-events-auto rounded shadow hover:scale-110 transition-transform flex items-center justify-center"
                                    style={{
                                        top: `calc(${t.proportion * 100}% - 9px)`,
                                        height: '18px',
                                        width: '36px',
                                        backgroundColor: tickColor,
                                        color: '#1f2937',
                                        fontSize: '11px',
                                        fontWeight: 700,
                                        lineHeight: 1,
                                        border: '1.5px solid rgba(0,0,0,0.65)',
                                    }}
                                    title={`${versionLabel} — Page ${t.page} — ${t.type}`}
                                    aria-label={`Jump to ${t.type} on page ${t.page}, ${versionLabel}`}
                                >
                                    {versionLabel || '·'}
                                </button>
                            );
                        })}
                    </div>
                )}

                {loading && (
                    <div className="absolute inset-0 flex items-center justify-center text-white text-lg pointer-events-none">
                        Loading drawing…
                    </div>
                )}
            </div>
        </div>,
        document.body,
    );
}

export default PdfMarkupModal;
