/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Generic single-date modal (set / clear / cancel) sharing the DWL modal shell. Used for the
 *   DUE DATE cell so it gets the same modal interaction as Start Install, without any coupled logic.
 *   Optionally renders a second, mutually-exclusive date field (e.g. an anchor date the caller
 *   backdates from) when secondaryLabel is passed.
 * exports:
 *   DateFieldModal: Props — isOpen, onClose, title, jobLabel, label, helpText, currentDate,
 *     onConfirm(date), onClear, secondaryLabel, secondaryHelpText, secondaryFieldKey.
 *     When secondaryLabel is set, onConfirm receives { [primary field]: date, [secondaryFieldKey]: date }
 *     instead of a plain string — exactly one of the two is non-null.
 * imports_from: [react, ../utils/formatters]
 * imported_by: [frontend/src/components/TableRow.jsx]
 * invariants:
 *   - Confirm is enabled only when a date is chosen; Clear (shown only when a date is already set)
 *     removes it. The component is presentational — the caller owns persistence.
 *   - The primary and secondary fields are mutually exclusive: filling one clears the other, but
 *     either can be overwritten again to switch which one is used.
 */
import React, { useState, useEffect } from 'react';
import { toYmd } from '../utils/formatters';

export function DateFieldModal({
    isOpen,
    onClose,
    title = 'Set Date',
    jobLabel,
    label = 'Date',
    helpText,
    currentDate,
    onConfirm,
    onClear,
    secondaryLabel,
    secondaryHelpText,
    secondaryFieldKey = 'secondary_date',
    secondaryCurrentDate,
}) {
    const [dateInput, setDateInput] = useState('');
    const [secondaryInput, setSecondaryInput] = useState('');
    const hasSecondary = !!secondaryLabel;
    const hadDate = !!toYmd(currentDate) || !!toYmd(secondaryCurrentDate);

    useEffect(() => {
        if (isOpen) {
            setDateInput(toYmd(currentDate));
            setSecondaryInput(toYmd(secondaryCurrentDate));
        }
    }, [isOpen, currentDate, secondaryCurrentDate]);

    if (!isOpen) return null;

    // Both fields can show their real stored values at once when the modal opens.
    // Mutual exclusion only kicks in when the user actively edits one — that clears
    // the other, so exactly one is ever submitted (it can be re-overwritten either way).
    const handlePrimaryChange = (value) => {
        setDateInput(value);
        if (hasSecondary) setSecondaryInput('');
    };

    const handleSecondaryChange = (value) => {
        setSecondaryInput(value);
        setDateInput('');
    };

    const canConfirm = !!dateInput || !!secondaryInput;

    const handleConfirm = () => {
        if (hasSecondary) {
            onConfirm({
                due_date: secondaryInput ? null : (dateInput || null),
                [secondaryFieldKey]: secondaryInput || null,
            });
        } else {
            onConfirm(dateInput || null);
        }
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4">
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                    <div className="flex items-center justify-between">
                        <h2 className="text-2xl font-bold text-white">{title}</h2>
                        <button onClick={onClose} className="text-white hover:text-gray-200 text-2xl font-bold">×</button>
                    </div>
                    {jobLabel && <p className="text-accent-100 text-sm mt-1">{jobLabel}</p>}
                </div>

                <div className="p-6">
                    <div className={hasSecondary ? 'mb-4' : 'mb-6'}>
                        <label className="block text-sm font-semibold text-gray-700 mb-2">{label}</label>
                        <input
                            type="date"
                            value={dateInput}
                            onChange={(e) => handlePrimaryChange(e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500"
                        />
                        {helpText && <p className="text-gray-500 text-xs mt-2">{helpText}</p>}
                    </div>

                    {hasSecondary && (
                        <div className="mb-6">
                            <label className="block text-sm font-semibold text-gray-700 mb-2">{secondaryLabel}</label>
                            <input
                                type="date"
                                value={secondaryInput}
                                onChange={(e) => handleSecondaryChange(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500"
                            />
                            {secondaryHelpText && <p className="text-gray-500 text-xs mt-2">{secondaryHelpText}</p>}
                        </div>
                    )}

                    <div className="flex justify-between gap-3">
                        <div>
                            {hadDate && onClear && (
                                <button
                                    onClick={onClear}
                                    className="px-4 py-2 bg-red-100 border border-red-300 text-red-700 rounded-lg font-medium hover:bg-red-200 transition-all"
                                >
                                    Clear
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
                                disabled={!canConfirm}
                                className={`px-4 py-2 rounded-lg font-medium transition-all ${canConfirm ? 'bg-accent-500 text-white hover:bg-accent-600' : 'bg-gray-300 text-gray-500 cursor-not-allowed'}`}
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

export default DateFieldModal;
