/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Read-only pdf.js canvas for the hybrid viewer — every page stacked in one
 *   continuous scroll (the way a drawing set is read), quiet well, floating page/zoom pill.
 *   Markup authoring stays in PdfMarkupModal.
 * exports:
 *   PdfReadViewer: props { fileUrl, citePage, citeRuleId, onClearCite, onNumPages }
 * imports_from: [react, pdfjs-dist]
 * imported_by: [frontend/src/components/pdfViewer/PdfViewerPane.jsx]
 * invariants:
 *   - Continuous scroll is the only mode; the pill's page number reports where you are
 *   - Pages render lazily as they come into view and re-render on zoom; a 40-page set
 *     never rasterises 40 canvases at once
 *   - Nothing rasters until the well has been measured for THIS document, and every raster
 *     is at device resolution — otherwise page 1 draws at a stale scale and CSS stretches it
 *   - citePage (1-based) scrolls that page into view; scrolling on clears the cite
 *   - No URL → empty state, and numPages reports 0 to the host
 * updated_by_agent: 2026-09-07T00:00:00Z
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';

if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
}

const FIT = { width: 'width', fit: 'fit' };
const PAGE_GAP = 14;
//: Render this far outside the viewport so scrolling lands on drawn pages, not blanks.
const PRERENDER_MARGIN = '600px';

