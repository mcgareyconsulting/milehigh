/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Lets users set or clear the Start Install date on a release. Any date entered is treated as a hard date; a separate Clear button reverts to formula-driven scheduling.
 * exports:
 *   StartInstallDateModal: Date-picker modal with Save and Clear actions
 * imports_from: [react]
 * imported_by: [frontend/src/components/JobsTableRow.jsx]
 * invariants:
 *   - Any non-empty date submitted via Save is persisted as a hard date (is_hard_date=true).
 *   - Clear button is only shown when the row currently has a hard date (startInstallFormulaTF === false && currentDate).
 * updated_by_agent: 2026-04-21T00:00:00Z
 */
import React, { useState, useEffect } from 'react';

export function StartInstallDateModal({ isOpen, onClose, currentDate, onSave, onClearHardDate, jobNumber, releaseNumber, startInstallFormulaTF }) {
    const [dateInput, setDateInput] = useState('');
    const [error, setError] = useState('');

    useEffect(() => {
        if (isOpen) {
            if (currentDate) {
                try {
                    const isoDate = typeof currentDate === 'string'
                        ? currentDate.split('T')[0]
                        : (() => {
                            const d = new Date(currentDate);
                            if (isNaN(d.getTime())) return '';
                            const y = d.getFullYear();
                            const m = String(d.getMonth() + 1).padStart(2, '0');
                            const day = String(d.getDate()).padStart(2, '0');
                            return `${y}-${m}-${day}`;
                        })();
                    setDateInput(isoDate || '');
                } catch (e) {
                    setDateInput('');
                }
            } else {
                setDateInput('');
            }
            setError('');
        }
    }, [isOpen, currentDate]);

    const handleDateInputChange = (e) => {
        setDateInput(e.target.value);
        setError('');
    };

    const handleSave = () => {
        if (!dateInput) {
            setError('Please select a date');
            return;
        }
        onSave(dateInput);
    };

    const handleCancel = () => {
        setDateInput('');
        setError('');
        onClose();
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4">
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                    <div className="flex items-center justify-between">
                        <h2 className="text-2xl font-bold text-white">
                            Set Start Install Date
                        </h2>
                        <button
                            onClick={handleCancel}
                            className="text-white hover:text-gray-200 text-2xl font-bold"
                        >
                            ×
                        </button>
                    </div>
                    {jobNumber && releaseNumber && (
                        <p className="text-accent-100 text-sm mt-1">
                            Job {jobNumber}-{releaseNumber}
                        </p>
                    )}
                </div>

                <div className="p-6">
                    <div className="mb-6">
                        <label className="block text-sm font-semibold text-gray-700 mb-2">
                            Date
                        </label>
                        <input
                            type="date"
                            value={dateInput}
                            onChange={handleDateInputChange}
                            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500 ${
                                error ? 'border-red-500' : 'border-gray-300'
                            }`}
                        />
                        {error && (
                            <p className="text-red-600 text-sm mt-1">{error}</p>
                        )}
                        <p className="text-gray-500 text-xs mt-2">
                            Saving a date sets it as a hard date. Start Install dates cascade automatically.
                        </p>
                    </div>

                    <div className="flex justify-between gap-3">
                        <div>
                            {startInstallFormulaTF === false && currentDate && onClearHardDate && (
                                <button
                                    onClick={onClearHardDate}
                                    className="px-4 py-2 bg-red-100 border border-red-300 text-red-700 rounded-lg font-medium hover:bg-red-200 transition-all"
                                >
                                    Clear Hard Date
                                </button>
                            )}
                        </div>
                        <div className="flex gap-3">
                            <button
                                onClick={handleCancel}
                                className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg font-medium hover:bg-gray-50 transition-all"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleSave}
                                disabled={!dateInput}
                                className={`px-4 py-2 rounded-lg font-medium transition-all ${
                                    dateInput
                                        ? 'bg-accent-500 text-white hover:bg-accent-600'
                                        : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                }`}
                            >
                                Save
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
