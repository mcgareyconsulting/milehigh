/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Thin read-only PDF page viewer for the release hub Attachments tab.
 *   Single-page canvas + page nav + Fit/Width zoom. Cite bar when a finding jumps.
 * exports:
 *   PdfReadViewer: props { fileUrl, fileName, citePage, citeRuleId, onClearCite }
 * imports_from: [react, pdfjs-dist]
 * imported_by: [frontend/src/components/PdfVersionHistoryModal.jsx]
 * invariants:
 *   - Read-only — no annotation tools (markup stays in PdfMarkupModal)
 *   - citePage (1-based) scrolls/jumps to that page when set
 *   - No page / missing URL → empty drop state
 * updated_by_agent: 2026-08-08T00:00:00Z
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
    fileName = '',
    citePage = null,
    citeRuleId = null,
    onClearCite = null,
}) {
    const canvasRef = useRef(null);
    const wellRef = useRef(null);
    const pdfRef = useRef(null);
    const [numPages, setNumPages] = useState(0);
    const [page, setPage] = useState(1);
    const [mode, setMode] = useState(FIT.width);
    const [scaleBoost, setScaleBoost] = useState(1);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    // Load document when URL changes.
    useEffect(() => {
        let cancelled = false;
        pdfRef.current = null;
        setNumPages(0);
        setPage(1);
        setError(null);
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
            } catch (err) {
                if (!cancelled) setError(err?.message || 'Failed to load PDF');
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => { cancelled = true; };
    }, [fileUrl]);

    // Jump when a finding cites a page.
    useEffect(() => {
        if (citePage == null || !numPages) return;
        const p = Math.max(1, Math.min(numPages, Number(citePage) || 1));
        setPage(p);
    }, [citePage, numPages]);

    const renderPage = useCallback(async () => {
        const pdf = pdfRef.current;
        const canvas = canvasRef.current;
        const well = wellRef.current;
        if (!pdf || !canvas || !well || page < 1) return;
        try {
            const pg = await pdf.getPage(page);
            const base = pg.getViewport({ scale: 1 });
            const availW = Math.max(200, well.clientWidth - 32);
            const availH = Math.max(200, well.clientHeight - 32);
            let scale = availW / base.width;
            if (mode === FIT.fit) {
                scale = Math.min(availW / base.width, availH / base.height);
            }
            scale = Math.max(0.25, Math.min(4, scale * scaleBoost));
            const viewport = pg.getViewport({ scale });
            const ctx = canvas.getContext('2d');
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            await pg.render({ canvasContext: ctx, viewport }).promise;
        } catch {
            // Transient during rapid page/zoom changes.
        }
    }, [page, mode, scaleBoost]);

    useEffect(() => {
        renderPage();
    }, [renderPage, numPages, fileUrl]);

    // Re-render on container resize.
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

    if (!fileUrl) {
        return (
            <div className="flex-1 min-h-0 flex flex-col" style={{ background: '#232b3e' }}>
                <div className="flex-1 grid place-items-center text-center" style={{ color: '#9aa3b2' }}>
                    <div>
                        <div style={{ fontSize: 28, marginBottom: 8 }}>📄</div>
                        <p style={{ fontSize: 13 }}>Select a drawing to preview</p>
                        <p style={{ fontSize: 12, marginTop: 4, opacity: 0.75 }}>
                            or drop a PDF from the left rail
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="flex-1 min-h-0 flex flex-col" style={{ background: '#232b3e' }}>
            {/* Toolbar */}
            <div
                className="shrink-0 flex items-center border-b border-hairline bg-surface"
                style={{ gap: 10, padding: '8px 12px', minHeight: 40 }}
            >
                <span className="font-mono text-ink truncate" style={{ fontSize: 12.5, maxWidth: 280 }} title={fileName}>
                    {fileName || 'drawing.pdf'}
                </span>
                <span className="font-mono text-ink-3" style={{ fontSize: 11.5 }}>
                    p {page} / {numPages || '—'}
                </span>
                <div className="flex-1" />
                <button
                    type="button"
                    onClick={() => { setScaleBoost((s) => Math.max(0.5, +(s - 0.15).toFixed(2))); onClearCite?.(); }}
                    className="font-semibold border border-hairline-strong bg-surface text-ink-2"
                    style={{ width: 28, height: 26, borderRadius: 6, fontSize: 14 }}
                    aria-label="Zoom out"
                >
                    −
                </button>
                <button
                    type="button"
                    onClick={() => { setScaleBoost((s) => Math.min(3, +(s + 0.15).toFixed(2))); onClearCite?.(); }}
                    className="font-semibold border border-hairline-strong bg-surface text-ink-2"
                    style={{ width: 28, height: 26, borderRadius: 6, fontSize: 14 }}
                    aria-label="Zoom in"
                >
                    +
                </button>
                <button
                    type="button"
                    onClick={() => { setMode(FIT.fit); setScaleBoost(1); }}
                    className="font-semibold border"
                    style={{
                        height: 26, padding: '0 10px', borderRadius: 6, fontSize: 11.5,
                        background: mode === FIT.fit ? 'var(--accent-soft)' : 'var(--surface)',
                        color: mode === FIT.fit ? 'var(--accent)' : 'var(--text-2)',
                        borderColor: mode === FIT.fit ? 'var(--accent)' : 'var(--border-strong)',
                    }}
                >
                    Fit
                </button>
                <button
                    type="button"
                    onClick={() => { setMode(FIT.width); setScaleBoost(1); }}
                    className="font-semibold border"
                    style={{
                        height: 26, padding: '0 10px', borderRadius: 6, fontSize: 11.5,
                        background: mode === FIT.width ? 'var(--accent-soft)' : 'var(--surface)',
                        color: mode === FIT.width ? 'var(--accent)' : 'var(--text-2)',
                        borderColor: mode === FIT.width ? 'var(--accent)' : 'var(--border-strong)',
                    }}
                >
                    Width
                </button>
                <div className="flex items-center" style={{ gap: 4, marginLeft: 4 }}>
                    <button
                        type="button"
                        disabled={page <= 1}
                        onClick={() => go(-1)}
                        className="font-semibold border border-hairline-strong bg-surface text-ink-2 disabled:opacity-40"
                        style={{ height: 26, padding: '0 8px', borderRadius: 6, fontSize: 11.5 }}
                    >
                        Prev
                    </button>
                    <button
                        type="button"
                        disabled={page >= numPages}
                        onClick={() => go(1)}
                        className="font-semibold border border-hairline-strong bg-surface text-ink-2 disabled:opacity-40"
                        style={{ height: 26, padding: '0 8px', borderRadius: 6, fontSize: 11.5 }}
                    >
                        Next
                    </button>
                </div>
            </div>

            {/* Citation bar */}
            {citePage != null && (
                <div
                    className="shrink-0 flex items-center"
                    style={{
                        gap: 8,
                        padding: '7px 12px',
                        background: '#1b2333',
                        color: '#f5d08c',
                        fontSize: 12,
                    }}
                >
                    <span
                        style={{
                            width: 7, height: 7, borderRadius: '50%',
                            background: '#f5d08c', flexShrink: 0,
                        }}
                    />
                    <span className="truncate">
                        Viewing p{citePage}
                        {citeRuleId ? (
                            <> — cited by finding <span className="font-mono">{citeRuleId}</span></>
                        ) : null}
                    </span>
                    {onClearCite && (
                        <button
                            type="button"
                            onClick={onClearCite}
                            className="ml-auto bg-transparent border-0 cursor-pointer"
                            style={{ color: '#f5d08c', fontSize: 14, opacity: 0.8 }}
                            aria-label="Clear citation"
                        >
                            ×
                        </button>
                    )}
                </div>
            )}

            {/* Canvas well */}
            <div
                ref={wellRef}
                className="flex-1 min-h-0 overflow-auto grid place-items-start justify-center"
                style={{ padding: 16 }}
            >
                {loading && (
                    <p className="text-sm italic" style={{ color: '#9aa3b2', marginTop: 40 }}>Loading PDF…</p>
                )}
                {error && (
                    <p className="text-sm" style={{ color: '#f87171', marginTop: 40 }}>{error}</p>
                )}
                {!loading && !error && (
                    <canvas
                        ref={canvasRef}
                        style={{
                            maxWidth: 820,
                            background: '#fff',
                            borderRadius: 4,
                            boxShadow: '0 12px 40px rgba(0,0,0,.45)',
                        }}
                    />
                )}
            </div>
        </div>
    );
}

export default PdfReadViewer;
