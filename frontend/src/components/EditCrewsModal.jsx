/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin modal for managing installer crews — rename, add, remove, and set each crew's number of installers (crew_size). A crew's size drives the completion ETA of releases assigned to it.
 * exports:
 *   EditCrewsModal: Portal modal with an editable list of crews (name + crew size) plus add/remove
 * imports_from: [react, react-dom, ../services/jobsApi]
 * imported_by: [frontend/src/pages/PMBoard.jsx]
 * invariants:
 *   - Crew name matches its Trello list name; names must be unique.
 *   - Saving diffs against the loaded snapshot: new rows POST, edited rows PATCH, removed rows DELETE.
 *   - crew_size is a positive integer; blank/invalid defaults to 2 server-side.
 */
import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { jobsApi } from '../services/jobsApi';

export function EditCrewsModal({ isOpen, onClose, onSaved }) {
    const [rows, setRows] = useState([]);
    const [original, setOriginal] = useState([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        if (!isOpen) return;
        setError('');
        setLoading(true);
        jobsApi.getCrews()
            .then((crews) => {
                const mapped = crews.map((c) => ({
                    id: c.id,
                    name: c.name,
                    crew_size: c.crew_size,
                }));
                setRows(mapped);
                setOriginal(mapped);
            })
            .catch((e) => setError(e.message || 'Failed to load crews'))
            .finally(() => setLoading(false));
    }, [isOpen]);

    if (!isOpen) return null;

    const updateRow = (idx, patch) => {
        setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
        setError('');
    };

    const addRow = () => {
        setRows((prev) => [...prev, { id: null, name: '', crew_size: 2 }]);
        setError('');
    };

    const removeRow = (idx) => {
        setRows((prev) => prev.filter((_, i) => i !== idx));
        setError('');
    };

    const handleSave = async () => {
        // Validate.
        const cleaned = rows.map((r) => ({ ...r, name: (r.name || '').trim() }));
        if (cleaned.some((r) => !r.name)) {
            setError('Every crew needs a name.');
            return;
        }
        const names = cleaned.map((r) => r.name.toLowerCase());
        if (new Set(names).size !== names.length) {
            setError('Crew names must be unique.');
            return;
        }

        setSaving(true);
        setError('');
        try {
            const originalById = new Map(original.map((r) => [r.id, r]));
            const keptIds = new Set(cleaned.filter((r) => r.id != null).map((r) => r.id));

            // Deletes: rows present originally but no longer kept.
            const deletes = original
                .filter((r) => r.id != null && !keptIds.has(r.id))
                .map((r) => jobsApi.deleteCrew(r.id));

            // Creates and updates.
            const writes = cleaned.map((r) => {
                const size = Number(r.crew_size) || 2;
                if (r.id == null) {
                    return jobsApi.createCrew(r.name, size);
                }
                const before = originalById.get(r.id);
                if (before && (before.name !== r.name || before.crew_size !== size)) {
                    return jobsApi.updateCrew(r.id, { name: r.name, crew_size: size });
                }
                return null;
            }).filter(Boolean);

            await Promise.all([...deletes, ...writes]);
            if (onSaved) onSaved();
            onClose();
        } catch (e) {
            setError(e.message || 'Failed to save crews');
        } finally {
            setSaving(false);
        }
    };

    const modalContent = (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4"
            onClick={onClose}
        >
            <div
                className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-lg w-full max-h-[85vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl flex items-center justify-between">
                    <h2 className="text-xl font-bold text-white">Edit Crews</h2>
                    <button
                        onClick={onClose}
                        className="text-white hover:text-gray-200 text-2xl font-bold leading-none"
                        aria-label="Close"
                    >
                        ×
                    </button>
                </div>

                <div className="p-6 overflow-y-auto">
                    {error && (
                        <div className="bg-red-50 border-l-4 border-red-500 p-3 text-sm text-red-700 mb-4">
                            {error}
                        </div>
                    )}

                    {loading ? (
                        <p className="text-sm text-gray-500 dark:text-slate-400 py-6 text-center">Loading crews…</p>
                    ) : (
                        <>
                            <div className="flex items-center gap-2 px-1 mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500">
                                <span className="flex-1">Crew name</span>
                                <span className="w-24 text-center"># of guys</span>
                                <span className="w-16" />
                            </div>
                            <div className="space-y-2">
                                {rows.map((row, idx) => (
                                    <div key={row.id ?? `new-${idx}`} className="flex items-center gap-2">
                                        <input
                                            type="text"
                                            value={row.name}
                                            placeholder="Crew name"
                                            onChange={(e) => updateRow(idx, { name: e.target.value })}
                                            className="flex-1 px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-700 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-500"
                                        />
                                        <input
                                            type="number"
                                            min="1"
                                            step="1"
                                            value={row.crew_size}
                                            onChange={(e) => updateRow(idx, { crew_size: e.target.value })}
                                            className="w-24 px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-lg text-sm text-center bg-white dark:bg-slate-700 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-500"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => removeRow(idx)}
                                            className="w-16 px-2 py-1.5 bg-red-100 text-red-700 text-xs font-medium rounded hover:bg-red-200"
                                        >
                                            Remove
                                        </button>
                                    </div>
                                ))}
                                {rows.length === 0 && (
                                    <p className="text-sm text-gray-500 dark:text-slate-400 py-2">No crews yet.</p>
                                )}
                            </div>

                            <button
                                type="button"
                                onClick={addRow}
                                className="mt-3 text-sm text-accent-600 hover:underline font-medium"
                            >
                                + Add Crew
                            </button>

                            <p className="text-xs text-gray-500 dark:text-slate-400 mt-4">
                                A crew’s name matches its Trello list. The number of guys drives the
                                completion ETA (install hours ÷ crew × 8h) for every release assigned
                                to that crew.
                            </p>
                        </>
                    )}
                </div>

                <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-slate-600">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm font-medium bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={saving || loading}
                        className={`px-4 py-2 text-sm font-medium text-white rounded-lg ${
                            saving || loading ? 'bg-gray-300 cursor-not-allowed' : 'bg-accent-500 hover:bg-accent-600'
                        }`}
                    >
                        {saving ? 'Saving…' : 'Save'}
                    </button>
                </div>
            </div>
        </div>
    );

    return createPortal(modalContent, document.body);
}

export default EditCrewsModal;
