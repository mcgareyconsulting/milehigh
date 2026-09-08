/**
 * Fullscreen PDF markup modal — renders a release's drawing version with
 * pdf.js's built-in AnnotationEditor (pen + text) plus shape tools
 * (line/arrow/box/circle) and a stroke-thickness control, and saves the result
 * as the next version via POST /brain/releases/<id>/drawing.
 *
 * Shapes have no native pdf.js editor: a transparent overlay captures the drag
 * and the result is injected as an Ink annotation (built from point paths) so
 * it persists via saveDocument() and behaves like any other annotation.
 *
 * Tablet-friendly: native pointer events, large toolbar hit targets. The scroll
 * container allows one-finger pan in Hand mode and suppresses touch while a
 * drawing tool is active; two-finger pinch-to-zoom is handled explicitly.
 *
 * `inline` drops the fixed overlay and the portal so the same editor can be hosted inside
 * another surface — the release hub's Attachments pane runs it in place of the read
 * viewer. Inline also means another dialog owns Escape, so this one claims it in capture.
 *
 * Undo / redo / delete ride pdf.js's own command stack (every pen stroke, text box,
 * injected shape, move, resize, restyle and delete is a command), surfaced as buttons in
 * the pill and as Ctrl/⌘+Z, Ctrl+Y / ⌘⇧Z and Delete. pdf.js only services those keys
 * while a drawing tool is armed, so Hand mode gets its own handler that calls the same
 * UIManager methods — the shortcuts work whatever tool is up.
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

// Option 4c palette. Applies to NEW annotations; existing ones keep the color they
// were saved with.
const COLORS = ['#dc2626', '#111827', '#2563eb', '#16a34a', '#eab308'];

const TOOL = {
    // pdf.js's PDFViewer rejects DISABLE (-1) — initializing with it prevents
    // the editor UIManager from being created, breaking later switches to
    // INK/FREETEXT. Use NONE here and suppress annotation interaction with
    // CSS (data-tool="hand" on the container disables pointer events on the
    // editor layer) when the user picks Hand.
    HAND: pdfjsLib.AnnotationEditorType.NONE,
    INK: pdfjsLib.AnnotationEditorType.INK,
    FREETEXT: pdfjsLib.AnnotationEditorType.FREETEXT,
    // Shape tools have no native pdf.js editor — they are drawn through an
    // input overlay and committed as Ink annotations (see commitShape). String
    // sentinels keep them distinct from the numeric AnnotationEditorType values.
    LINE: 'line',
    ARROW: 'arrow',
    SQUARE: 'square',
    CIRCLE: 'circle',
};

const SHAPE_TOOLS = new Set([TOOL.LINE, TOOL.ARROW, TOOL.SQUARE, TOOL.CIRCLE]);
const isShapeTool = (t) => SHAPE_TOOLS.has(t);

// Stroke-width presets shared by the pen and shapes (pdf.js "thickness" units).
const THICKNESS = { Thin: 2, Medium: 6, Thick: 12 };

function hexToRgbArray(hex) {
    const h = hex.replace('#', '');
    return [
        parseInt(h.slice(0, 2), 16),
        parseInt(h.slice(2, 4), 16),
        parseInt(h.slice(4, 6), 16),
    ];
}

// pdf.js reports editor colors as hex ("#dc2626"); anything else (a CSS keyword such
// as "CanvasText") is not a value the palette can show, so it is ignored.
function normalizeHex(value) {
    if (typeof value !== 'string') return null;
    const v = value.trim().toLowerCase();
    if (/^#[0-9a-f]{6}$/.test(v)) return v;
    if (/^#[0-9a-f]{3}$/.test(v)) return `#${v[1]}${v[1]}${v[2]}${v[2]}${v[3]}${v[3]}`;
    return null;
}

const IS_MAC = typeof navigator !== 'undefined'
    && /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent || '');
const UNDO_KEYS = IS_MAC ? '⌘Z' : 'Ctrl+Z';
const REDO_KEYS = IS_MAC ? '⌘⇧Z' : 'Ctrl+Y';

// True when the keystroke belongs to a text field — the note box, the comment composer,
// or a text annotation being typed into — so markup shortcuts must leave it alone.
function isTypingTarget(el) {
    return !!el && (el.isContentEditable
        || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
}

// Two arrowhead barbs for an arrow from s -> e (page-space points).
function arrowHeadPoints(s, e) {
    const ang = Math.atan2(e.y - s.y, e.x - s.x);
    const len = 18;
    const spread = Math.PI / 7;
    return {
        a: { x: e.x - len * Math.cos(ang - spread), y: e.y - len * Math.sin(ang - spread) },
        b: { x: e.x - len * Math.cos(ang + spread), y: e.y - len * Math.sin(ang + spread) },
    };
}

// Build a shape as a list of polylines (each an array of {x,y}) in page space.
// Rect/arrow use separate 2-point segments so corners stay crisp (pdf.js
// bezier-smooths long polylines); the circle uses one sampled polyline.
function buildShapeCssPaths(shape, s, e) {
    switch (shape) {
        case TOOL.LINE:
            return [[s, e]];
        case TOOL.ARROW: {
            const { a, b } = arrowHeadPoints(s, e);
            return [[s, e], [a, e], [b, e]];
        }
        case TOOL.SQUARE: {
            const p1 = { x: s.x, y: s.y };
            const p2 = { x: e.x, y: s.y };
            const p3 = { x: e.x, y: e.y };
            const p4 = { x: s.x, y: e.y };
            return [[p1, p2], [p2, p3], [p3, p4], [p4, p1]];
        }
        case TOOL.CIRCLE: {
            const cx = (s.x + e.x) / 2;
            const cy = (s.y + e.y) / 2;
            const rx = Math.abs(e.x - s.x) / 2;
            const ry = Math.abs(e.y - s.y) / 2;
            const N = 64;
            const pts = [];
            for (let i = 0; i <= N; i++) {
                const a = (i / N) * 2 * Math.PI;
                pts.push({ x: cx + rx * Math.cos(a), y: cy + ry * Math.sin(a) });
            }
            // Emit consecutive points as separate straight chords rather than one
            // closed polyline: pdf.js bezier-smooths long polylines, and the seam
            // of a closed loop produces control-point overshoot that inflates the
            // bounding box. 64 short chords read as a smooth ellipse but give an
            // exact bbox (same approach as the square's edges).
            const segments = [];
            for (let i = 0; i < pts.length - 1; i++) {
                segments.push([pts[i], pts[i + 1]]);
            }
            return segments;
        }
        default:
            return [];
    }
}

export function PdfMarkupModal({
    isOpen,
    releaseId,
    versionId,
    fileUrl,           // read-only: load this PDF URL directly (bypasses release/version)
    title = 'Drawing markup',
    mode = 'edit',
    inline = false,
    /** 'window' = this component's own toolbar chrome. 'hybrid' = Option 4c: tools live in
     *  the floating pill, and the note + Save version appear above it only when there is
     *  uncommitted markup. */
    variant = 'window',
    /** hybrid: report state the host's chrome renders (markup list, unsaved). */
    onMarkupsChange = null,
    onDirtyChange = null,
    onSavingChange = null,
    /** hybrid: page count once pdf.js has laid the set out (0 while loading). */
    onNumPages = null,
    initialPage = null,
    citeNonce = null,
    onClose,
    onSaved,
}) {
    const containerRef = useRef(null);
    // Always holds the latest requested page so the pdf.js 'pagesloaded'
    // listener (created once inside init) can jump without a stale closure.
    const initialPageRef = useRef(initialPage);
    initialPageRef.current = initialPage;
    const overlayRef = useRef(null);
    const shapeStartRef = useRef(null);  // { x, y } client coords of the in-progress shape
    const viewerStateRef = useRef({
        pdfDocument: null,
        pdfViewer: null,
        eventBus: null,
        loadingTask: null,
        uiManager: null,
    });

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [saving, setSaving] = useState(false);
    const savingRef = useRef(false);   // synchronous double-submit guard; see handleSave
    const [tool, setTool] = useState(TOOL.HAND);
    const [color, setColor] = useState(COLORS[0]);
    const [fontSize, setFontSize] = useState(16);
    const [thickness, setThickness] = useState(THICKNESS.Medium);
    const [note, setNote] = useState('');
    const [dirty, setDirty] = useState(false);
    const [ticks, setTicks] = useState([]);  // scrollbar ticks for each annotation
    const [shapeDraft, setShapeDraft] = useState(null);  // { sx, sy, ex, ey } overlay-relative preview
    const [hasSelection, setHasSelection] = useState(false);  // an editor is currently selected
    const [canUndo, setCanUndo] = useState(false);
    const [canRedo, setCanRedo] = useState(false);
    // Same flags, readable from window key handlers without a stale closure.
    const undoStackRef = useRef({ canUndo: false, canRedo: false });
    // Mirrored from the pdf.js viewer for the Option 4c pill.
    const [pageNumber, setPageNumber] = useState(1);
    const [pagesCount, setPagesCount] = useState(0);
    const [scalePct, setScalePct] = useState(100);
    const [fitMode, setFitMode] = useState('fit');   // 'fit' | 'width' | null (manual zoom)
    // The selected markup, mirrored from pdf.js: { kind: 'freetext' | 'ink' | null,
    // color, thickness, fontSize }. `color` / `thickness` / `fontSize` above are the
    // DEFAULTS for the next markup (pdf.js's own defaults after the first push); while
    // something is selected the pill shows the selection's values instead, and a
    // control click restyles the selection and moves the default in one dispatch.
    const [selection, setSelection] = useState(null);
    const selectedKind = selection?.kind ?? null;
    const shownColor = selection ? (selection.color ?? null) : color;
    const shownThickness = selectedKind === 'ink' && selection.thickness ? selection.thickness : thickness;
    const shownFontSize = selectedKind === 'freetext' && selection.fontSize ? selection.fontSize : fontSize;
    // Latest defaults for pdf.js listeners and effects that must not close over a render.
    const paramsRef = useRef({ color, thickness, fontSize });
    paramsRef.current = { color, thickness, fontSize };

    const isEdit = mode === 'edit';
    const hybrid = variant === 'hybrid';
    const noteValue = note;
    const setNoteValue = setNote;

    // Load PDF + initialize viewer
    useEffect(() => {
        if (!isOpen || (!releaseId && !fileUrl)) return;
        let cancelled = false;
        const container = containerRef.current;
        if (!container) return;

        setLoading(true);
        setError(null);
        setDirty(false);
        setTool(TOOL.HAND);
        setTicks([]);
        setShapeDraft(null);
        shapeStartRef.current = null;
        setHasSelection(false);
        setSelection(null);
        setCanUndo(false);
        setCanRedo(false);
        undoStackRef.current = { canUndo: false, canRedo: false };
        setNote('');  // optional save-note resets every time the editor opens

        const init = async () => {
            try {
                const url = fileUrl
                    ? fileUrl
                    : (versionId
                        ? `${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions/${versionId}/file`
                        : `${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions/latest/file`);
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

                eventBus.on('pagechanging', (e) => {
                    if (e?.pageNumber) setPageNumber(e.pageNumber);
                });
                eventBus.on('scalechanging', (e) => {
                    if (e?.scale) setScalePct(Math.round(e.scale * 100));
                });
                eventBus.on('pagesinit', () => {
                    setPagesCount(pdfViewer.pagesCount || 0);
                    setScalePct(Math.round((pdfViewer.currentScale || 1) * 100));
                    setFitMode('fit');
                    // Inline review pane: fit width so the sheet fills the column and
                    // dimensions are legible (fit-page leaves it tiny in a tall pane).
                    // Fullscreen markup: 'page-fit' shows the whole sheet to work on.
                    // Whole sheet by default everywhere except the thin inline review pane,
                    // where fit-page leaves the drawing unreadably small.
                    pdfViewer.currentScaleValue = (inline && !hybrid) ? 'page-width' : 'page-fit';
                });
                // pdf.js merges every change into one state object, so each event carries
                // every flag. The undo stack is the source of truth for "unsaved markup":
                // every edit is a command, so undoing back to the start clears the badge,
                // and merely selecting a markup no longer raises it.
                eventBus.on('annotationeditorstateschanged', (e) => {
                    const details = e?.details;
                    if (!details) return;
                    if ('hasSomethingToUndo' in details) {
                        const v = !!details.hasSomethingToUndo;
                        undoStackRef.current.canUndo = v;
                        setCanUndo(v);
                        setDirty(v);
                    }
                    if ('hasSomethingToRedo' in details) {
                        const v = !!details.hasSomethingToRedo;
                        undoStackRef.current.canRedo = v;
                        setCanRedo(v);
                    }
                    if ('hasSelectedEditor' in details) {
                        setHasSelection(!!details.hasSelectedEditor);
                        if (!details.hasSelectedEditor) setSelection(null);
                    }
                });
                // Fires with the selected editor's own properties every time the selection
                // lands on an editor — including a straight hop from one markup to another,
                // which the states event above does not report because "has a selection"
                // did not change. The pill mirrors the selection: its kind picks the size
                // control, and its color/weight/size are what the controls show. Without
                // a selection this is pdf.js broadcasting defaults, which the pill owns —
                // so those are left alone.
                eventBus.on('annotationeditorparamschanged', (e) => {
                    const uiManager = viewerStateRef.current.uiManager || e?.source;
                    const editor = uiManager?.firstSelectedEditor;
                    if (!editor) return;
                    const next = {
                        kind: editor.editorType === 'freetext' ? 'freetext'
                            : editor.editorType === 'ink' ? 'ink' : null,
                    };
                    const params = pdfjsLib.AnnotationEditorParamsType || {};
                    for (const [type, value] of e?.details || []) {
                        if (type === params.INK_COLOR || type === params.FREETEXT_COLOR) {
                            next.color = normalizeHex(value);
                        } else if (type === params.INK_THICKNESS) {
                            const n = Number(value);
                            if (Number.isFinite(n) && n > 0) next.thickness = n;
                        } else if (type === params.FREETEXT_SIZE) {
                            const n = Number(value);
                            if (Number.isFinite(n) && n > 0) next.fontSize = Math.round(n);
                        }
                    }
                    setSelection(next);
                });
                // The UIManager is created during setDocument (NONE mode still
                // creates it); capture it so shape tools can inject Ink editors
                // via uiManager.getLayer(pageIndex).deserialize/add.
                eventBus.on('annotationeditoruimanager', ({ uiManager }) => {
                    viewerStateRef.current.uiManager = uiManager;
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
                            const [x1, y1, , y2] = viewport.convertToViewportRectangle(ann.rect);
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

                eventBus.on('pagesloaded', () => {
                    const p = initialPageRef.current;
                    if (p && pdfViewer.pagesCount) {
                        const clamped = Math.max(1, Math.min(pdfViewer.pagesCount, p));
                        pdfViewer.scrollPageIntoView({ pageNumber: clamped });
                    }
                    refreshTicks();
                });
                // Recompute after a zoom change once the new scale's pages are laid out
                eventBus.on('scalechanging', () => { setTimeout(refreshTicks, 100); });

                // Cheap version-meta lookup BEFORE setDocument so the current
                // version number is set when pagesloaded fires.
                viewerStateRef.current.originByFingerprint = new Map();
                viewerStateRef.current.currentVersionNumber = null;
                let lineageChain = [];
                if (!fileUrl) try {
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
            viewerStateRef.current = { pdfDocument: null, pdfViewer: null, eventBus: null, loadingTask: null, uiManager: null };
        };
    }, [isOpen, releaseId, versionId, fileUrl, inline, hybrid]);

    // Jump-to-page on command: react to initialPage / citeNonce changes when the
    // doc is already loaded (NOT via the init effect's deps — reloading the whole
    // doc would flash). citeNonce forces a re-jump when two findings cite the
    // same page number.
    useEffect(() => {
        if (!isOpen || loading || !initialPage) return;
        const v = viewerStateRef.current.pdfViewer;
        if (!v || !v.pagesCount) return;
        const clamped = Math.max(1, Math.min(v.pagesCount, initialPage));
        v.scrollPageIntoView({ pageNumber: clamped });
    }, [initialPage, citeNonce, isOpen, loading]);

    // The right API in pdf.js 4.x is dispatching 'switchannotationeditorparams' on the
    // EventBus — there is no pdfViewer.annotationEditorParams setter. The UI manager
    // applies the value to every selected editor AND makes it the default for the next
    // one created. Each editor kind ignores the other kind's parameter, so a color goes
    // out as both INK_COLOR and FREETEXT_COLOR: one palette for pen, shapes and text.
    const dispatchParam = (type, value) => {
        const eventBus = viewerStateRef.current.eventBus;
        if (!eventBus || type == null) return;
        try {
            eventBus.dispatch('switchannotationeditorparams', { type, value });
        } catch { /* viewer not ready yet */ }
    };

    // Make the pill's defaults pdf.js's defaults. Only ever called with nothing
    // selected: pdf.js applies a parameter to the selection too, and re-applying a
    // markup's own value to it would push a no-op entry onto the undo stack.
    const pushDefaults = () => {
        const params = pdfjsLib.AnnotationEditorParamsType || {};
        const { color: c, thickness: t, fontSize: f } = paramsRef.current;
        dispatchParam(params.INK_COLOR, c);
        dispatchParam(params.FREETEXT_COLOR, c);
        dispatchParam(params.INK_THICKNESS, t);
        dispatchParam(params.FREETEXT_SIZE, f);
    };

    // Apply tool changes to the viewer
    useEffect(() => {
        const pdfViewer = viewerStateRef.current.pdfViewer;
        if (!pdfViewer || !isEdit) return;
        try {
            // Shape tools ride on the INK editor layer (which provides the page
            // layers we inject into); the shape input overlay handles drawing.
            const mode = isShapeTool(tool) ? TOOL.INK : tool;
            const uiManager = viewerStateRef.current.uiManager;
            // Commit whatever is in flight — an open pen session, a text box mid-edit —
            // and drop the selection BEFORE the mode flips. pdf.js does the same from
            // inside updateMode, but only after the mode has changed, and in 4.10 ending
            // a pen session once the mode is already NONE throws (its editor type lookup
            // is by mode), which left the stroke uncommitted: undo could not reach it and
            // Save silently dropped it. Doing it here also means the defaults pushed
            // below reach the defaults only, never a still-selected markup.
            try { uiManager?.unselectAll(); } catch { /* noop */ }
            pdfViewer.annotationEditorMode = { mode };
            // A selection that survived (pdf.js keeps an editor mid-edit selected) means
            // skip: the control handlers keep the defaults in step on every click anyway,
            // this push only matters for the very first markup.
            if (tool !== TOOL.HAND && uiManager && !uiManager.hasSelection) pushDefaults();
        } catch {
            // pdfViewer not yet ready — ignored, will retry on next state change.
        }
        // pushDefaults reads paramsRef, so it never goes stale.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [tool, isEdit]);

    // Pill controls: each one restyles whatever is selected — in Hand mode too — and
    // sets the default for the next markup (pdf.js does both in one dispatch). A click
    // on the value already shown is skipped so the undo stack only records real changes.
    // pdf.js echoes an editor's properties back only on undo/redo, not on the change
    // itself, so the mirrored selection is moved here too.
    const chooseColor = (c) => {
        if (c === shownColor) return;
        setColor(c);
        setSelection((sel) => (sel?.kind ? { ...sel, color: c } : sel));
        const params = pdfjsLib.AnnotationEditorParamsType || {};
        dispatchParam(params.INK_COLOR, c);
        dispatchParam(params.FREETEXT_COLOR, c);
    };

    const chooseThickness = (value) => {
        if (value === shownThickness) return;
        setThickness(value);
        setSelection((sel) => (sel?.kind === 'ink' ? { ...sel, thickness: value } : sel));
        dispatchParam((pdfjsLib.AnnotationEditorParamsType || {}).INK_THICKNESS, value);
    };

    const chooseFontSize = (value) => {
        const next = Math.min(96, Math.max(8, value));
        if (next === shownFontSize) return;
        setFontSize(next);
        setSelection((sel) => (sel?.kind === 'freetext' ? { ...sel, fontSize: next } : sel));
        dispatchParam((pdfjsLib.AnnotationEditorParamsType || {}).FREETEXT_SIZE, next);
    };

    // Two-finger pinch-to-zoom. pdf.js's own TouchManager only resizes the
    // selected editor, so page zoom is handled here: adjust currentScale by the
    // change in finger distance. Single-finger touches fall through to native
    // pan-scroll (touch-action on the container).
    useEffect(() => {
        if (!isOpen) return;
        const container = containerRef.current;
        if (!container) return;
        let lastDist = null;
        const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
        const onTouchMove = (e) => {
            if (e.touches.length !== 2) return;
            e.preventDefault();
            const d = dist(e.touches);
            if (lastDist != null && d > 0) {
                const pdfViewer = viewerStateRef.current.pdfViewer;
                if (pdfViewer) {
                    const current = pdfViewer.currentScale || 1;
                    pdfViewer.currentScale = Math.min(8, Math.max(0.25, current * (d / lastDist)));
                }
            }
            lastDist = d;
        };
        const onTouchEnd = (e) => {
            if (e.touches.length < 2) lastDist = null;
        };
        container.addEventListener('touchmove', onTouchMove, { passive: false });
        container.addEventListener('touchend', onTouchEnd);
        container.addEventListener('touchcancel', onTouchEnd);
        return () => {
            container.removeEventListener('touchmove', onTouchMove);
            container.removeEventListener('touchend', onTouchEnd);
            container.removeEventListener('touchcancel', onTouchEnd);
        };
    }, [isOpen]);

    // Esc-to-close. Inline, this editor is hosted inside another dialog (the release hub)
    // that also closes on Escape from a window listener — so claim the key in the capture
    // phase and stop it there. Otherwise one Escape exits markup AND closes the host, and
    // the discard confirm becomes pointless: the host closes whichever button is pressed.
    useEffect(() => {
        if (!isOpen) return undefined;
        const onKey = (e) => {
            if (e.key !== 'Escape') return;
            if (inline) e.stopPropagation();
            // Hybrid chrome has no close action — markup is always on — so Escape disarms
            // the current tool back to Hand, per the Option 4c interaction spec.
            if (hybrid) {
                setTool(TOOL.HAND);
                return;
            }
            tryClose();
        };
        window.addEventListener('keydown', onKey, inline);
        return () => window.removeEventListener('keydown', onKey, inline);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, dirty, inline, hybrid]);

    // Undo / redo / delete shortcuts. pdf.js binds these on window itself but only acts
    // while a drawing tool is armed (its handler returns early in NONE mode), so Hand —
    // the mode you select and move markups in — needs the same keys wired here. Runs in
    // capture so it can also keep the keys away from pdf.js while the user is typing in
    // a text field: pdf.js exempts <input> but not <textarea>, so Ctrl+Z in the comment
    // composer would otherwise undo a markup instead of the typing.
    useEffect(() => {
        if (!isOpen || !isEdit) return undefined;
        const onKey = (e) => {
            const mod = e.metaKey || e.ctrlKey;
            const key = (e.key || '').toLowerCase();
            const isUndo = mod && !e.shiftKey && key === 'z';
            const isRedo = mod && (key === 'y' || (e.shiftKey && key === 'z'));
            const isDelete = !mod && !e.altKey && (e.key === 'Delete' || e.key === 'Backspace');
            if (!isUndo && !isRedo && !isDelete) return;
            if (isTypingTarget(e.target)) {
                // Native text editing owns the key; stop pdf.js's window handler seeing it.
                if (isUndo || isRedo) e.stopPropagation();
                return;
            }
            const uiManager = viewerStateRef.current.uiManager;
            if (!uiManager) return;
            // A drawing tool is armed: pdf.js's own keyboard manager handles it.
            if (uiManager.getMode() !== TOOL.HAND) return;
            if (isUndo) {
                if (!undoStackRef.current.canUndo) return;
                e.preventDefault();
                e.stopPropagation();
                uiManager.undo();
            } else if (isRedo) {
                if (!undoStackRef.current.canRedo) return;
                e.preventDefault();
                e.stopPropagation();
                uiManager.redo();
            } else if (uiManager.hasSelection) {
                e.preventDefault();
                e.stopPropagation();
                uiManager.delete();
            }
        };
        window.addEventListener('keydown', onKey, true);
        return () => window.removeEventListener('keydown', onKey, true);
    }, [isOpen, isEdit]);

    // Option 4c keyboard: V hand · P pen · T text · L line · A arrow · R box · O circle.
    // Ignored while typing, so the note field and text annotations keep their letters.
    useEffect(() => {
        if (!isOpen || !hybrid || !isEdit) return undefined;
        const KEYS = {
            v: TOOL.HAND, p: TOOL.INK, t: TOOL.FREETEXT, l: TOOL.LINE,
            a: TOOL.ARROW, r: TOOL.SQUARE, o: TOOL.CIRCLE,
        };
        const onKey = (e) => {
            if (e.metaKey || e.ctrlKey || e.altKey) return;
            if (isTypingTarget(e.target)) return;
            const next = KEYS[e.key?.toLowerCase()];
            if (next !== undefined) setTool(next);
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, hybrid, isEdit]);

    // Hybrid chrome: the host renders the markup list, the unsaved badge and Save.
    useEffect(() => { onMarkupsChange?.(ticks); }, [ticks, onMarkupsChange]);
    useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
    useEffect(() => { onSavingChange?.(saving); }, [saving, onSavingChange]);
    useEffect(() => { onNumPages?.(pagesCount); }, [pagesCount, onNumPages]);

    const goToPage = (n) => {
        const pdfViewer = viewerStateRef.current.pdfViewer;
        if (!pdfViewer || !pdfViewer.pagesCount) return;
        const clamped = Math.max(1, Math.min(pdfViewer.pagesCount, n));
        pdfViewer.scrollPageIntoView({ pageNumber: clamped });
        setPageNumber(clamped);
    };

    const adjustZoom = (delta) => {
        const pdfViewer = viewerStateRef.current.pdfViewer;
        if (!pdfViewer) return;
        setFitMode(null);
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

    // Which rendered page is under a screen point, plus its scaled viewport and
    // on-screen rect (used to map the gesture into PDF page coordinates).
    const getPageAtClientPoint = (clientX, clientY) => {
        const pdfViewer = viewerStateRef.current.pdfViewer;
        const doc = viewerStateRef.current.pdfDocument;
        if (!pdfViewer || !doc) return null;
        for (let i = 0; i < doc.numPages; i++) {
            const pv = pdfViewer.getPageView(i);
            if (!pv || !pv.div || !pv.viewport) continue;
            const r = pv.div.getBoundingClientRect();
            if (clientX >= r.left && clientX <= r.right && clientY >= r.top && clientY <= r.bottom) {
                return { pageIndex: i, viewport: pv.viewport, rect: r };
            }
        }
        return null;
    };

    // Convert a drag (start -> end, client coords) into an Ink annotation on the
    // page under the start point and inject it via the editor layer so it
    // persists through saveDocument() and behaves like any other annotation.
    const commitShape = async (startClient, endClient) => {
        const uiManager = viewerStateRef.current.uiManager;
        if (!uiManager) return;
        const page = getPageAtClientPoint(startClient.x, startClient.y);
        if (!page) return;
        const { pageIndex, viewport, rect } = page;
        const s = { x: startClient.x - rect.left, y: startClient.y - rect.top };
        const e = { x: endClient.x - rect.left, y: endClient.y - rect.top };
        if (Math.hypot(e.x - s.x, e.y - s.y) < 4) return;  // ignore taps/tiny drags

        const cssPaths = buildShapeCssPaths(tool, s, e);
        if (!cssPaths.length) return;

        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        const points = cssPaths.map((path) => {
            const flat = [];
            for (const p of path) {
                const [px, py] = viewport.convertToPdfPoint(p.x, p.y);
                flat.push(px, py);
                if (px < minX) minX = px;
                if (px > maxX) maxX = px;
                if (py < minY) minY = py;
                if (py > maxY) maxY = py;
            }
            return Float32Array.from(flat);
        });

        const pad = thickness / 2 + 1;
        const obj = {
            annotationType: pdfjsLib.AnnotationEditorType.INK,
            color: hexToRgbArray(color),
            opacity: 1,
            thickness,
            paths: { points },
            pageIndex,
            rect: [minX - pad, minY - pad, maxX + pad, maxY + pad],
            // pdf.js initializes every editor's rotation to the page's view
            // rotation (architectural PDFs are often stored rotated). The points
            // are in unrotated PDF space (convertToPdfPoint), so deserialize maps
            // them through the rotation-matched rescale and the selection box
            // lands on the right axes. Hardcoding 0 here put the box on swapped
            // axes for rotated pages.
            rotation: viewport.rotation || 0,
        };

        try {
            const layer = uiManager.getLayer(pageIndex);
            if (!layer) return;
            const editor = await layer.deserialize(obj);
            if (editor) {
                layer.add(editor);
                setDirty(true);
            }
        } catch (err) {
            console.error('Failed to add shape:', err);
        }
    };

    const onShapePointerDown = (e) => {
        if (!isShapeTool(tool)) return;
        e.currentTarget.setPointerCapture?.(e.pointerId);
        const r = overlayRef.current?.getBoundingClientRect();
        if (!r) return;
        shapeStartRef.current = { x: e.clientX, y: e.clientY };
        const ox = e.clientX - r.left;
        const oy = e.clientY - r.top;
        setShapeDraft({ sx: ox, sy: oy, ex: ox, ey: oy });
    };

    const onShapePointerMove = (e) => {
        if (!shapeStartRef.current) return;
        const r = overlayRef.current?.getBoundingClientRect();
        if (!r) return;
        const ex = e.clientX - r.left;
        const ey = e.clientY - r.top;
        setShapeDraft((d) => (d ? { ...d, ex, ey } : d));
    };

    const onShapePointerUp = (e) => {
        const start = shapeStartRef.current;
        shapeStartRef.current = null;
        setShapeDraft(null);
        if (!start) return;
        commitShape(start, { x: e.clientX, y: e.clientY });
    };

    // Delete the currently-selected annotation(s). pdf.js's delete() is
    // undoable and works for both saved and not-yet-saved editors; this is the
    // touch equivalent of pressing Delete/Backspace.
    const deleteSelected = () => {
        const uiManager = viewerStateRef.current.uiManager;
        if (!uiManager || !uiManager.hasSelection) return;
        uiManager.delete();
        setHasSelection(false);
        setDirty(true);
    };

    // Button equivalents of Ctrl+Z / Ctrl+Y. Guarded by the stack flags: pdf.js's
    // undo() on an empty stack still reports "something to redo".
    const undoLast = () => {
        const uiManager = viewerStateRef.current.uiManager;
        if (!uiManager || !undoStackRef.current.canUndo) return;
        uiManager.undo();
    };

    const redoLast = () => {
        const uiManager = viewerStateRef.current.uiManager;
        if (!uiManager || !undoStackRef.current.canRedo) return;
        uiManager.redo();
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
        // `saving` is state and so is a render behind: two fast taps (or the pill's Save
        // and the toolbar's Save) both saw false and each POSTed, landing two versions of
        // the same markup. The ref flips synchronously, so the second call is a no-op.
        if (!pdfDocument || saving || savingRef.current) return;
        savingRef.current = true;
        setSaving(true);
        try {
            const bytes = await pdfDocument.saveDocument();
            const fd = new FormData();
            fd.append('file', new Blob([bytes], { type: 'application/pdf' }), 'markup.pdf');
            if (versionId != null) fd.append('source_version_id', String(versionId));
            if ((noteValue || '').trim()) fd.append('note', noteValue.trim());

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
            savingRef.current = false;
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

    // ── Option 4c chrome: every canvas control in the floating bottom pill ──
    const ToolIcon = ({ name }) => {
        const common = {
            width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none',
            stroke: 'currentColor', strokeWidth: 2,
            strokeLinecap: 'round', strokeLinejoin: 'round',
        };
        switch (name) {
            case 'hand':   // feather "move"
                return <svg {...common}><path d="M5 9l-3 3 3 3M9 5l3-3 3 3M15 19l-3 3-3-3M19 9l3 3-3 3M2 12h20M12 2v20" /></svg>;
            case 'pen':
                return <svg {...common}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>;
            case 'text':
                return <svg {...common}><path d="M4 7V5h16v2M12 5v14M9 19h6" /></svg>;
            case 'line':
                return <svg {...common}><path d="M5 19L19 5" /></svg>;
            case 'arrow':
                return <svg {...common}><path d="M5 19L19 5M19 5h-7M19 5v7" /></svg>;
            case 'box':
                return <svg {...common}><rect x="4" y="6" width="16" height="12" rx="1" /></svg>;
            case 'circle':
                return <svg {...common}><circle cx="12" cy="12" r="8" /></svg>;
            case 'undo':   // feather "corner-up-left"
                return <svg {...common}><polyline points="9 14 4 9 9 4" /><path d="M20 20v-7a4 4 0 0 0-4-4H4" /></svg>;
            case 'redo':   // feather "corner-up-right"
                return <svg {...common}><polyline points="15 14 20 9 15 4" /><path d="M4 20v-7a4 4 0 0 1 4-4h12" /></svg>;
            case 'trash':  // feather "trash-2"
                return <svg {...common}><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" /><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /></svg>;
            default:
                return null;
        }
    };

    const pillToolBtn = (icon, value, label) => {
        const active = tool === value;
        return (
            <button
                key={label}
                type="button"
                onClick={() => setTool(value)}
                aria-label={label}
                title={label}
                className="grid place-items-center border-0 cursor-pointer"
                style={{
                    width: 30, height: 30, borderRadius: 7,
                    background: active ? 'var(--accent-soft)' : 'transparent',
                    color: active ? 'var(--accent)' : 'var(--text-3)',
                }}
            >
                <ToolIcon name={icon} />
            </button>
        );
    };

    // Undo / redo / delete: same footprint as a tool button, greyed out until there is
    // something to act on, never "active".
    const pillActionBtn = (icon, onClick, enabled, label, danger = false) => (
        <button
            key={label}
            type="button"
            onClick={onClick}
            disabled={!enabled}
            aria-label={label}
            title={label}
            className="grid place-items-center border-0 cursor-pointer disabled:cursor-not-allowed"
            style={{
                width: 30, height: 30, borderRadius: 7, background: 'transparent',
                color: !enabled ? 'var(--text-3)' : (danger ? '#dc2626' : 'var(--text-2)'),
                opacity: enabled ? 1 : 0.4,
            }}
        >
            <ToolIcon name={icon} />
        </button>
    );

    const pillDivider = (
        <span style={{ width: 1, height: 20, background: 'var(--border)', flexShrink: 0 }} />
    );

    const pillIconBtn = {
        border: 0, background: 'transparent', cursor: 'pointer',
        color: 'var(--text-2)', fontSize: 14, lineHeight: 1, padding: '2px 4px',
    };

    const pillModeBtn = (active) => ({
        border: 0, cursor: 'pointer', fontSize: 12,
        fontWeight: active ? 700 : 500, borderRadius: 999, padding: '3px 9px',
        background: active ? 'var(--accent-soft)' : 'transparent',
        color: active ? 'var(--accent)' : 'var(--text-2)',
    });

    // Appears above the pill only when there are uncommitted shapes: the note and the
    // commit action for the markup you just drew, next to where you drew it.
    const saveBar = (isEdit && dirty) ? (
        <div
            className="absolute flex items-center bg-surface border border-hairline-strong"
            style={{
                bottom: 62, left: '50%', transform: 'translateX(-50%)',
                gap: 8, padding: '6px 10px 6px 12px', borderRadius: 999,
                boxShadow: '0 8px 24px rgba(15,26,48,.18)', whiteSpace: 'nowrap', zIndex: 21,
            }}
        >
            <span className="font-semibold" style={{ fontSize: 12, color: '#b45309' }}>
                Unsaved markup
            </span>
            <input
                value={noteValue}
                onChange={(e) => setNoteValue(e.target.value)}
                placeholder="Note (optional)"
                className="border border-hairline bg-surface text-ink"
                style={{ width: 200, height: 26, padding: '0 8px', borderRadius: 7, fontSize: 12.5 }}
            />
            <button
                type="button"
                onClick={handleSave}
                disabled={saving || loading}
                className="font-semibold text-white disabled:opacity-60"
                style={{ height: 26, padding: '0 12px', borderRadius: 7, border: 0, fontSize: 12.5, background: '#264093' }}
            >
                {saving ? 'Saving…' : 'Save version'}
            </button>
        </div>
    ) : null;

    const markupPill = (
        <div
            className="absolute flex items-center bg-surface border border-hairline-strong"
            style={{
                bottom: 18, left: '50%', transform: 'translateX(-50%)',
                gap: 10, padding: '6px 14px', borderRadius: 999,
                boxShadow: '0 8px 24px rgba(15,26,48,.18)', whiteSpace: 'nowrap', zIndex: 20,
            }}
        >
            {isEdit && (
                <>
                    <div className="flex items-center" style={{ gap: 2 }}>
                        {pillToolBtn('hand', TOOL.HAND, 'Hand (V)')}
                        {pillToolBtn('pen', TOOL.INK, 'Pen (P)')}
                        {pillToolBtn('text', TOOL.FREETEXT, 'Text (T)')}
                        {pillToolBtn('line', TOOL.LINE, 'Line (L)')}
                        {pillToolBtn('arrow', TOOL.ARROW, 'Arrow (A)')}
                        {pillToolBtn('box', TOOL.SQUARE, 'Box (R)')}
                        {pillToolBtn('circle', TOOL.CIRCLE, 'Circle (O)')}
                    </div>
                    {pillDivider}
                    <div className="flex items-center" style={{ gap: 8, padding: '0 4px' }}>
                        {COLORS.map((c) => (
                            <button
                                key={c}
                                type="button"
                                onClick={() => chooseColor(c)}
                                aria-label={`Color ${c}`}
                                aria-pressed={shownColor === c}
                                className="border-0 cursor-pointer"
                                style={{
                                    width: 16, height: 16, borderRadius: '50%', background: c,
                                    boxShadow: shownColor === c
                                        ? '0 0 0 2px var(--surface), 0 0 0 3.5px var(--accent)'
                                        : 'none',
                                }}
                            />
                        ))}
                    </div>
                    {pillDivider}

                    {/* Size controls follow the armed tool, the way the window toolbar
                        did — text gets point size, pen and shapes get stroke weight. */}
                    {(tool === TOOL.FREETEXT || selectedKind === 'freetext') && (
                        <>
                            <button
                                type="button"
                                style={pillIconBtn}
                                onClick={() => chooseFontSize(shownFontSize - 2)}
                                aria-label="Decrease text size"
                                title="Smaller text"
                            >
                                A−
                            </button>
                            <span className="text-ink-2" style={{ fontSize: 12, minWidth: 22, textAlign: 'center' }}>
                                {shownFontSize}
                            </span>
                            <button
                                type="button"
                                style={{ ...pillIconBtn, fontSize: 16 }}
                                onClick={() => chooseFontSize(shownFontSize + 2)}
                                aria-label="Increase text size"
                                title="Larger text"
                            >
                                A+
                            </button>
                            {pillDivider}
                        </>
                    )}

                    {(tool === TOOL.INK || isShapeTool(tool) || selectedKind === 'ink') && (
                        <>
                            {Object.entries(THICKNESS).map(([label, value]) => (
                                <button
                                    key={label}
                                    type="button"
                                    onClick={() => chooseThickness(value)}
                                    aria-label={`${label} stroke width`}
                                    aria-pressed={shownThickness === value}
                                    title={`${label} stroke`}
                                    className="grid place-items-center border-0 cursor-pointer"
                                    style={{
                                        width: 26, height: 26, borderRadius: 7,
                                        background: shownThickness === value ? 'var(--accent-soft)' : 'transparent',
                                    }}
                                >
                                    <span
                                        style={{
                                            display: 'block',
                                            width: 14,
                                            height: Math.max(1.5, value),
                                            borderRadius: 999,
                                            background: shownThickness === value ? 'var(--accent)' : 'var(--text-3)',
                                        }}
                                    />
                                </button>
                            ))}
                            {pillDivider}
                        </>
                    )}

                    {/* Edit history: the button form of Ctrl+Z / Ctrl+Y / Delete. */}
                    <div className="flex items-center" style={{ gap: 2 }}>
                        {pillActionBtn('undo', undoLast, canUndo, `Undo (${UNDO_KEYS})`)}
                        {pillActionBtn('redo', redoLast, canRedo, `Redo (${REDO_KEYS})`)}
                        {pillActionBtn('trash', deleteSelected, hasSelection, 'Delete selected markup (Delete)', true)}
                    </div>
                    {pillDivider}
                </>
            )}
            <button type="button" style={pillIconBtn} onClick={() => goToPage(pageNumber - 1)}
                    disabled={pageNumber <= 1} aria-label="Previous page">‹</button>
            <span className="text-ink-2" style={{ fontSize: 12 }}>
                Page <strong className="text-ink">{pageNumber}</strong> / {pagesCount || '—'}
            </span>
            <button type="button" style={pillIconBtn} onClick={() => goToPage(pageNumber + 1)}
                    disabled={pagesCount ? pageNumber >= pagesCount : true} aria-label="Next page">›</button>
            {pillDivider}
            <button type="button" style={pillIconBtn} onClick={() => adjustZoom(0.8)} aria-label="Zoom out">−</button>
            <span className="text-ink-2" style={{ fontSize: 12, minWidth: 38, textAlign: 'center' }}>{scalePct}%</span>
            <button type="button" style={pillIconBtn} onClick={() => adjustZoom(1.25)} aria-label="Zoom in">+</button>
            {pillDivider}
            <button
                type="button"
                style={pillModeBtn(fitMode === 'fit')}
                onClick={() => { setFitMode('fit'); fitToPage(); }}
            >
                Fit
            </button>
            <button
                type="button"
                style={pillModeBtn(fitMode === 'width')}
                onClick={() => { setFitMode('width'); fitToWidth(); }}
            >
                Width
            </button>
        </div>
    );

    const rootClass = hybrid
        ? 'relative w-full h-full flex flex-col'
        : (inline
            ? 'relative w-full h-full flex flex-col bg-gray-900'
            : 'fixed inset-0 z-50 flex flex-col bg-gray-900 bg-opacity-95');

    const tree = (
        <div className={rootClass}>
            {/* Hide pdf.js's floating per-editor delete/altText buttons — they
                land in odd spots; the pill's Delete button and the Delete key cover it. */}
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

                /* Hand mode = move/select. pdf.js disables editor-layer pointer
                   events in NONE mode (adds .disabled); we re-enable them so
                   existing annotations — pen strokes, shapes, text — can be
                   selected and dragged. NONE mode binds no create-on-click
                   handler, so empty-space clicks create nothing, and the
                   container's touch-action still allows one-finger pan-scroll. */
                [data-tool="hand"] .annotationEditorLayer,
                [data-tool="hand"] .annotationEditorLayer.disabled {
                    pointer-events: auto !important;
                }

                /* Shape mode: suppress the editor layer so the shape input
                   overlay — not the native ink pen — handles drawing. */
                [data-tool="shape"] .annotationEditorLayer,
                [data-tool="shape"] .annotationEditorLayer * {
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
            {/* Window chrome only. Hybrid puts every control in the pill and the
                host's top strip, so this bar must not render at all — `hidden`
                loses to the element's own `flex` class. */}
            {!hybrid && (
            <div className="flex items-center gap-2 px-3 py-2 bg-white border-b border-gray-200 shadow-sm flex-wrap">
                <span className="font-semibold text-gray-800 mr-2">{title}</span>
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
                        {toolBtn('Line', TOOL.LINE)}
                        {toolBtn('Arrow', TOOL.ARROW)}
                        {toolBtn('Box', TOOL.SQUARE, 'Square')}
                        {toolBtn('Circle', TOOL.CIRCLE)}
                        {(tool === TOOL.INK || isShapeTool(tool) || selectedKind === 'ink') && (
                            <div className="flex items-center gap-1 ml-2">
                                {Object.entries(THICKNESS).map(([label, value]) => (
                                    <button
                                        key={label}
                                        type="button"
                                        onClick={() => chooseThickness(value)}
                                        aria-pressed={shownThickness === value}
                                        className={`px-3 py-3 min-h-[44px] rounded-md text-sm font-semibold border ${
                                            shownThickness === value
                                                ? 'bg-accent-600 text-white border-accent-600'
                                                : 'bg-white text-gray-800 border-gray-300 hover:bg-gray-100'
                                        }`}
                                        title={`${label} stroke`}
                                        aria-label={`${label} stroke width`}
                                    >
                                        {label}
                                    </button>
                                ))}
                            </div>
                        )}
                        {(tool === TOOL.FREETEXT || selectedKind === 'freetext') && (
                            <div className="flex items-center gap-1 ml-2">
                                <button
                                    type="button"
                                    onClick={() => chooseFontSize(shownFontSize - 2)}
                                    className="px-3 py-3 min-w-[44px] min-h-[44px] rounded-md text-sm font-semibold border bg-white text-gray-800 border-gray-300 hover:bg-gray-100"
                                    title="Smaller text"
                                    aria-label="Decrease font size"
                                >A−</button>
                                <span className="px-2 text-sm text-gray-700 select-none min-w-[36px] text-center">{shownFontSize}</span>
                                <button
                                    type="button"
                                    onClick={() => chooseFontSize(shownFontSize + 2)}
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
                                    onClick={() => chooseColor(c)}
                                    aria-label={`Color ${c}`}
                                    aria-pressed={shownColor === c}
                                    className={`w-9 h-9 rounded-full border-2 ${shownColor === c ? 'border-accent-600 ring-2 ring-accent-300' : 'border-gray-300'}`}
                                    style={{ backgroundColor: c }}
                                />
                            ))}
                        </div>
                        <button
                            type="button"
                            onClick={undoLast}
                            disabled={!canUndo}
                            className="ml-2 px-4 py-3 min-h-[44px] rounded-md font-semibold border bg-white text-gray-800 border-gray-300 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
                            title={`Undo (${UNDO_KEYS})`}
                            aria-label={`Undo (${UNDO_KEYS})`}
                        >
                            Undo
                        </button>
                        <button
                            type="button"
                            onClick={redoLast}
                            disabled={!canRedo}
                            className="px-4 py-3 min-h-[44px] rounded-md font-semibold border bg-white text-gray-800 border-gray-300 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
                            title={`Redo (${REDO_KEYS})`}
                            aria-label={`Redo (${REDO_KEYS})`}
                        >
                            Redo
                        </button>
                        <button
                            type="button"
                            onClick={deleteSelected}
                            disabled={!hasSelection}
                            className="ml-2 px-4 py-3 min-h-[44px] rounded-md font-semibold border border-red-300 text-red-700 bg-white hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed"
                            title="Delete selected markup (Delete)"
                            aria-label="Delete selected markup (Delete)"
                        >
                            Delete
                        </button>
                        <input
                            type="text"
                            value={noteValue}
                            onChange={(e) => setNoteValue(e.target.value)}
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
            )}

            {error && (
                <div className="px-4 py-2 bg-red-100 text-red-800 text-sm border-b border-red-200">
                    {error}
                </div>
            )}

            <div
                className="flex-1 relative"
                style={hybrid ? { background: 'var(--bg)' } : undefined}
            >
                {hybrid && saveBar}
                {hybrid && markupPill}
                <div
                    ref={containerRef}
                    className="absolute inset-0 overflow-auto"
                    // pdf.js binds a window-level keyboard handler that maps
                    // Backspace/Delete to "delete selected annotation". Its
                    // checker only exempts <input> elements, not the FreeText
                    // contenteditable box — so while typing in a text annotation,
                    // Backspace bubbles to that handler, gets preventDefault'd,
                    // and removes no text. Stop the event before it reaches
                    // window whenever the target is an editable text box; native
                    // editing then handles it. Annotation-delete via Backspace
                    // still works (that target isn't contenteditable).
                    onKeyDownCapture={(e) => {
                        if ((e.key === 'Backspace' || e.key === 'Delete') && e.target?.isContentEditable) {
                            e.stopPropagation();
                        }
                    }}
                    // Hand mode allows one-finger pan-scroll; drawing tools
                    // suppress it so finger/stylus drags become strokes.
                    style={{ touchAction: tool === TOOL.HAND ? 'pan-x pan-y' : 'none', position: 'absolute' }}
                    data-tool={
                        tool === TOOL.HAND ? 'hand'
                            : tool === TOOL.INK ? 'pen'
                                : tool === TOOL.FREETEXT ? 'text'
                                    : 'shape'
                    }
                >
                    <div className="pdfViewer" />
                </div>

                {/* Shape input overlay: captures the drag for line/arrow/box/circle,
                    shows a live preview, and commits the result as an Ink annotation
                    on pointer-up. Only mounted while a shape tool is active. */}
                {isEdit && isShapeTool(tool) && (
                    <div
                        ref={overlayRef}
                        className="absolute inset-0 z-10"
                        style={{ touchAction: 'none', cursor: 'crosshair' }}
                        onPointerDown={onShapePointerDown}
                        onPointerMove={onShapePointerMove}
                        onPointerUp={onShapePointerUp}
                        onPointerCancel={onShapePointerUp}
                        onWheel={(e) => {
                            const c = containerRef.current;
                            if (c) { c.scrollTop += e.deltaY; c.scrollLeft += e.deltaX; }
                        }}
                    >
                        {shapeDraft && (
                            <svg className="absolute inset-0 w-full h-full pointer-events-none">
                                {buildShapeCssPaths(
                                    tool,
                                    { x: shapeDraft.sx, y: shapeDraft.sy },
                                    { x: shapeDraft.ex, y: shapeDraft.ey },
                                ).map((path, idx) => (
                                    <polyline
                                        key={idx}
                                        points={path.map((p) => `${p.x},${p.y}`).join(' ')}
                                        fill="none"
                                        stroke={color}
                                        strokeWidth={thickness}
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                    />
                                ))}
                            </svg>
                        )}
                    </div>
                )}

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
                            // Fallback tag when there's no version (e.g. Procore-pulled
                            // markups): show a glyph for the markup kind, not a bare dot.
                            const typeGlyph = t.type === 'FreeText' ? 'T' : (t.type === 'Ink' ? '✎' : '▢');
                            const typeLabel = t.type === 'FreeText' ? 'Text note' : (t.type === 'Ink' ? 'Pen markup' : 'Shape markup');
                            const tickLabel = [versionLabel, typeLabel, t.page != null ? `page ${t.page}` : '']
                                .filter(Boolean).join(' · ');
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
                                    title={tickLabel}
                                    aria-label={`Jump to ${tickLabel}`}
                                >
                                    {versionLabel || typeGlyph}
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
        </div>
    );

    return inline ? tree : createPortal(tree, document.body);
}

export default PdfMarkupModal;
