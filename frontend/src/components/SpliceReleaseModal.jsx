/**
 * purpose: "+ Splice" dialog — creates a 340.1 / 340.2 child release under the
 *   release the hub modal is showing. The number is derived by the server; the
 *   user supplies install hours (drawn from the parent's pool), can rescope the
 *   description, and picks a released date. No fab hours, no Trello.
 * imports_from: [react, ../services/jobsApi]
 * imported_by: [frontend/src/components/JobDetailsBody.jsx]
 * invariants:
 *   - Install hours are capped at the pool's remaining hours client-side AND server-side
 *     (the server is the authority — a 409 is surfaced verbatim).
 *   - The release number is display-only; it is never sent.
 */
import React, { useEffect, useState } from 'react';
import { jobsApi } from '../services/jobsApi';

const todayYmd = () => {
    const d = new Date();
    const m = `${d.getMonth() + 1}`.padStart(2, '0');
    const day = `${d.getDate()}`.padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day}`;
};

const fmtHrs = (v) => (v == null ? '—' : `${Number(v)}`);

export function SpliceReleaseModal({
    isOpen,
    onClose,
    /** Parent row id (releases.id). */
    parentId,
    jobNumber,
    releaseNumber,
    jobName = '',
    description = '',
    /** Pool snapshot from GET /splices; refreshed on open. */
    pool = null,
    /** Called with the server response after a successful create. */
    onCreated = null,
}) {
    const [livePool, setLivePool] = useState(pool);
    const [installHrs, setInstallHrs] = useState('');
    const [desc, setDesc] = useState(description || '');
    const [released, setReleased] = useState(todayYmd());
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!isOpen) return;
        setInstallHrs('');
        setDesc(description || '');
        setReleased(todayYmd());
        setError(null);
        setLivePool(pool);
        let cancelled = false;
        if (parentId != null) {
            jobsApi.getSplices(parentId)
                .then((data) => { if (!cancelled) setLivePool(data); })
                .catch(() => { /* keep the snapshot we were handed */ });
        }
        return () => { cancelled = true; };
    }, [isOpen, parentId, description, pool]);

    useEffect(() => {
        if (!isOpen) return undefined;
        const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    const remaining = livePool?.remaining_install_hrs;
    const total = livePool?.total_install_hrs;
    const nextNumber = livePool?.next_splice_number || `${releaseNumber}.?`;
    const hrs = parseFloat(installHrs);
    const hrsValid = Number.isFinite(hrs) && hrs > 0;
    const overPool = hrsValid && remaining != null && hrs > remaining + 1e-9;
    const noPool = total == null;
    const canSubmit = hrsValid && !overPool && !noPool && !submitting;

    const submit = async (e) => {
        e?.preventDefault?.();
        if (!canSubmit) return;
        setSubmitting(true);
        setError(null);
        try {
            const result = await jobsApi.createSplice(parentId, {
                install_hrs: hrs,
                description: desc,
                released: released || null,
            });
            onCreated?.(result);
            onClose?.();
        } catch (err) {
            setError(err.message || 'Could not create the splice');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <form onSubmit={submit} className="bg-white rounded-xl shadow-2xl max-w-lg w-full mx-4">
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                    <div className="flex items-center justify-between">
                        <h2 className="text-2xl font-bold text-white">Splice release</h2>
                        <button type="button" onClick={onClose} className="text-white hover:text-gray-200 text-2xl font-bold" aria-label="Close">×</button>
                    </div>
                    <p className="text-accent-100 text-sm mt-1">
                        From {jobNumber}-{releaseNumber}{jobName ? ` · ${jobName}` : ''}
                    </p>
                </div>

                <div className="p-6 space-y-4">
                    <p className="text-sm text-gray-600">
                        A splice carries install hours only. Fabrication stays on {jobNumber}-{releaseNumber};
                        the splice draws from its install-hour pool and gets no Trello card.
                    </p>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs font-semibold uppercase text-gray-500 mb-1">Release #</label>
                            <div className="px-3 py-2 rounded-md border border-gray-200 bg-gray-50 font-mono text-gray-800">
                                {jobNumber}-{nextNumber}
                            </div>
                        </div>
                        <div>
                            <label className="block text-xs font-semibold uppercase text-gray-500 mb-1">Pool</label>
                            <div className="px-3 py-2 rounded-md border border-gray-200 bg-gray-50 text-gray-800">
                                {noPool
                                    ? 'No install hours on the original'
                                    : `${fmtHrs(remaining)} of ${fmtHrs(total)} hrs remaining`}
                            </div>
                        </div>
                    </div>

                    <div>
                        <label htmlFor="splice-install-hrs" className="block text-xs font-semibold uppercase text-gray-500 mb-1">
                            Install hours <span className="text-red-500">*</span>
                        </label>
                        <input
                            id="splice-install-hrs"
                            type="number"
                            inputMode="decimal"
                            min="0"
                            step="0.5"
                            max={remaining ?? undefined}
                            value={installHrs}
                            onChange={(e) => setInstallHrs(e.target.value)}
                            autoFocus
                            className={`w-full px-3 py-2 rounded-md border ${overPool ? 'border-red-400' : 'border-gray-300'} focus:outline-none focus:ring-2 focus:ring-accent-500`}
                            placeholder={remaining != null ? `up to ${fmtHrs(remaining)}` : ''}
                        />
                        {overPool && (
                            <p className="text-xs text-red-600 mt-1">
                                Only {fmtHrs(remaining)} hours remain on {jobNumber}-{releaseNumber}.
                            </p>
                        )}
                    </div>

                    <div>
                        <label htmlFor="splice-description" className="block text-xs font-semibold uppercase text-gray-500 mb-1">Description</label>
                        <input
                            id="splice-description"
                            type="text"
                            maxLength={256}
                            value={desc}
                            onChange={(e) => setDesc(e.target.value)}
                            className="w-full px-3 py-2 rounded-md border border-gray-300 focus:outline-none focus:ring-2 focus:ring-accent-500"
                            placeholder="Scope of this splice (e.g. wall handrails only)"
                        />
                    </div>

                    <div>
                        <label htmlFor="splice-released" className="block text-xs font-semibold uppercase text-gray-500 mb-1">Released</label>
                        <input
                            id="splice-released"
                            type="date"
                            value={released}
                            onChange={(e) => setReleased(e.target.value)}
                            className="px-3 py-2 rounded-md border border-gray-300 focus:outline-none focus:ring-2 focus:ring-accent-500"
                        />
                    </div>

                    {error && (
                        <p className="text-sm text-red-600" role="alert">{error}</p>
                    )}
                </div>

                <div className="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
                    <button type="button" onClick={onClose} className="px-4 py-2 rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50">
                        Cancel
                    </button>
                    <button
                        type="submit"
                        disabled={!canSubmit}
                        className="px-4 py-2 rounded-md bg-accent-600 text-white font-semibold hover:bg-accent-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {submitting ? 'Creating…' : `Create ${jobNumber}-${nextNumber}`}
                    </button>
                </div>
            </form>
        </div>
    );
}

export default SpliceReleaseModal;
