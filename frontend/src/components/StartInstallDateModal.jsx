/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Lets users set or clear the Start Install date on a release, or flag the release ASAP. Any date entered is treated as a hard date. ASAP is a rush FLAG only — it paints the row red and triggers the Paint Complete → Ship Planning auto-advance, but the user must enter the Start Install date themselves. Ship and Install stay linked (ship = install − 1 biz day) until the user hits Break (N6).
 * exports:
 *   StartInstallDateModal: Date-picker modal with Save, Set ASAP, Clear Hard Date, Clear ASAP, Break/Link actions
 * imports_from: [react]
 * imported_by: [frontend/src/components/JobsTableRow.jsx]
 * invariants:
 *   - Any non-empty date submitted via Save is persisted as a hard date (is_hard_date=true).
 *   - ASAP REQUIRES a Start Install date: the toggle leaves the date fields enabled and Save is
 *     refused until a date is entered. ASAP sets no date of its own.
 *   - The toggle only ever turns ASAP ON — it is disabled once the flag is set, because Save
 *     has no clear path; Clear ASAP owns that.
 *   - The confirm button reads "Set ASAP" only when turning ASAP on (off->on); otherwise "Save".
 *     Saving an already-ASAP row edits its date/installer exactly like any other row.
 *   - Clear Hard Date button is shown whenever the row has a hard date (startInstallFormulaTF === false && currentDate), ASAP rows included — an ASAP row's date is hand-set like any other and must be clearable without losing the flag.
 *   - Clear ASAP button is only shown when the row currently has ASAP set (isAsap === true).
 *   - Ship ↔ Install auto-estimate only runs while `linked` is true (default when gap is empty or 1 biz day). Break (N6) sets linked false; Link re-enables and re-applies ship = install − 1.
 *   - N5: at Ship Planning / Ship Complete, open unlinked (Break / manual mode by default).
 *     Auto ship↔install estimate is off until the user hits Link — covers formula blanking and
 *     Store→Ship Planning before the parent row has refetched stage.
 * updated_by_agent: 2026-08-08T00:00:00Z
 */
import React, { useState, useEffect } from 'react';
import { jobsApi } from '../services/jobsApi';
import { toYmd, subtractBusinessDays, addBusinessDays } from '../utils/formatters';
import { isInstallStartOrLater } from '../utils/installDateColor';

const SHIPPING_STAGES = new Set(['Ship Planning', 'Ship Complete']);

/** True when ship is empty or exactly one business day before install. */
function areDatesLinked(installYmd, shipYmd) {
    if (!installYmd && !shipYmd) return true;
    if (!installYmd || !shipYmd) return true; // empty other side still "linkable"
    return shipYmd === subtractBusinessDays(installYmd, 1);
}

