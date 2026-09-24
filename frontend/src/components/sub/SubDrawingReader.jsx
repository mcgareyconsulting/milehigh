/**
 * @milehigh-header
 * schema_version: 1
 * purpose: A full-screen, read-only PDF reader for a phone (release-mobile-recommendations.md
 *          §4b): dark ground, every page rendered to a canvas via pdf.js at fit-width × device
 *          pixel ratio, scroll to pan, zoom-to-fit / + / − buttons, a page stepper, and a one-time
 *          hint pill. No markup tools — the reader is the deliberate answer to "the desktop editor
 *          is impossible on a phone". Existing vector markups draw because they are part of the
 *          PDF; pins and authoring are deferred (spec §4b/§7 open question 1).
 * exports:
 *   SubDrawingReader: ({ url, title, meta, onClose })
 * imports_from: [react, pdfjs-dist]
 * imported_by: [./SubReleaseAttachments.jsx]
 * invariants:
 *   - The document is fetched with credentials so the sub session cookie authorizes the stream.
 *   - Rendering is cancelled on unmount / scale change so a slow page never paints over a newer one.
 *   - Native browser pinch-zoom is left enabled on the scroll container (touch-action allows it).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';

if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
}

const ICONS = {
    back: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>,
};
const ZOOMS = [1, 1.5, 2, 3];

function PdfPage({ pdf, pageNumber, scale, fitWidth, onSize }) {
    const canvasRef = useRef(null);
    useEffect(() => {
        let cancelled = false;
        let task = null;
        (async () => {
            const page = await pdf.getPage(pageNumber);
            if (cancelled) return;
            const base = page.getViewport({ scale: 1 });
            const cssScale = (fitWidth / base.width) * scale;
            const dpr = Math.min(window.devicePixelRatio || 1, 3);
            const viewport = page.getViewport({ scale: cssScale * dpr });
            const canvas = canvasRef.current;
            if (!canvas) return;
            canvas.width = Math.floor(viewport.width);
            canvas.height = Math.floor(viewport.height);
            canvas.style.width = `${Math.floor(viewport.width / dpr)}px`;
            canvas.style.height = `${Math.floor(viewport.height / dpr)}px`;
            onSize?.(pageNumber, Math.floor(viewport.height / dpr));
            task = page.render({ canvasContext: canvas.getContext('2d'), viewport });
            try { await task.promise; } catch { /* cancelled */ }
        })();
        return () => { cancelled = true; try { task?.cancel(); } catch { /* ignore */ } };
    }, [pdf, pageNumber, scale, fitWidth, onSize]);
    return <canvas ref={canvasRef} data-page={pageNumber} className="mb-2 bg-white shadow-lg" />;
}

export default function SubDrawingReader({ url, title, meta, onClose }) {
    const [pdf, setPdf] = useState(null);
    const [error, setError] = useState(null);
    const [zoomIdx, setZoomIdx] = useState(0);
    const [page, setPage] = useState(1);
    const [fitWidth, setFitWidth] = useState(() => Math.max(320, window.innerWidth - 16));
    const [hint, setHint] = useState(() => { try { return !sessionStorage.getItem('sub-reader-hint'); } catch { return true; } });
    const bodyRef = useRef(null);

    useEffect(() => {
        let cancelled = false;
        const task = pdfjsLib.getDocument({ url, withCredentials: true });
        task.promise.then((doc) => { if (!cancelled) setPdf(doc); })
            .catch((e) => { if (!cancelled) setError(e?.message || 'Could not open the drawing'); });
        return () => { cancelled = true; task.destroy(); };
    }, [url]);

    useEffect(() => {
        const onResize = () => setFitWidth(Math.max(320, window.innerWidth - 16));
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
    }, []);

    useEffect(() => {
        if (!hint) return undefined;
        const t = setTimeout(() => { setHint(false); try { sessionStorage.setItem('sub-reader-hint', '1'); } catch { /* ignore */ } }, 3500);
        return () => clearTimeout(t);
    }, [hint]);

    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [onClose]);

    // Track the page under the top of the viewport for the stepper label.
    const onScroll = useCallback(() => {
        const body = bodyRef.current;
        if (!body) return;
        const canvases = body.querySelectorAll('canvas[data-page]');
        let current = 1;
        for (const c of canvases) {
            if (c.offsetTop - body.scrollTop <= body.clientHeight / 2) current = Number(c.dataset.page);
        }
        setPage(current);
    }, []);

    const goTo = (n) => {
        const body = bodyRef.current;
        const c = body?.querySelector(`canvas[data-page="${n}"]`);
        if (c) body.scrollTo({ top: c.offsetTop - 8, behavior: 'smooth' });
    };

    const total = pdf?.numPages || 0;
    const scale = ZOOMS[zoomIdx];
    const noop = useCallback(() => {}, []);

    return (
        <div className="sub-reader" role="dialog" aria-modal="true" aria-label={title}>
            <div className="sub-reader-head">
                <button type="button" className="sub-iconbtn" aria-label="Back" onClick={onClose}>{ICONS.back}</button>
                <div className="title">
                    <div className="fname">{title}</div>
                    <div className="fmeta">{[meta, total ? `page ${page} of ${total}` : null].filter(Boolean).join(' · ')}</div>
                </div>
            </div>
            <div ref={bodyRef} className="sub-reader-body p-2" onScroll={onScroll}>
                {error && <p className="p-6 text-center text-sm text-white/80">{error}</p>}
                {!pdf && !error && <p className="p-6 text-center text-sm text-white/80">Opening drawing…</p>}
                {pdf && Array.from({ length: total }, (_, i) => (
                    <PdfPage key={i + 1} pdf={pdf} pageNumber={i + 1} scale={scale} fitWidth={fitWidth} onSize={noop} />
                ))}
            </div>
            {hint && <div className="sub-hint">Pinch to zoom · scroll to pan</div>}
            <div className="sub-reader-foot">
                <button type="button" disabled={page <= 1} onClick={() => goTo(page - 1)} aria-label="Previous page">‹</button>
                <button type="button" disabled={total <= 1} onClick={() => goTo(page >= total ? 1 : page + 1)}>{total ? `${page} / ${total}` : '–'}</button>
                <button type="button" disabled={zoomIdx === 0} onClick={() => setZoomIdx((z) => Math.max(0, z - 1))} aria-label="Zoom out">−</button>
                <button type="button" onClick={() => setZoomIdx(0)} disabled={zoomIdx === 0}>Fit</button>
                <button type="button" disabled={zoomIdx === ZOOMS.length - 1} onClick={() => setZoomIdx((z) => Math.min(ZOOMS.length - 1, z + 1))} aria-label="Zoom in">+</button>
            </div>
        </div>
    );
}
