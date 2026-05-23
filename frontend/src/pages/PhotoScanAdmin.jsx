import { useState, useRef, useEffect } from 'react';
import { checkAuth } from '../utils/auth';
import { API_BASE_URL } from '../utils/api';
import { AlertMessage } from '../components/AlertMessage';

function formatCost(usd) {
    if (usd == null) return '—';
    return `$${usd.toFixed(6)}`;
}

function formatMs(ms) {
    if (ms == null) return '—';
    if (ms < 1000) return `${Math.round(ms)} ms`;
    return `${(ms / 1000).toFixed(2)} s`;
}

function ResultRow({ r }) {
    return (
        <tr className="border-t border-slate-200 dark:border-slate-700">
            <td className="px-3 py-2 font-medium capitalize text-slate-700 dark:text-slate-200">
                {r.provider}
                {r.fallback && <span className="ml-1 text-xs font-normal text-amber-600 dark:text-amber-400">(LLM fallback)</span>}
            </td>
            <td className="px-3 py-2">
                {r.error ? (
                    <span className="text-red-600 dark:text-red-400 text-sm">⚠️ {r.error}</span>
                ) : (
                    <span className="font-mono text-lg font-bold text-emerald-700 dark:text-emerald-400">
                        {r.code || '—'}
                    </span>
                )}
            </td>
            <td className="px-3 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">{formatMs(r.elapsed_ms)}</td>
            <td className="px-3 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">{formatCost(r.cost_usd)}</td>
            <td className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500 tabular-nums">{r.input_tokens}/{r.output_tokens}</td>
            <td className="px-3 py-2 text-xs font-mono text-slate-400 dark:text-slate-500 max-w-[12rem] truncate" title={r.raw_response || ''}>
                {r.raw_response || '—'}
            </td>
        </tr>
    );
}

export default function PhotoScanAdmin() {
    const [isAdmin, setIsAdmin] = useState(null);
    const [file, setFile] = useState(null);
    const [previewUrl, setPreviewUrl] = useState(null);
    const [scanning, setScanning] = useState(false);
    const [results, setResults] = useState(null);
    const [error, setError] = useState(null);
    const [provider, setProvider] = useState('smart');
    const fileInputRef = useRef(null);

    useEffect(() => {
        (async () => {
            const user = await checkAuth();
            setIsAdmin(!!user?.is_admin);
        })();
    }, []);

    // Revoke the object URL when it changes / unmounts.
    useEffect(() => {
        return () => { if (previewUrl) URL.revokeObjectURL(previewUrl); };
    }, [previewUrl]);

    const handleFileChange = (e) => {
        const f = e.target.files?.[0];
        if (!f) return;
        setFile(f);
        setResults(null);
        setError(null);
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        setPreviewUrl(URL.createObjectURL(f));
    };

    const handleScan = async () => {
        if (!file || scanning) return;
        setScanning(true);
        setError(null);
        setResults(null);
        try {
            const fd = new FormData();
            fd.append('file', file);
            fd.append('provider', provider);
            const resp = await fetch(`${API_BASE_URL}/admin/photo-scan`, {
                method: 'POST',
                body: fd,
                credentials: 'include',
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
            setResults(data.results || []);
        } catch (e) {
            setError(e.message || 'Scan failed.');
        } finally {
            setScanning(false);
        }
    };

    if (isAdmin === null) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[#f8fafc] dark:bg-slate-900">
                <div className="text-gray-600 dark:text-slate-400">Loading...</div>
            </div>
        );
    }

    if (!isAdmin) {
        return (
            <div className="max-w-3xl mx-auto px-6 py-12">
                <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-2">Photo Code Scan</h1>
                <div className="rounded-lg bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 px-4 py-3">
                    Admin access required.
                </div>
            </div>
        );
    }

    const totalCost = results
        ? results.reduce((sum, r) => sum + (r.cost_usd || 0), 0)
        : 0;

    return (
        <div className="max-w-4xl mx-auto px-6 py-8">
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Photo Code Scan</h1>
            <p className="text-sm text-slate-600 dark:text-slate-400 mt-1 mb-6">
                Upload a photo containing a job code (XXX-YYY label or a 3-digit stamp).
                Smart mode reads it with Google OCR first and falls back to Sonnet 4.6 when
                OCR can't (e.g. stamped metal). Other modes report code, latency, and cost.
            </p>

            <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6">
                <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    onChange={handleFileChange}
                    className="hidden"
                />
                <div className="flex flex-wrap items-center gap-3">
                    <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="px-4 py-2 rounded-lg font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
                    >
                        Choose photo
                    </button>
                    <span className="text-sm text-slate-500 dark:text-slate-400">
                        {file ? file.name : 'No file selected'}
                    </span>
                    <select
                        value={provider}
                        onChange={(e) => setProvider(e.target.value)}
                        className="ml-auto px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-500"
                    >
                        <option value="smart">Smart (OCR → Sonnet)</option>
                        <option value="anthropic">Anthropic (Sonnet 4.6)</option>
                        <option value="openai">OpenAI (gpt-4o)</option>
                        <option value="google">Google OCR</option>
                        <option value="both">LLMs (Sonnet + gpt-4o)</option>
                        <option value="all">All three (compare)</option>
                    </select>
                    <button
                        type="button"
                        onClick={handleScan}
                        disabled={!file || scanning}
                        className="px-4 py-2 rounded-lg font-medium bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        {scanning ? 'Scanning…' : 'Scan'}
                    </button>
                </div>

                {previewUrl && (
                    <img
                        src={previewUrl}
                        alt="Upload preview"
                        className="mt-4 max-h-72 rounded-lg border border-slate-200 dark:border-slate-700"
                    />
                )}

                {error && <AlertMessage type="error" title="Scan failed" message={error} />}
            </div>

            {results && (
                <div className="mt-6 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 dark:bg-slate-900/40 text-slate-600 dark:text-slate-400 text-xs uppercase tracking-wide">
                            <tr>
                                <th className="text-left px-3 py-2 font-medium">Provider</th>
                                <th className="text-left px-3 py-2 font-medium">Code</th>
                                <th className="text-right px-3 py-2 font-medium">Time</th>
                                <th className="text-right px-3 py-2 font-medium">Cost</th>
                                <th className="text-left px-3 py-2 font-medium">Tok in/out</th>
                                <th className="text-left px-3 py-2 font-medium">Raw</th>
                            </tr>
                        </thead>
                        <tbody>
                            {results.map(r => <ResultRow key={r.provider} r={r} />)}
                        </tbody>
                    </table>
                    <div className="px-3 py-2 border-t border-slate-200 dark:border-slate-700 text-right text-xs text-slate-500 dark:text-slate-400">
                        Total scan cost: <span className="font-medium tabular-nums">{formatCost(totalCost)}</span>
                    </div>
                </div>
            )}
        </div>
    );
}