export function PdfReadViewer({
    fileUrl = null,
    citePage = null,
    citeRuleId = null,
    onClearCite = null,
    /** (n:number) => void — page count for the top strip's "38 pages · 1.2 MB". */
    onNumPages = null,
}) {
    const wellRef = useRef(null);
    const pdfRef = useRef(null);
    const pageElRef = useRef([]);      // index 0 = page 1
    const canvasElRef = useRef([]);
    const renderedRef = useRef(new Set());
    const renderSeqRef = useRef(0);    // bumped on scale change to void stale renders
    const scrollingToRef = useRef(null);

    const [numPages, setNumPages] = useState(0);
    const [pageSizes, setPageSizes] = useState([]);   // base (scale 1) dimensions
    const [page, setPage] = useState(1);
    const [mode, setMode] = useState(FIT.width);
    const [scaleBoost, setScaleBoost] = useState(1);
    const [scale, setScale] = useState(1);
    // Until the well has been measured for this document, `scale` is last document's (or
    // the default 1). Drawing then means rasterising page 1 at the wrong size and letting
    // CSS stretch it — the blurry, clipped first page you get right after a pull.
    const [scaleReady, setScaleReady] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    // Load the document, then measure every page once so the scroll column has its full
    // height immediately — otherwise the scrollbar grows as pages render and the view jumps.
    useEffect(() => {
        let cancelled = false;
        pdfRef.current = null;
        renderedRef.current = new Set();
        pageElRef.current = [];
        canvasElRef.current = [];
        setNumPages(0);
        setPageSizes([]);
        setPage(1);
        setScaleReady(false);
        setError(null);
        onNumPages?.(0);
        if (!fileUrl) {
            setLoading(false);
            return undefined;
        }
        setLoading(true);
        (async () => {
            try {
                const resp = await fetch(fileUrl, { credentials: 'include' });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.arrayBuffer();
                if (cancelled) return;
                const pdf = await pdfjsLib.getDocument({ data }).promise;
                if (cancelled) return;
                pdfRef.current = pdf;
                const count = pdf.numPages || 0;

                const sizes = [];
                for (let n = 1; n <= count; n += 1) {
                    const pg = await pdf.getPage(n);
                    if (cancelled) return;
                    const vp = pg.getViewport({ scale: 1 });
                    sizes.push({ width: vp.width, height: vp.height });
                }
                if (cancelled) return;
                setNumPages(count);
                setPageSizes(sizes);
                setPage(1);
                onNumPages?.(count);
            } catch (err) {
                if (!cancelled) setError(err?.message || 'Failed to load PDF');
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [fileUrl]);

    // Scale follows the well: Width fills it, Fit shows a whole page. Widest page wins so
    // a landscape sheet mid-set doesn't overflow the column.
    const recomputeScale = useCallback(() => {
        const well = wellRef.current;
        if (!well || !pageSizes.length) return;
        // A hidden pane (the hub keeps tabs mounted) measures 0 — computing from that
        // would raster the whole set at a placeholder size. Wait for the ResizeObserver.
        if (!well.clientWidth) return;
        const widest = Math.max(...pageSizes.map((s) => s.width));
        const tallest = Math.max(...pageSizes.map((s) => s.height));
        const availW = Math.max(200, well.clientWidth - 40);
        const availH = Math.max(200, well.clientHeight - 40);
        const base = mode === FIT.fit
            ? Math.min(availW / widest, availH / tallest)
            : availW / widest;
        setScale(Math.max(0.25, Math.min(4, base * scaleBoost)));
        setScaleReady(true);
    }, [pageSizes, mode, scaleBoost]);

    useEffect(() => { recomputeScale(); }, [recomputeScale]);

    useEffect(() => {
        const el = wellRef.current;
        if (!el || typeof ResizeObserver === 'undefined') return undefined;
        const ro = new ResizeObserver(() => recomputeScale());
        ro.observe(el);
        return () => ro.disconnect();
    }, [recomputeScale]);

    const drawPage = useCallback(async (n) => {
        const pdf = pdfRef.current;
        const canvas = canvasElRef.current[n - 1];
        if (!pdf || !canvas || !scaleReady || renderedRef.current.has(n)) return;
        const seq = renderSeqRef.current;
        renderedRef.current.add(n);
        try {
            const pg = await pdf.getPage(n);
            if (seq !== renderSeqRef.current) return;
            // Raster at device resolution, present at CSS size: a 1x backing store on a
            // retina screen is what makes drawing text look soft. Capped at 2x so a long
            // set does not blow memory.
            const dpr = Math.min(2, (typeof window !== 'undefined' && window.devicePixelRatio) || 1);
            const viewport = pg.getViewport({ scale: scale * dpr });
            const css = pg.getViewport({ scale });
            canvas.width = Math.floor(viewport.width);
            canvas.height = Math.floor(viewport.height);
            canvas.style.width = `${css.width}px`;
            canvas.style.height = `${css.height}px`;
            await pg.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
        } catch {
            // Transient — a re-render at the next scale will pick it up.
            renderedRef.current.delete(n);
        }
    }, [scale, scaleReady]);

    // Any scale change invalidates every raster.
    useEffect(() => {
        renderSeqRef.current += 1;
        renderedRef.current = new Set();
        if (!numPages) return;
        const well = wellRef.current;
        if (!well) return;
        // Redraw what is on screen right now; the observer covers the rest as it scrolls in.
        pageElRef.current.forEach((el, i) => {
            if (!el) return;
            const top = el.offsetTop - well.scrollTop;
            if (top < well.clientHeight + 400 && top + el.offsetHeight > -400) drawPage(i + 1);
        });
    }, [scale, numPages, drawPage]);

    // Lazy render + "which page am I on".
    useEffect(() => {
        if (!numPages || !scaleReady) return undefined;
        const well = wellRef.current;
        if (!well) return undefined;
        if (typeof IntersectionObserver === 'undefined') {
            // jsdom and very old browsers: draw everything rather than nothing.
            for (let n = 1; n <= numPages; n += 1) drawPage(n);
            return undefined;
        }
        const io = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                const n = Number(entry.target.dataset.page);
                if (entry.isIntersecting) drawPage(n);
            });
        }, { root: well, rootMargin: PRERENDER_MARGIN, threshold: 0 });
        pageElRef.current.forEach((el) => el && io.observe(el));
        return () => io.disconnect();
    }, [numPages, scaleReady, drawPage]);

    // The pill's page number: whichever page covers the middle of the well.
    const onScroll = useCallback(() => {
        const well = wellRef.current;
        if (!well) return;
        const middle = well.scrollTop + well.clientHeight / 2;
        let current = 1;
        for (let i = 0; i < pageElRef.current.length; i += 1) {
            const el = pageElRef.current[i];
            if (el && el.offsetTop <= middle) current = i + 1;
            else break;
        }
        setPage(current);
        // Scrolling under your own steam means you have left the cited page.
        if (scrollingToRef.current === null && citePage != null) onClearCite?.();
    }, [citePage, onClearCite]);

    const scrollToPage = useCallback((n) => {
        const well = wellRef.current;
        const el = pageElRef.current[n - 1];
        if (!well || !el) return;
        scrollingToRef.current = n;
        well.scrollTo({ top: Math.max(0, el.offsetTop - 8), behavior: 'smooth' });
        setPage(n);
        window.setTimeout(() => { scrollingToRef.current = null; }, 400);
    }, []);

    // A finding's citation scrolls its page into view.
    useEffect(() => {
        if (citePage == null || !numPages) return;
        scrollToPage(Math.max(1, Math.min(numPages, Number(citePage) || 1)));
    }, [citePage, numPages, scrollToPage]);

    const go = (delta) => {
        const next = Math.max(1, Math.min(numPages, page + delta));
        onClearCite?.();
        scrollToPage(next);
    };

    const zoom = (delta) => {
        setScaleBoost((s) => Math.max(0.5, Math.min(3, +(s + delta).toFixed(2))));
    };

    if (!fileUrl) {
        return (
            <div className="flex-1 min-w-0 grid place-items-center" style={{ background: 'var(--bg)' }}>
                <div className="text-center text-ink-3">
                    <div style={{ fontSize: 28, marginBottom: 8 }}>📄</div>
                    <p style={{ fontSize: 13 }}>No drawing selected</p>
                    <p style={{ fontSize: 12, marginTop: 4, opacity: 0.8 }}>
                        Pick one from the title menu, or upload a PDF.
                    </p>
                </div>
            </div>
        );
    }

    const divider = (
        <span style={{ width: 1, height: 18, background: 'var(--border)', flexShrink: 0 }} />
    );

    const iconBtn = {
        border: 0,
        background: 'transparent',
        cursor: 'pointer',
        color: 'var(--text-2)',
        fontSize: 14,
        lineHeight: 1,
        padding: '2px 4px',
    };

    const modeBtn = (active) => ({
        border: 0,
        cursor: 'pointer',
        fontSize: 12,
        fontWeight: active ? 700 : 500,
        borderRadius: 999,
        padding: '3px 9px',
        background: active ? 'var(--accent-soft)' : 'transparent',
        color: active ? 'var(--accent)' : 'var(--text-2)',
    });

    return (
        <div className="flex-1 min-w-0 relative flex flex-col" style={{ background: 'var(--bg)' }}>
            {citePage != null && (
                <div
                    className="shrink-0 flex items-center"
                    style={{
                        gap: 8,
                        padding: '6px 14px',
                        background: '#fffbeb',
                        color: '#8a5208',
                        fontSize: 12,
                        borderBottom: '1px solid var(--border)',
                    }}
                >
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#b45309', flexShrink: 0 }} />
                    <span className="truncate">
                        Viewing p{citePage}
                        {citeRuleId ? <> — cited by finding <span className="font-mono">{citeRuleId}</span></> : null}
                    </span>
                    {onClearCite && (
                        <button
                            type="button"
                            onClick={onClearCite}
                            className="ml-auto bg-transparent border-0 cursor-pointer"
                            style={{ color: '#8a5208', fontSize: 14 }}
                            aria-label="Clear citation"
                        >
                            ×
                        </button>
                    )}
                </div>
            )}

            {/* One continuous column of pages. */}
            <div
                ref={wellRef}
                onScroll={onScroll}
                className="flex-1 min-h-0 overflow-auto"
                style={{ padding: '20px 20px 76px' }}
            >
                {loading && <p className="text-sm italic text-ink-3 text-center">Loading PDF…</p>}
                {error && <p className="text-sm text-center" style={{ color: 'var(--fl-red-bg)' }}>{error}</p>}

                <div className="flex flex-col items-center" style={{ gap: PAGE_GAP }}>
                    {pageSizes.map((size, i) => (
                        <div
                            key={i}
                            data-page={i + 1}
                            ref={(el) => { pageElRef.current[i] = el; }}
                            style={{
                                width: size.width * scale,
                                height: size.height * scale,
                                background: '#fff',
                                borderRadius: 3,
                                boxShadow: '0 2px 10px rgba(15,26,48,.18)',
                                flexShrink: 0,
                            }}
                        >
                            <canvas
                                ref={(el) => { canvasElRef.current[i] = el; }}
                                style={{ display: 'block' }}
                            />
                        </div>
                    ))}
                </div>
            </div>

            {!error && (
                <div
                    className="absolute flex items-center bg-surface border border-hairline-strong"
                    style={{
                        bottom: 18,
                        left: '50%',
                        transform: 'translateX(-50%)',
                        gap: 10,
                        padding: '6px 14px',
                        borderRadius: 999,
                        boxShadow: '0 8px 24px rgba(15,26,48,.18)',
                        whiteSpace: 'nowrap',
                    }}
                >
                    <button type="button" style={iconBtn} onClick={() => go(-1)} disabled={page <= 1} aria-label="Previous page">‹</button>
                    <span className="text-ink-2" style={{ fontSize: 12 }}>
                        Page <strong className="text-ink">{page}</strong> / {numPages || '—'}
                    </span>
                    <button type="button" style={iconBtn} onClick={() => go(1)} disabled={page >= numPages} aria-label="Next page">›</button>
                    {divider}
                    <button type="button" style={iconBtn} onClick={() => zoom(-0.15)} aria-label="Zoom out">−</button>
                    <span className="text-ink-2" style={{ fontSize: 12, minWidth: 38, textAlign: 'center' }}>
                        {Math.round(scale * 100)}%
                    </span>
                    <button type="button" style={iconBtn} onClick={() => zoom(0.15)} aria-label="Zoom in">+</button>
                    {divider}
                    <button
                        type="button"
                        style={modeBtn(mode === FIT.fit)}
                        onClick={() => { setMode(FIT.fit); setScaleBoost(1); }}
                    >
                        Fit
                    </button>
                    <button
                        type="button"
                        style={modeBtn(mode === FIT.width)}
                        onClick={() => { setMode(FIT.width); setScaleBoost(1); }}
                    >
                        Width
                    </button>
                </div>
            )}
        </div>
    );
}

export default PdfReadViewer;
