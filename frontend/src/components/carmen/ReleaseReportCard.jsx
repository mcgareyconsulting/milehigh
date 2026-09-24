/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Chat card for the PDF and CSV Carmen built from a release-report query.
 * exports:
 *   ReleaseReportCard: Props { artifact }
 *   extractReportArtifacts: recover the card from assistant text on reload
 * imports_from: [react, ../../services/bbChatApi]
 * imported_by: [../BBChatWidget.jsx]
 * invariants:
 *   - Downloads go through the session cookie. Paths stay under /brain/reports/artifacts/.
 */
import { useState } from 'react';
import { fetchReportFile } from '../../services/bbChatApi';

const PDF_RE = /\/brain\/reports\/artifacts\/([A-Za-z0-9_-]+)\.pdf/g;
const CSV_RE = /\/brain\/reports\/artifacts\/([A-Za-z0-9_-]+)\.csv/g;

export function extractReportArtifacts(content, structured) {
    if (Array.isArray(structured) && structured.some((item) => item && item.kind === 'release_report')) {
        return structured.filter((item) => item && item.kind === 'release_report' && item.download_path);
    }
    if (Array.isArray(structured) && structured.length > 0) return [];

    const byId = new Map();
    const text = content || '';
    const take = (re, field) => {
        re.lastIndex = 0;
        let match;
        while ((match = re.exec(text)) !== null) {
            const current = byId.get(match[1]) || {
                kind: 'release_report',
                artifact_id: match[1],
                title: 'Release report',
            };
            current[field] = match[0];
            byId.set(match[1], current);
        }
    };
    take(PDF_RE, 'download_path');
    take(CSV_RE, 'download_csv');
    return [...byId.values()].filter((item) => item.download_path || item.download_csv);
}

function countLine(totals) {
    if (!totals || typeof totals !== 'object') return null;
    const parts = [];
    if (totals.releases != null) {
        parts.push(`${totals.releases} release${totals.releases === 1 ? '' : 's'}`);
    }
    if (totals.fab_hrs != null) parts.push(`${totals.fab_hrs} fab hrs`);
    if (totals.install_hrs != null) parts.push(`${totals.install_hrs} install hrs`);
    return parts.length ? parts.join(' · ') : null;
}

async function saveBlob(path, filename) {
    const blob = await fetchReportFile(path);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export default function ReleaseReportCard({ artifact }) {
    const [busy, setBusy] = useState(null);
    const [error, setError] = useState('');

    if (!artifact?.download_path && !artifact?.download_csv) return null;

    const title = artifact.title || 'Release report';
    const summary = typeof artifact.summary === 'string' ? artifact.summary : '';
    const counts = countLine(artifact.totals);

    const run = async (which) => {
        setBusy(which);
        setError('');
        try {
            if (which === 'pdf') {
                await saveBlob(artifact.download_path, 'release-report.pdf');
            } else {
                await saveBlob(artifact.download_csv, 'release-report.csv');
            }
        } catch (err) {
            setError(err?.message || 'Could not download the file');
        } finally {
            setBusy(null);
        }
    };

    return (
        <div className="mt-2 rounded-xl border border-accent-200 dark:border-accent-700/50 bg-white dark:bg-slate-800/80 shadow-sm overflow-hidden">
            <div className="px-3 py-2.5">
                <div className="text-sm font-semibold text-gray-900 dark:text-slate-100">
                    {title}
                </div>
                {summary && (
                    <div className="text-[11px] text-gray-500 dark:text-slate-400 mt-0.5">{summary}</div>
                )}
                {counts && (
                    <div className="text-[11px] text-gray-400 dark:text-slate-500 mt-0.5">{counts}</div>
                )}
            </div>
            <div className="flex items-center gap-2 px-3 pb-2.5">
                {artifact.download_path && (
                    <button
                        type="button"
                        disabled={!!busy}
                        onClick={() => run('pdf')}
                        className="flex-1 h-8 rounded-lg bg-accent-500 hover:bg-accent-600 disabled:opacity-50 text-white text-xs font-medium"
                    >
                        {busy === 'pdf' ? 'Preparing…' : 'Download PDF'}
                    </button>
                )}
                {artifact.download_csv && (
                    <button
                        type="button"
                        disabled={!!busy}
                        onClick={() => run('csv')}
                        className="flex-1 h-8 rounded-lg border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50 text-gray-700 dark:text-slate-200 text-xs font-medium"
                    >
                        {busy === 'csv' ? 'Preparing…' : 'Download CSV'}
                    </button>
                )}
            </div>
            {error && <div className="px-3 pb-2 text-[11px] text-red-500">{error}</div>}
        </div>
    );
}
