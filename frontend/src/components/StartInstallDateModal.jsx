/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Lets users set or clear the Start Install date on a release, choosing between a hard date and a formula-driven date.
 * exports:
 *   StartInstallDateModal: Date-picker modal with hard-date vs formula toggle and clear action
 * imports_from: [react]
 * imported_by: [frontend/src/components/JobsTableRow.jsx]
 * invariants:
 *   - Hard-date checkbox is initialized from startInstallFormulaTF prop to reflect current backend state
 *   - Clearing a hard date requires a separate onClearHardDate callback distinct from onSave
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import React, { useState, useEffect } from 'react';

export function StartInstallDateModal({ isOpen, onClose, currentDate, onSave, onClearHardDate, jobNumber, releaseNumber, startInstallFormulaTF }) {
    const [dateInput, setDateInput] = useState('');
    const [isHardDate, setIsHardDate] = useState(false);
    const [error, setError] = useState('');

    // Initialize form when modal opens or currentDate changes
    useEffect(() => {
        if (isOpen) {
            if (currentDate) {
                try {
                    // Native date input requires YYYY-MM-DD
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
            // Initialize hard date checkbox based on start_install_formulaTF field
            // If start_install_formulaTF is explicitly false and there's a date, it's a hard date
            // Otherwise, default to false (formula-driven or no date)
            const isCurrentlyHardDate = startInstallFormulaTF === false && currentDate;
            setIsHardDate(isCurrentlyHardDate);
            setError('');
        }
    }, [isOpen, currentDate, startInstallFormulaTF]);

    const handleDateInputChange = (e) => {
        setDateInput(e.target.value);
        setError('');
    };

    const handleSave = () => {
        if (!dateInput && isHardDate) {
            setError('Please select a date or uncheck "Hard Date"');
            return;
        }

        // Only save if it's a hard date, otherwise just close
        if (isHardDate) {
            onSave(dateInput || null, true);
        } else {
            onClose();
        }
    };

    const handleCancel = () => {
        setDateInput('');
        setIsHardDate(false);
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
                    <div className="mb-4">
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
                    </div>

                    <div className="mb-6">
                        <label className="flex items-center cursor-pointer">
                            <input
                                type="checkbox"
                                checked={isHardDate}
                                onChange={(e) => setIsHardDate(e.target.checked)}
                                className="w-5 h-5 text-accent-600 border-gray-300 rounded focus:ring-accent-500 focus:ring-2"
                            />
                            <span className="ml-3 text-sm font-medium text-gray-700">
                                Hard Date
                            </span>
                        </label>
                        <p className="text-gray-500 text-xs mt-1 ml-8">
                            {isHardDate
                                ? 'This date will be saved and synced to Trello. Formula calculations will not override it.'
                                : 'Leave unchecked to keep formula-driven dates. Changes will not be saved.'}
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
                                className={`px-4 py-2 rounded-lg font-medium transition-all ${
                                    isHardDate
                                        ? 'bg-accent-500 text-white hover:bg-accent-600'
                                        : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                }`}
                                disabled={!isHardDate}
                            >
                                {isHardDate ? 'Save Hard Date' : 'Save (Hard Date Required)'}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
