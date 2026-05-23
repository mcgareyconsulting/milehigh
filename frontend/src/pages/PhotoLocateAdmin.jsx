import { useState, useRef, useEffect } from 'react';
import { checkAuth } from '../utils/auth';
import { API_BASE_URL } from '../utils/api';
import { AlertMessage } from '../components/AlertMessage';

// Per-provider colors for the overlay circles + legend.
const PROVIDER_COLOR = {
    anthropic: '#d97706', // amber-600
    openai: '#2563eb',    // blue-600
};

function formatCost(usd) {
    return usd == null ? '—' : `$${usd.toFixed(6)}`;
}

function formatMs(ms) {
    if (ms == null) return '—';
    return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
}

// SVG ellipse over the located box. Coordinates are normalized [0,1]; the SVG
// uses a 0..100 viewBox stretched to the image, so percentages map directly.
function LocateCircle({ box, color }) {
    const cx = ((box.x_min + box.x_max) / 2) * 100;
    const cy = ((box.y_min + box.y_max) / 2) * 100;
    // Pad the radius ~25% beyond the box so the circle clearly encloses the digits.
    const rx = ((box.x_max - box.x_min) / 2) * 100 * 1.25;
    const ry = ((box.y_max - box.y_min) / 2) * 100 * 1.25;
    return (
        <ellipse
            cx={cx} cy={cy} rx={rx} ry={ry}
            fill="none" stroke={color} strokeWidth="3"
            vectorEffect="non-scaling-stroke"
        />
    );
}

export default function PhotoLocateAdmin() {
    const [isAdmin, setIsAdmin] = useState(null);
    const [file, setFile] = useState(null);
    const [previewUrl, setPreviewUrl] = useState(null);
    const [code, setCode] = useState('');
    const [provider, setProvider] = useState('anthropic');
    const [locating, setLocating] = useState(false);
    const [results, setResults] = useState(null);
    const [error, setError] = useState(null);
    const fileInputRef = useRef(null);

    useEffect(() => {
        (async () => {
            const user = await checkAuth();
            setIsAdmin(!!user?.is_admin);
        })();
    }, []);

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

    const codeValid = /^\d{3}-\d{3}$/.test(code);

    // Accept digits only and auto-insert the hyphen after the 3rd digit (XXX-YYY).
    const handleCodeChange = (e) => {
        const digits = e.target.value.replace(/\D/g, '').slice(0, 6);
        setCode(digits.length > 3 ? `${digits.slice(0, 3)}-${digits.slice(3)}` : digits);
    };

    const handleLocate = async () => {
        if (!file || !codeValid || locating) return;
        setLocating(true);
        setError(null);
        setResults(null);
        try {
            const fd = new FormData();
            fd.append('file', file);
            fd.append('code', code);
            fd.append('provider', provider);
            const resp = await fetch(`${API_BASE_URL}/admin/photo-locate`, {
                method: 'POST',
                body: fd,
                credentials: 'include',
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
            setResults(data.results || []);
        } catch (e) {
            setError(e.message || 'Locate failed.');
        } finally {
            setLocating(false);
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
                <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-2">Photo Locate Code</h1>
                <div className="rounded-lg bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 px-4 py-3">
                    Admin access required.
                </div>
            </div>
        );
    }

    const foundResults = (results || []).filter(r => r.found && r.box);

    return (
        <div className="max-w-4xl mx-auto px-6 py-8">
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Photo Locate Code</h1>
            <p className="text-sm text-slate-600 dark:text-slate-400 mt-1 mb-6">
                Upload a photo and enter the job code (XXX-YYY) you expect in it. The AI
                model finds the code and circles it on the image.
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
                </div>

                <div className="flex flex-wrap items-end gap-3 mt-4">
                    <div>
                        <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Code (XXX-YYY)</label>
                        <input
                            type="text"
                            inputMode="numeric"
                            maxLength={7}
                            value={code}
                            onChange={handleCodeChange}
                            placeholder="482-913"
                            className="w-32 px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-accent-500"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Model</label>
                        <select
                            value={provider}
                            onChange={(e) => setProvider(e.target.value)}
                            className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-500"
                        >
                            <option value="anthropic">Anthropic (Sonnet 4.6)</option>
                            <option value="openai">OpenAI (gpt-4o)</option>
                            <option value="both">Both (compare)</option>
                        </select>
                    </div>
                    <button
                        type="button"
                        onClick={handleLocate}
                        disabled={!file || !codeValid || locating}
                        className="ml-auto px-4 py-2 rounded-lg font-medium bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        {locating ? 'Locating…' : 'Locate'}
                    </button>
                </div>

                {previewUrl && (
                    <div className="relative inline-block mt-4">
                        <img
                            src={previewUrl}
                            alt="Upload preview"
                            className="block max-h-[70vh] rounded-lg border border-slate-200 dark:border-slate-700"
                        />
                        {foundResults.length > 0 && (
                            <svg
                                className="absolute inset-0 w-full h-full pointer-events-none"
                                viewBox="0 0 100 100"
                                preserveAspectRatio="none"
                            >
                                {foundResults.map(r => (
                                    <LocateCircle
                                        key={r.provider}
                                        box={r.box}
                                        color={PROVIDER_COLOR[r.provider] || '#dc2626'}
                                    />
                                ))}
                            </svg>
                        )}
                    </div>
                )}

                {error && <AlertMessage type="error" title="Locate failed" message={error} />}
            </div>

            {results && (
                <div className="mt-6 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 dark:bg-slate-900/40 text-slate-600 dark:text-slate-400 text-xs uppercase tracking-wide">
                            <tr>
                                <th className="text-left px-3 py-2 font-medium">Provider</th>
                                <th className="text-left px-3 py-2 font-medium">Found</th>
                                <th className="text-right px-3 py-2 font-medium">Time</th>
                                <th className="text-right px-3 py-2 font-medium">Cost</th>
                                <th className="text-left px-3 py-2 font-medium">Raw</th>
                            </tr>
                        </thead>
                        <tbody>
                            {results.map(r => (
                                <tr key={r.provider} className="border-t border-slate-200 dark:border-slate-700">
                                    <td className="px-3 py-2 font-medium capitalize text-slate-700 dark:text-slate-200">
                                        <span className="inline-block w-2.5 h-2.5 rounded-full mr-2 align-middle"
                                              style={{ backgroundColor: PROVIDER_COLOR[r.provider] || '#dc2626' }} />
                                        {r.provider}
                                    </td>
                                    <td className="px-3 py-2">
                                        {r.error ? (
                                            <span className="text-red-600 dark:text-red-400 text-sm">⚠️ {r.error}</span>
                                        ) : r.found ? (
                                            <span className="text-emerald-700 dark:text-emerald-400 font-medium">✓ circled</span>
                                        ) : (
                                            <span className="text-slate-400">not found</span>
                                        )}
                                    </td>
                                    <td className="px-3 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">{formatMs(r.elapsed_ms)}</td>
                                    <td className="px-3 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">{formatCost(r.cost_usd)}</td>
                                    <td className="px-3 py-2 text-xs font-mono text-slate-400 dark:text-slate-500 max-w-[16rem] truncate" title={r.raw_response || ''}>
                                        {r.raw_response || '—'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
