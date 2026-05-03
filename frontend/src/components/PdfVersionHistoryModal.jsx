/**
 * Lists every saved drawing version for a release. Each row offers View
 * (read-only) and Edit (opens the markup modal seeded from that version).
 * The top of the list lets the user upload a fresh PDF as the next version.
 */
import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { API_BASE_URL } from '../utils/api';

export function PdfVersionHistoryModal({
    isOpen,
    releaseId,
    onClose,
    onOpenVersion,
}) {
    const [versions, setVersions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [uploading, setUploading] = useState(false);
    const fileInputRef = useRef(null);

    const load = async () => {
        if (!releaseId) return;
        setLoading(true);
        setError(null);
        try {
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions`, {
                credentials: 'include',
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            setVersions(data?.versions ?? []);
        } catch (err) {
            setError(err?.message || 'Failed to load versions');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (!isOpen) return;
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, releaseId]);

    useEffect(() => {
        if (!isOpen) return;
        const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);

    const handleUpload = async (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        setUploading(true);
        setError(null);
        try {
            const fd = new FormData();
            fd.append('file', file);
            const latest = versions[0];
            if (latest) fd.append('source_version_id', String(latest.id));
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${releaseId}/drawing`, {
                method: 'POST',
                body: fd,
                credentials: 'include',
            });
            if (!resp.ok) {
                const errBody = await resp.text();
                throw new Error(`Upload failed (${resp.status}): ${errBody.slice(0, 200)}`);
            }
            await load();
        } catch (err) {
            setError(err?.message || 'Upload failed');
        } finally {
            setUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    if (!isOpen) return null;

    const fmtDate = (iso) => {
        if (!iso) return '—';
        try {
            return new Date(iso).toLocaleString();
        } catch {
            return iso;
        }
    };

    const fmtSize = (bytes) => {
        if (!bytes) return '';
        const kb = bytes / 1024;
        if (kb < 1024) return `${kb.toFixed(0)} KB`;
        return `${(kb / 1024).toFixed(1)} MB`;
    };

    return createPortal(
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
            onClick={onClose}
        >
            <div
                className="bg-white rounded-xl shadow-2xl w-full max-w-2xl mx-4 max-h-[85vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl flex items-center justify-between">
                    <h2 className="text-xl font-bold text-white">Drawing version history</h2>
                    <button
                        onClick={onClose}
                        className="text-white hover:text-gray-200 text-2xl font-bold leading-none"
                        aria-label="Close"
                    >
                        ×
                    </button>
                </div>

                <div className="px-6 py-4 border-b border-gray-200 flex items-center gap-3">
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept="application/pdf,.pdf"
                        onChange={handleUpload}
                        disabled={uploading}
                        className="text-sm"
                    />
                    {uploading && <span className="text-sm text-gray-500">Uploading…</span>}
                </div>

                <div className="px-6 py-4 overflow-y-auto flex-1">
                    {loading && <p className="text-sm text-gray-500 italic">Loading…</p>}
                    {error && <p className="text-sm text-red-600">{error}</p>}
                    {!loading && !error && versions.length === 0 && (
                        <p className="text-sm text-gray-500 italic">
                            No versions yet — upload a PDF above to create v1.
                        </p>
                    )}
                    {!loading && !error && versions.length > 0 && (
                        <ul className="space-y-3">
                            {versions.map((v) => (
                                <li
                                    key={v.id}
                                    className="border border-gray-200 rounded-lg p-3 flex items-center gap-3"
                                >
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-baseline gap-2">
                                            <span className="font-semibold text-gray-900">v{v.version_number}</span>
                                            <span className="text-xs text-gray-500">{fmtDate(v.uploaded_at)}</span>
                                            <span className="text-xs text-gray-500">
                                                {v.uploaded_by?.name || '—'}
                                            </span>
                                            <span className="text-xs text-gray-400 ml-auto">{fmtSize(v.file_size_bytes)}</span>
                                        </div>
                                        {v.note && (
                                            <p className="text-sm text-gray-700 mt-1 break-words">{v.note}</p>
                                        )}
                                        {v.source_version_id != null && (
                                            <p className="text-xs text-gray-400 mt-1">from v-id {v.source_version_id}</p>
                                        )}
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => onOpenVersion?.(v.id, 'view')}
                                        className="px-3 py-2 text-sm border border-gray-300 rounded-md hover:bg-gray-50"
                                    >
                                        View
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => onOpenVersion?.(v.id, 'edit')}
                                        className="px-3 py-2 text-sm bg-accent-600 text-white rounded-md font-semibold"
                                    >
                                        Edit
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>

                <div className="bg-gray-50 px-6 py-4 rounded-b-xl border-t border-gray-200 flex justify-end">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>,
        document.body,
    );
}

export default PdfVersionHistoryModal;
