/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Lets users set or clear the Start Install date on a release, or flag the release ASAP. Any date entered is treated as a hard date; flagging ASAP sets a hard Start Install one week out (and triggers the Paint Complete → Ship Planning auto-advance).
 * exports:
 *   StartInstallDateModal: Date-picker modal with Save, Set ASAP, Clear Hard Date, Clear ASAP actions
 * imports_from: [react]
 * imported_by: [frontend/src/components/JobsTableRow.jsx]
 * invariants:
 *   - Any non-empty date submitted via Save is persisted as a hard date (is_hard_date=true).
 *   - ASAP toggle disables the date input (ASAP owns the date), but the installer select stays
 *     enabled — an ASAP release still needs an installer assigned (that seeds the mirror bar).
 *   - The confirm button reads "Set ASAP" only when turning ASAP on (off->on); otherwise "Save".
 *     Saving an already-ASAP row with an installer change assigns the installer and keeps the date.
 *   - Clear Hard Date button is only shown when the row currently has a hard date (startInstallFormulaTF === false && currentDate && !isAsap).
 *   - Clear ASAP button is only shown when the row currently has ASAP set (isAsap === true).
 * updated_by_agent: 2026-05-12T00:00:00Z
 */
import React, { useState, useEffect } from 'react';
import { jobsApi } from '../services/jobsApi';

export function StartInstallDateModal({ isOpen, onClose, currentDate, currentInstaller, onSave, onClearHardDate, onSetAsap, onClearAsap, jobNumber, releaseNumber, startInstallFormulaTF, isAsap }) {
    const [dateInput, setDateInput] = useState('');
    const [asapToggle, setAsapToggle] = useState(false);
    const [installer, setInstaller] = useState('');
    const [installerOptions, setInstallerOptions] = useState([]);
    const [error, setError] = useState('');

    const initialInstaller = currentInstaller || '';

    useEffect(() => {
        if (isOpen) {
            setAsapToggle(!!isAsap);
            setInstaller(initialInstaller);
            if (currentDate && !isAsap) {
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
                } catch {
                    setDateInput('');
                }
            } else {
                setDateInput('');
            }
            setError('');
        }
    }, [isOpen, currentDate, isAsap, initialInstaller]);

    useEffect(() => {
        if (isOpen && installerOptions.length === 0) {
            jobsApi.getInstallerTeams()
                .then(setInstallerOptions)
                .catch(() => { /* leave options empty; selector still shows current value */ });
        }
    }, [isOpen, installerOptions.length]);

    const handleDateInputChange = (e) => {
        setDateInput(e.target.value);
        setError('');
    };

    const handleAsapToggle = (e) => {
        const next = e.target.checked;
        setAsapToggle(next);
        setError('');
        if (next) setDateInput('');
    };

    const installerChanged = installer !== initialInstaller;
    // Turning ASAP on (off -> on) stamps the hard date via the ASAP path. When ASAP is
    // already set, the toggle stays on but the installer/date controls still work — an
    // ASAP release still needs an installer assigned (that's what seeds the mirror bar).
    const turningAsapOn = asapToggle && !isAsap;

    const handleSave = () => {
        if (turningAsapOn) {
            // Flag ASAP (which stamps the date); also apply an installer if one was picked.
            onSetAsap(installerChanged ? installer : undefined);
            return;
        }
        if (!dateInput && !installerChanged) {
            setError('Please select a date or installer');
            return;
        }
        // An already-ASAP row keeps its ASAP date (pass null -> installer-only); otherwise use
        // the date input. Installer is sent only when it changed, so a date-only save leaves it.
        onSave(asapToggle ? null : (dateInput || null), installerChanged ? installer : undefined);
    };

    const handleCancel = () => {
        setDateInput('');
        setAsapToggle(!!isAsap);
        setInstaller(initialInstaller);
        setError('');
        onClose();
    };

    if (!isOpen) return null;

    const confirmLabel = turningAsapOn ? 'Set ASAP' : 'Save';
    const confirmEnabled = turningAsapOn || !!dateInput || installerChanged;

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
                    <label className="flex items-start gap-2 mb-4 cursor-pointer select-none">
                        <input
                            type="checkbox"
                            checked={asapToggle}
                            onChange={handleAsapToggle}
                            className="mt-1 h-4 w-4 accent-red-600"
                        />
                        <span>
                            <span className="block text-sm font-semibold text-gray-700">ASAP Mode</span>
                            <span className="block text-xs text-gray-500">
                                Sets Start Install one week out and rips to Shipping Planning at Paint Complete.
                            </span>
                        </span>
                    </label>

                    <div className="mb-6">
                        <label className="block text-sm font-semibold text-gray-700 mb-2">
                            Date
                        </label>
                        <input
                            type="date"
                            value={dateInput}
                            onChange={handleDateInputChange}
                            disabled={asapToggle}
                            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500 ${
                                error ? 'border-red-500' : 'border-gray-300'
                            } ${asapToggle ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : ''}`}
                        />
                        {error && (
                            <p className="text-red-600 text-sm mt-1">{error}</p>
                        )}
                        <p className="text-gray-500 text-xs mt-2">
                            {asapToggle
                                ? 'ASAP sets a hard Start Install one week out and displays "ASAP" in red.'
                                : 'Saving a date sets it as a hard date. Start Install dates cascade automatically.'}
                        </p>
                    </div>

                    <div className="mb-6">
                        <label className="block text-sm font-semibold text-gray-700 mb-2">
                            Installer / Team
                        </label>
                        <select
                            value={installer}
                            onChange={(e) => { setInstaller(e.target.value); setError(''); }}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500"
                        >
                            <option value="">— Unassigned —</option>
                            {installerOptions.map((name) => (
                                <option key={name} value={name}>{name}</option>
                            ))}
                            {/* Preserve a current value that is no longer in the configured list. */}
                            {installer && !installerOptions.includes(installer) && (
                                <option value={installer}>{installer}</option>
                            )}
                        </select>
                        <p className="text-gray-500 text-xs mt-2">
                            Assigning an installer moves the mirror card to that team's list and sets its date range on Trello.
                        </p>
                    </div>

                    <div className="flex justify-between gap-3">
                        <div className="flex gap-2">
                            {!isAsap && startInstallFormulaTF === false && currentDate && onClearHardDate && (
                                <button
                                    onClick={onClearHardDate}
                                    className="px-4 py-2 bg-red-100 border border-red-300 text-red-700 rounded-lg font-medium hover:bg-red-200 transition-all"
                                >
                                    Clear Hard Date
                                </button>
                            )}
                            {isAsap && onClearAsap && (
                                <button
                                    onClick={onClearAsap}
                                    className="px-4 py-2 bg-red-100 border border-red-300 text-red-700 rounded-lg font-medium hover:bg-red-200 transition-all"
                                >
                                    Clear ASAP
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
                                disabled={!confirmEnabled}
                                className={`px-4 py-2 rounded-lg font-medium transition-all ${
                                    confirmEnabled
                                        ? (turningAsapOn
                                            ? 'bg-red-600 text-white hover:bg-red-700'
                                            : 'bg-accent-500 text-white hover:bg-accent-600')
                                        : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                }`}
                            >
                                {confirmLabel}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