export function StartInstallDateModal({ isOpen, onClose, currentDate, currentShipDate, currentInstaller, onSave, onSaveShipDate, onClearHardDate, onSetAsap, onClearAsap, jobNumber, releaseNumber, startInstallFormulaTF, isAsap, stage }) {
    const [dateInput, setDateInput] = useState('');
    const [shipDateInput, setShipDateInput] = useState('');
    const [linked, setLinked] = useState(true);
    const [asapToggle, setAsapToggle] = useState(false);
    // Past `Install Start` the color is already dumped and the server rejects a set
    // with 409 asap_after_install_start (BUG-11).
    const asapLocked = isInstallStartOrLater(stage) && !isAsap;
    const [installer, setInstaller] = useState('');
    const [installerOptions, setInstallerOptions] = useState([]);
    const [error, setError] = useState('');

    const initialInstaller = currentInstaller || '';
    const initialShipYmd = toYmd(currentShipDate);

    useEffect(() => {
        if (isOpen) {
            setAsapToggle(!!isAsap);
            setInstaller(initialInstaller);
            const shipYmd = toYmd(currentShipDate);
            // An ASAP row's date is a real hand-set date, so it loads like any other.
            const installYmd = toYmd(currentDate);
            setShipDateInput(shipYmd);
            setDateInput(installYmd);
            // N5: shipping stages always open in manual mode (Break). Estimated Link
            // (ship = install − 1) only after the user opts in — never by default after
            // formula wipe or a stage move into Ship Planning / Ship Complete.
            if (SHIPPING_STAGES.has(stage)) {
                setLinked(false);
            } else {
                // Outside shipping: link when empty/one-sided or already 1 biz day apart;
                // a deliberately larger gap opens unlinked so Break is not required first.
                setLinked(areDatesLinked(installYmd, shipYmd));
            }
            setError('');
        }
    }, [isOpen, currentDate, currentShipDate, isAsap, initialInstaller, stage, startInstallFormulaTF]);

    useEffect(() => {
        if (isOpen && installerOptions.length === 0) {
            jobsApi.getInstallerTeams()
                .then(setInstallerOptions)
                .catch(() => { /* leave options empty; selector still shows current value */ });
        }
    }, [isOpen, installerOptions.length]);

    // While linked: ship = install − 1 business day (symmetric edits).
    // After Break (N6): either field edits alone; Link re-ties them.
    const handleDateInputChange = (e) => {
        const value = e.target.value;
        setDateInput(value);
        if (value && linked) {
            setShipDateInput(subtractBusinessDays(value, 1));
        }
        setError('');
    };

    const handleShipDateChange = (e) => {
        const value = e.target.value;
        setShipDateInput(value);
        if (value && linked) {
            setDateInput(addBusinessDays(value, 1));
        }
        setError('');
    };

    const handleBreak = () => {
        setLinked(false);
        setError('');
    };

    const handleLink = () => {
        // Re-link and snap to the default relationship (prefer install as anchor).
        setLinked(true);
        if (dateInput) {
            setShipDateInput(subtractBusinessDays(dateInput, 1));
        } else if (shipDateInput) {
            setDateInput(addBusinessDays(shipDateInput, 1));
        }
        setError('');
    };

    const handleAsapToggle = (e) => {
        // Flag only — the date fields stay live and stay filled. ASAP marks the row a rush;
        // the date is still the user's to set, and Save below refuses without one.
        //
        // Only ever turns ASAP ON: the box is disabled once the flag is set (see the
        // checkbox below), because Save has no path that clears it — that is Clear ASAP's
        // job. Leaving it un-checkable silently was a dead control: the box read
        // unchecked, Save wrote the date, and the row stayed red with no explanation.
        setAsapToggle(e.target.checked);
        setError('');
    };

    const installerChanged = installer !== initialInstaller;
    const shipChanged = (shipDateInput || null) !== (initialShipYmd || null);
    // Turning ASAP on (off -> on) sets the flag and then saves the date in one action.
    // When ASAP is already set the toggle stays on and the row edits normally.
    const turningAsapOn = asapToggle && !isAsap;

    const handleSave = () => {
        // Validate BEFORE writing anything. The ship date used to be persisted up front,
        // so a rejected "Set ASAP" still saved it — and saved it again on the retry.
        if (turningAsapOn && !dateInput) {
            // ASAP is a flag on a real date, not a date of its own — refuse without one.
            setError('ASAP needs a Start Install date — pick the date this has to go in by');
            return;
        }
        if (!dateInput && !installerChanged && !shipChanged) {
            setError('Please select an install date, ship date, or installer');
            return;
        }
        // Ship date is independent of install/ASAP — persist it whenever it changed, so it
        // works alongside a date/installer save or on its own.
        if (shipChanged && onSaveShipDate) {
            onSaveShipDate(shipDateInput || null);
        }
        if (turningAsapOn) {
            onSetAsap(installerChanged ? installer : undefined, dateInput);
            return;
        }
        if (!dateInput && !installerChanged) {
            // Ship-date-only change: nothing to send to the install endpoint.
            onClose();
            return;
        }
        // Installer is sent only when it changed, so a date-only save leaves it alone.
        onSave(dateInput || null, installerChanged ? installer : undefined);
    };

    const handleCancel = () => {
        setDateInput('');
        setShipDateInput('');
        setLinked(true);
        setAsapToggle(!!isAsap);
        setInstaller(initialInstaller);
        setError('');
        onClose();
    };

    if (!isOpen) return null;

    const confirmLabel = turningAsapOn ? 'Set ASAP' : 'Save';
    // ASAP cannot be saved without a date, so it does not enable the button on its own.
    const confirmEnabled = !!dateInput || installerChanged || shipChanged;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full mx-4">
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                    <div className="flex items-center justify-between">
                        <h2 className="text-2xl font-bold text-white">
                            Set Install &amp; Ship Dates
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
                    {/* ASAP is a rush flag on work that has not started. The server refuses
                        it once the stage is `Install Start` or later, so don't offer it —
                        an enabled control that 409s is worse than a disabled one. */}
                    <label className={`flex items-start gap-2 mb-4 select-none ${
                        asapLocked ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'
                    }`}>
                        <input
                            type="checkbox"
                            checked={asapToggle}
                            onChange={handleAsapToggle}
                            disabled={asapLocked || isAsap}
                            className="mt-1 h-4 w-4 accent-red-600"
                        />
                        <span>
                            <span className="block text-sm font-semibold text-gray-700">ASAP Mode</span>
                            <span className="block text-xs text-gray-500">
                                {asapLocked
                                    ? 'Unavailable once install has started.'
                                    : isAsap
                                        ? 'This release is flagged a rush. Use Clear ASAP below to remove it; the date stays.'
                                        : 'Marks the release a rush (red) and rips to Shipping Planning at Paint Complete. Set the Start Install date below — ASAP will not pick one for you.'}
                            </span>
                        </span>
                    </label>

                    {/* Ship Date → Start Install; Break/Link sits in the middle (N6). */}
                    <div className="mb-2 flex flex-col sm:flex-row items-stretch sm:items-end gap-2 sm:gap-3">
                        <div className="flex-1 min-w-0">
                            <label className="block text-sm font-semibold text-gray-700 mb-2">
                                Ship Date
                            </label>
                            <input
                                type="date"
                                value={shipDateInput}
                                onChange={handleShipDateChange}
                                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500"
                            />
                        </div>
                        <div className="flex flex-col items-center justify-end pb-0.5 shrink-0 self-center sm:self-end">
                            {linked ? (
                                <button
                                    type="button"
                                    onClick={handleBreak}
                                    className="px-2.5 py-1.5 text-xs font-semibold rounded-md border border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100 transition-colors whitespace-nowrap"
                                    title="Break link — stop auto-updating the other date when you edit one"
                                >
                                    Break
                                </button>
                            ) : (
                                <button
                                    type="button"
                                    onClick={handleLink}
                                    className="px-2.5 py-1.5 text-xs font-semibold rounded-md border border-accent-300 bg-accent-50 text-accent-800 hover:bg-accent-100 transition-colors whitespace-nowrap"
                                    title="Link dates (ship = start install − 1 business day)"
                                >
                                    Link
                                </button>
                            )}
                        </div>
                        <div className="flex-1 min-w-0">
                            <label className="block text-sm font-semibold text-gray-700 mb-2">
                                Start Install Date
                            </label>
                            <input
                                type="date"
                                value={dateInput}
                                onChange={handleDateInputChange}
                                className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500 ${
                                    error ? 'border-red-500' : 'border-gray-300'
                                }`}
                            />
                        </div>
                    </div>

                    {error && (
                        <p className="text-red-600 text-sm mb-2">{error}</p>
                    )}
                    <p className="text-gray-500 text-xs mb-6">
                        {linked
                                ? 'Ship and Install are linked (ship = install − 1 business day). Use Break between the fields for an independent gap. Saving Start Install sets a hard date and cascades; Ship date does not push to Trello or affect scheduling.'
                                : SHIPPING_STAGES.has(stage)
                                    ? 'At Ship Planning/Complete, Ship and Install start independent (manual). Set each date yourself, or use Link to re-tie them (ship = install − 1 business day).'
                                : 'Ship and Install are independent. Use Link between the fields to re-tie them. Saving Start Install sets a hard date and cascades; Ship date does not push to Trello or affect scheduling.'}
                    </p>

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
                            {startInstallFormulaTF === false && currentDate && onClearHardDate && (
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
