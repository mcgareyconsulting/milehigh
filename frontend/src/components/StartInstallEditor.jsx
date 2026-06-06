/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Self-contained, table-free Start Install control for the touch card views (mobile big card,
 *   tablet expandable row). Renders the colored ASAP/hard-date/formula trigger and owns a
 *   StartInstallDateModal so users can set a hard date, flag ASAP (2-per-PM cap enforced), or clear —
 *   the same actions available from the desktop table cell, without embedding JobsTableRow.
 * exports:
 *   default StartInstallEditor: Props — row, onUpdate, formatDate, variant ('tile' | 'pill'), className.
 * imports_from: [react, ./StartInstallDateModal, ../services/jobsApi, ../utils/asap, ../utils/formatters]
 * imported_by: [frontend/src/components/JobLogCard.jsx, frontend/src/components/JobLogRow.jsx]
 * invariants:
 *   - Mirrors JobsTableRow's Start install colors: ASAP=red, past hard date=yellow, future hard date=green.
 *   - The trigger stops click propagation so it never triggers the parent card's open/expand handler.
 *   - Editing requires an onUpdate callback; without it (e.g. Archive cards) the control renders read-only.
 */
import React, { useState } from 'react';
import { StartInstallDateModal } from './StartInstallDateModal';
import { jobsApi } from '../services/jobsApi';
import { setAsapWithCapConfirm } from '../utils/asap';
import { formatDateShort } from '../utils/formatters';

export default function StartInstallEditor({
    row,
    onUpdate,
    formatDate = formatDateShort,
    variant = 'tile',
    className = '',
}) {
    const [open, setOpen] = useState(false);

    const job = row['Job #'];
    const release = row['Release #'];
    const value = row['Start install'];

    const isAsap = row['start_install_asap'] === true;
    // A no-color date (auto-recorded when an ASAP release reached Ship Complete+) shows
    // the date plainly — neither the red ASAP nor the green/yellow hard-date treatment.
    const isNoColor = row['start_install_no_color'] === true;
    const isHardDate = !isAsap && !isNoColor && row['start_install_formulaTF'] === false && !!value;
    const now = new Date();
    const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const installDay = String(value ?? '').split('T')[0];
    const isHardDatePast = isHardDate && installDay < todayStr;

    const displayValue = isAsap ? 'ASAP' : (formatDate(value) || '—');

    let colorClass;
    if (isAsap) colorClass = 'bg-red-500 text-white hover:bg-red-600';
    else if (isHardDatePast) colorClass = 'bg-yellow-400 text-gray-900 hover:bg-yellow-500';
    else if (isHardDate) colorClass = 'bg-green-500 text-white hover:bg-green-600';
    else colorClass = 'bg-gray-50 dark:bg-slate-700/50 text-gray-900 dark:text-slate-100 hover:bg-accent-50 dark:hover:bg-slate-600';

    const colored = isAsap || isHardDate || isHardDatePast;
    const readOnly = !onUpdate;
    const refresh = () => { if (onUpdate) onUpdate(); };

    const handleSave = async (dateValue, installer) => {
        setOpen(false);
        try {
            await jobsApi.updateStartInstall(job, release, dateValue, installer);
            refresh();
        } catch (e) {
            alert(`Failed to update start install: ${e.message}`);
        }
    };

    const handleSetAsap = async () => {
        setOpen(false);
        try {
            const ok = await setAsapWithCapConfirm(job, release);
            if (ok) refresh();
        } catch (e) {
            alert(`Failed to set ASAP: ${e.message}`);
        }
    };

    const handleClearAsap = async () => {
        setOpen(false);
        try {
            await jobsApi.setStartInstallAsap(job, release, false);
            refresh();
        } catch (e) {
            alert(`Failed to clear ASAP: ${e.message}`);
        }
    };

    const handleClearHardDate = async () => {
        setOpen(false);
        try {
            await jobsApi.clearStartInstallHardDate(job, release);
            refresh();
        } catch (e) {
            alert(`Failed to clear hard date: ${e.message}`);
        }
    };

    const openModal = (e) => {
        e.stopPropagation();
        setOpen(true);
    };

    const title = readOnly ? displayValue : `${displayValue} — tap to set hard date or ASAP`;

    let trigger;
    if (variant === 'pill') {
        const cls = `inline-flex items-center justify-center min-w-[72px] rounded px-2 py-0.5 text-xs font-semibold tabular-nums leading-none transition-colors ${colorClass} ${className}`;
        trigger = readOnly
            ? <span className={cls} title={title}>{displayValue}</span>
            : <button type="button" onClick={openModal} title={title} className={cls}>{displayValue}</button>;
    } else {
        const cls = `block w-full text-left rounded px-2 py-1 transition-colors ${colorClass} ${className}`;
        const inner = (
            <>
                <div className={`text-[10px] uppercase tracking-wide ${colored ? 'opacity-80' : 'text-gray-500 dark:text-slate-400'}`}>
                    Start Install
                </div>
                <div className="font-semibold">{displayValue}</div>
                <div className={`text-[10px] ${colored ? 'opacity-80' : 'text-gray-500 dark:text-slate-400'}`}>
                    {row['installer'] || '—'}
                </div>
            </>
        );
        trigger = readOnly
            ? <div className={cls} title={title}>{inner}</div>
            : <button type="button" onClick={openModal} title={title} className={cls}>{inner}</button>;
    }

    return (
        <>
            {trigger}
            {!readOnly && (
                <StartInstallDateModal
                    isOpen={open}
                    onClose={() => setOpen(false)}
                    currentDate={value}
                    currentInstaller={row['installer']}
                    onSave={handleSave}
                    onClearHardDate={handleClearHardDate}
                    onSetAsap={handleSetAsap}
                    onClearAsap={handleClearAsap}
                    jobNumber={job}
                    releaseNumber={release}
                    startInstallFormulaTF={row['start_install_formulaTF']}
                    isAsap={isAsap}
                />
            )}
        </>
    );
}
