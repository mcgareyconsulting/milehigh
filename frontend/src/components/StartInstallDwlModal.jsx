/**
 * @milehigh-header
 * schema_version: 1
 * purpose: DWL Start Install modal. The drafter picks a desired start-install date; the modal proposes
 *   a Design Drawings Due date (LEAD_BUSINESS_DAYS business days before) which the drafter can tweak,
 *   then Confirm sets BOTH on the submittal. Modeled on the Job Log StartInstallDateModal shell but
 *   without the hard-date/ASAP/installer machinery — a DRR has no release yet.
 * exports:
 *   StartInstallDwlModal: Props — isOpen, onClose, currentStartInstall, currentDueDate, jobLabel,
 *     onConfirm(startInstall, dueDate), onClear, leadBusinessDays.
 * imports_from: [react, ../utils/formatters]
 * imported_by: [frontend/src/components/TableRow.jsx]
 * invariants:
 *   - Changing the start-install date re-proposes the due date (LEAD_BUSINESS_DAYS business days before);
 *     the drafter can then override the due date independently before confirming.
 *   - Confirm requires a start-install date; Clear (shown only when one is already set) removes it.
 */
import React, { useState, useEffect } from 'react';
import { subtractBusinessDays, toYmd } from '../utils/formatters';

export function StartInstallDwlModal({
    isOpen,
    onClose,
    currentStartInstall,
    currentDueDate,
    jobLabel,
    onConfirm,
    onClear,
    leadBusinessDays = 15,
}) {
    const [startInstall, setStartInstall] = useState('');
    const [dueDate, setDueDate] = useState('');
    const [error, setError] = useState('');

    const hadStartInstall = !!toYmd(currentStartInstall);

    useEffect(() => {
        if (!isOpen) return;
        setStartInstall(toYmd(currentStartInstall));
        setDueDate(toYmd(currentDueDate));
        setError('');
    }, [isOpen, currentStartInstall, currentDueDate]);

    // Picking/changing the start install re-proposes the due date; the drafter may then edit it.
    const handleStartInstallChange = (e) => {
        const next = e.target.value;
        setStartInstall(next);
        setDueDate(next ? subtractBusinessDays(next, leadBusinessDays) : '');
        setError('');
    };

    const handleConfirm = () => {
        if (!startInstall) {
            setError('Pick a start install date.');
            return;
        }
        onConfirm(startInstall, dueDate || null);
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4">
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                    <div className="flex items-center justify-between">
                        <h2 className="text-2xl font-bold text-white">Set Start Install</h2>
                        <button onClick={onClose} className="text-white hover:text-gray-200 text-2xl font-bold">×</button>
                    </div>
                    {jobLabel && <p className="text-accent-100 text-sm mt-1">{jobLabel}</p>}
                </div>

                <div className="p-6">
                    <div className="mb-5">
                        <label className="block text-sm font-semibold text-gray-700 mb-2">Start install date</label>
                        <input
                            type="date"
                            value={startInstall}
                            onChange={handleStartInstallChange}
                            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500 ${error ? 'border-red-500' : 'border-gray-300'}`}
                        />
                        {error && <p className="text-red-600 text-sm mt-1">{error}</p>}
                    </div>

                    <div className="mb-6">
                        <label className="block text-sm font-semibold text-gray-700 mb-2">Due date (Design Drawings Due)</label>
                        <input
                            type="date"
                            value={dueDate}
                            onChange={(e) => setDueDate(e.target.value)}
                            disabled={!startInstall}
                            className={`w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500 ${!startInstall ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : ''}`}
                        />
                        <p className="text-gray-500 text-xs mt-2">
                            Proposed as {leadBusinessDays} business days before the start install — adjust if needed. Confirming sets both dates.
                        </p>
                    </div>

                    <div className="flex justify-between gap-3">
                        <div>
                            {hadStartInstall && onClear && (
                                <button
                                    onClick={onClear}
                                    className="px-4 py-2 bg-red-100 border border-red-300 text-red-700 rounded-lg font-medium hover:bg-red-200 transition-all"
                                >
                                    Clear Start Install
                                </button>
                            )}
                        </div>
                        <div className="flex gap-3">
                            <button
                                onClick={onClose}
                                className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg font-medium hover:bg-gray-50 transition-all"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleConfirm}
                                disabled={!startInstall}
                                className={`px-4 py-2 rounded-lg font-medium transition-all ${startInstall ? 'bg-accent-500 text-white hover:bg-accent-600' : 'bg-gray-300 text-gray-500 cursor-not-allowed'}`}
                            >
                                Confirm
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default StartInstallDwlModal;
