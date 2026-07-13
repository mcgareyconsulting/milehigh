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
    const [tool, setTool] = useState(TOOL.HAND);
    const [color, setColor] = useState(COLORS[0]);
    const [fontSize, setFontSize] = useState(16);
    const [thickness, setThickness] = useState(THICKNESS.Medium);
    const [note, setNote] = useState('');
    const [dirty, setDirty] = useState(false);
    const [ticks, setTicks] = useState([]);  // scrollbar ticks for each annotation
    const [shapeDraft, setShapeDraft] = useState(null);  // { sx, sy, ex, ey } overlay-relative preview
    const [hasSelection, setHasSelection] = useState(false);  // an editor is currently selected

    const isEdit = mode === 'edit';

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

                eventBus.on('pagesinit', () => {
                    // 'page-fit' shows the whole page; 'auto' / 'page-width' often
                    // over-zoom wide FC drawings on big screens.
                    pdfViewer.currentScaleValue = 'page-fit';
                });
                eventBus.on('annotationeditorstateschanged', (e) => {
                    setDirty(true);
                    const details = e?.details;
                    if (details && 'hasSelectedEditor' in details) {
                        setHasSelection(!!details.hasSelectedEditor);
                    }
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
    }, [isOpen, releaseId, versionId, fileUrl]);

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

    // Apply tool changes to the viewer
    useEffect(() => {
        const pdfViewer = viewerStateRef.current.pdfViewer;
        if (!pdfViewer || !isEdit) return;
        try {
            // Shape tools ride on the INK editor layer (which provides the page
            // layers we inject into); the shape input overlay handles drawing.
            const mode = isShapeTool(tool) ? TOOL.INK : tool;
            pdfViewer.annotationEditorMode = { mode };
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

    // Apply stroke-thickness changes to the pen. Shapes read `thickness`
    // directly when committed, so only the live INK editor needs the dispatch.
    useEffect(() => {
        const eventBus = viewerStateRef.current.eventBus;
        if (!eventBus || !isEdit || tool !== TOOL.INK) return;
        const params = pdfjsLib.AnnotationEditorParamsType;
        try {
            if (params?.INK_THICKNESS != null) {
                eventBus.dispatch('switchannotationeditorparams', { type: params.INK_THICKNESS, value: thickness });
            }
        } catch { /* swallow */ }
    }, [thickness, tool, isEdit]);

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
        if (!uiManager) return;
        uiManager.delete();
        setHasSelection(false);
        setDirty(true);
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

    const rootClass = inline
        ? 'relative w-full h-full flex flex-col bg-gray-900'
        : 'fixed inset-0 z-50 flex flex-col bg-gray-900 bg-opacity-95';

    const tree = (
        <div className={rootClass}>
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
                        {(tool === TOOL.INK || isShapeTool(tool)) && (
                            <div className="flex items-center gap-1 ml-2">
                                {Object.entries(THICKNESS).map(([label, value]) => (
                                    <button
                                        key={label}
                                        type="button"
                                        onClick={() => setThickness(value)}
                                        className={`px-3 py-3 min-h-[44px] rounded-md text-sm font-semibold border ${
                                            thickness === value
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
                        <button
                            type="button"
                            onClick={deleteSelected}
                            disabled={!hasSelection}
                            className="ml-2 px-4 py-3 min-h-[44px] rounded-md font-semibold border border-red-300 text-red-700 bg-white hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed"
                            title="Delete selected annotation (or press Delete)"
                            aria-label="Delete selected annotation"
                        >
                            Delete
                        </button>
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
        </div>
    );

    return inline ? tree : createPortal(tree, document.body);
}

export default PdfMarkupModal;
