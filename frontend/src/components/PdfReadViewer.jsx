/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Read-only pdf.js canvas for the hybrid viewer — quiet well, white page,
 *   floating page/zoom pill bar bottom-center. Markup authoring stays in PdfMarkupModal.
 * exports:
 *   PdfReadViewer: props { fileUrl, citePage, citeRuleId, onClearCite, onNumPages }
 * imports_from: [react, pdfjs-dist]
 * imported_by: [frontend/src/components/pdfViewer/PdfViewerPane.jsx]
 * invariants:
 *   - Read-only — no annotation tools
 *   - citePage (1-based) jumps to that page; any manual page move clears the cite
 *   - No URL → empty state, and numPages reports 0 to the host
 * updated_by_agent: 2026-09-05T00:00:00Z
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';

if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
}

const FIT = { width: 'width', fit: 'fit' };

export function PdfReadViewer({
    fileUrl = null,
    citePage = null,
    citeRuleId = null,
    onClearCite = null,
    /** (n:number) => void — page count for the top strip's "38 pages · 1.2 MB". */
    onNumPages = null,
}) {
    const canvasRef = useRef(null);
    const wellRef = useRef(null);
    const pdfRef = useRef(null);
    const [numPages, setNumPages] = useState(0);
    const [page, setPage] = useState(1);
    const [mode, setMode] = useState(FIT.width);
    const [scaleBoost, setScaleBoost] = useState(1);
    const [zoomPct, setZoomPct] = useState(100);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    // Load document when URL changes.
    useEffect(() => {
        let cancelled = false;
        pdfRef.current = null;
        setNumPages(0);
        setPage(1);
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
                const task = pdfjsLib.getDocument({ data });
                const pdf = await task.promise;
                if (cancelled) return;
                pdfRef.current = pdf;
                setNumPages(pdf.numPages || 0);
                setPage(1);
                onNumPages?.(pdf.numPages || 0);
            } catch (err) {
                if (!cancelled) setError(err?.message || 'Failed to load PDF');
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [fileUrl]);

    // Jump when a finding cites a page.
    useEffect(() => {
        if (citePage == null || !numPages) return;
        setPage(Math.max(1, Math.min(numPages, Number(citePage) || 1)));
    }, [citePage, numPages]);

    const renderPage = useCallback(async () => {
        const pdf = pdfRef.current;
        const canvas = canvasRef.current;
        const well = wellRef.current;
        if (!pdf || !canvas || !well || page < 1) return;
        try {
            const pg = await pdf.getPage(page);
            const base = pg.getViewport({ scale: 1 });
            const availW = Math.max(200, well.clientWidth - 40);
            const availH = Math.max(200, well.clientHeight - 96);
            let scale = availW / base.width;
            if (mode === FIT.fit) {
                scale = Math.min(availW / base.width, availH / base.height);
            }
            scale = Math.max(0.25, Math.min(4, scale * scaleBoost));
            const viewport = pg.getViewport({ scale });
            const ctx = canvas.getContext('2d');
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            canvas.style.width = `${viewport.width}px`;
            canvas.style.height = `${viewport.height}px`;
            await pg.render({ canvasContext: ctx, viewport }).promise;
            setZoomPct(Math.round(scale * 100));
        } catch {
            // Transient during rapid page/zoom changes.
        }
    }, [page, mode, scaleBoost]);

    useEffect(() => { renderPage(); }, [renderPage, numPages, fileUrl]);

    // Re-render on container resize (dock collapse, window resize).
    useEffect(() => {
        const el = wellRef.current;
        if (!el || typeof ResizeObserver === 'undefined') return undefined;
        const ro = new ResizeObserver(() => { renderPage(); });
        ro.observe(el);
        return () => ro.disconnect();
    }, [renderPage]);

    const go = (delta) => {
        setPage((p) => Math.max(1, Math.min(numPages, p + delta)));
        onClearCite?.();
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
            {/* Citation bar — only while a finding is driving the page. */}
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

            {/* Page well */}
            <div
                ref={wellRef}
                className="flex-1 min-h-0 overflow-auto grid place-items-start justify-center"
                style={{ padding: '20px 20px 76px' }}
            >
                {loading && <p className="text-sm italic text-ink-3" style={{ marginTop: 40 }}>Loading PDF…</p>}
                {error && <p className="text-sm" style={{ color: 'var(--fl-red-bg)', marginTop: 40 }}>{error}</p>}
                <canvas
                    ref={canvasRef}
                    className={loading || error ? 'hidden' : ''}
                    style={{
                        background: '#fff',
                        borderRadius: 3,
                        boxShadow: '0 2px 10px rgba(15,26,48,.18)',
                    }}
                />
            </div>

            {/* Floating pill bar */}
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
                    <span className="text-ink-2" style={{ fontSize: 12, minWidth: 38, textAlign: 'center' }}>{zoomPct}%</span>
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
