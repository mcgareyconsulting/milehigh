/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Chat UI card for a GC look-ahead PDF artifact Carmen produced — open in a new
 *   tab or download via session-authenticated fetch (cookie), not a bare href (would drop auth).
 * exports:
 *   LookaheadPdfCard: default. Props: { artifact }
 *   extractLookaheadArtifacts: recover cards from assistant text when structured artifacts missing
 * imports_from: [react, ../../services/bbChatApi]
 * imported_by: [../BBChatWidget.jsx]
 * invariants:
 *   - Never navigates with <a href> alone for download_path — must include credentials.
 *   - Revokes object URLs after use so blob memory does not leak across many chats.
 */
import { useState } from 'react';
import { fetchLookaheadPdfBlob } from '../../services/bbChatApi';

const PATH_RE = /\/brain\/lookahead\/artifacts\/([A-Za-z0-9_-]+)\.pdf/g;

/**
 * Prefer structured artifacts from the API; otherwise scrape download paths from assistant text.
 * @param {string} content
 * @param {Array|undefined} structured
 */
export function extractLookaheadArtifacts(content, structured) {
    if (Array.isArray(structured) && structured.length > 0) {
        return structured.filter((a) => a && a.download_path);
    }
    const found = [];
    const seen = new Set();
    const text = content || '';
    let m;
    PATH_RE.lastIndex = 0;
    while ((m = PATH_RE.exec(text)) !== null) {
        const path = m[0];
        if (seen.has(path)) continue;
        seen.add(path);
        found.push({
            kind: 'lookahead_pdf',
            artifact_id: m[1],
            download_path: path,
            title: 'Production look-ahead PDF',
        });
    }
    return found;
}

function windowLabel(window) {
    if (!window) return null;
    const start = window.start;
    const end = window.end;
    const weeks = window.weeks;
    if (start && end) return `${start} → ${end}${weeks ? ` (${weeks} wk)` : ''}`;
    return null;
}

function summaryLine(summary) {
    if (!summary || typeof summary !== 'object') return null;
    const parts = [];
    if (summary.release_count != null) parts.push(`${summary.release_count} releases`);
    if (summary.drafting_count != null) parts.push(`${summary.drafting_count} drafting`);
    if (summary.phase_bar_count != null) parts.push(`${summary.phase_bar_count} phase bars`);
    return parts.length ? parts.join(' · ') : null;
}

export default function LookaheadPdfCard({ artifact }) {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    if (!artifact?.download_path) return null;

    const title = artifact.title || 'Production look-ahead PDF';
    const win = windowLabel(artifact.window);
    const sum = summaryLine(artifact.summary);
    const jobBit = artifact.job != null
        ? `Job ${artifact.job}${artifact.project_name ? ` — ${artifact.project_name}` : ''}`
        : artifact.project_name || null;

    const run = async (asDownload) => {
        setBusy(true);
        setError('');
        let objectUrl;
        try {
            const blob = await fetchLookaheadPdfBlob(artifact.download_path);
            objectUrl = URL.createObjectURL(blob);
            if (asDownload) {
                const a = document.createElement('a');
                a.href = objectUrl;
                a.download = `${(title || 'lookahead').replace(/[^\w\- ]+/g, '').trim() || 'lookahead'}.pdf`;
                document.body.appendChild(a);
                a.click();
                a.remove();
            } else {
                window.open(objectUrl, '_blank', 'noopener,noreferrer');
            }
            // Keep the blob alive long enough for the tab / download to attach.
            setTimeout(() => {
                if (objectUrl) URL.revokeObjectURL(objectUrl);
            }, 60_000);
        } catch (err) {
            setError(err?.message || 'Could not open PDF');
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="mt-2 rounded-xl border border-accent-200 dark:border-accent-700/50 bg-white dark:bg-slate-800/80 shadow-sm overflow-hidden">
            <div className="flex items-start gap-2.5 px-3 py-2.5">
                <div
                    className="shrink-0 w-9 h-9 rounded-lg bg-accent-500/15 text-accent-600 dark:text-accent-300 flex items-center justify-center text-lg"
                    aria-hidden
                >
                    📄
                </div>
                <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-gray-900 dark:text-slate-100 truncate">
                        {title}
                    </div>
                    {jobBit && (
                        <div className="text-[11px] text-gray-500 dark:text-slate-400 truncate">{jobBit}</div>
                    )}
                    {win && (
                        <div className="text-[11px] text-gray-500 dark:text-slate-400">{win}</div>
                    )}
                    {sum && (
                        <div className="text-[11px] text-gray-400 dark:text-slate-500">{sum}</div>
                    )}
                    <div className="text-[10px] text-gray-400 dark:text-slate-500 mt-0.5">
                        Print-ready Gantt · session login required
                    </div>
                </div>
            </div>
            <div className="flex items-center gap-2 px-3 pb-2.5">
                <button
                    type="button"
                    disabled={busy}
                    onClick={() => run(false)}
                    className="flex-1 h-8 rounded-lg bg-accent-500 hover:bg-accent-600 disabled:opacity-50 text-white text-xs font-medium"
                >
                    {busy ? 'Opening…' : 'Open PDF'}
                </button>
                <button
                    type="button"
                    disabled={busy}
                    onClick={() => run(true)}
                    className="flex-1 h-8 rounded-lg border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50 text-gray-700 dark:text-slate-200 text-xs font-medium"
                >
                    Download
                </button>
            </div>
            {error && (
                <div className="px-3 pb-2 text-[11px] text-red-500">{error}</div>
            )}
        </div>
    );
}
