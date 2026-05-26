/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Self-contained, table-free Stage control for the touch card views. Renders the current stage
 *   as a colored pill (group color, matching JobLogCard) backed by a native <select> so the option
 *   picker is OS-native (never clipped by the scrolling row list) and touch-friendly. Writes through
 *   jobsApi.updateStage and refetches via onUpdate, so the backend Complete-zone cascade (job_comp/
 *   fab_order) is reflected without re-implementing it client-side.
 * exports:
 *   default StageEditor: Props — row, onUpdate, stageToGroup, stageGroupColors, className.
 * imports_from: [react, ../services/jobsApi, ../constants/stages]
 * imported_by: [frontend/src/components/JobLogRow.jsx]
 * invariants:
 *   - Pill color comes from the stage's group (stageToGroup → stageGroupColors), consistent with JobLogCard.
 *   - stopPropagation so changing the stage never toggles the parent card row.
 *   - Read-only (no onUpdate) renders a static pill.
 */
import React, { useState } from 'react';
import { jobsApi } from '../services/jobsApi';
import { STAGE_OPTIONS } from '../constants/stages';

export default function StageEditor({
    row,
    onUpdate,
    stageToGroup,
    stageGroupColors,
    className = '',
}) {
    const [saving, setSaving] = useState(false);

    const job = row['Job #'];
    const release = row['Release #'];
    const stage = row['Stage'] || 'Released';
    const readOnly = !onUpdate;

    const group = stageToGroup?.[stage];
    const colors = stageGroupColors?.[group];
    const pillStyle = colors
        ? { backgroundColor: colors.light, color: colors.text, borderColor: colors.border }
        : undefined;

    const label = STAGE_OPTIONS.find((o) => o.value === stage)?.label || stage;

    const handleChange = async (e) => {
        const next = e.target.value;
        if (next === stage) return;
        setSaving(true);
        try {
            await jobsApi.updateStage(job, release, next);
            if (onUpdate) onUpdate();
        } catch (err) {
            alert(`Failed to update stage: ${err.message}`);
        } finally {
            setSaving(false);
        }
    };

    const pillCls = `appearance-none rounded border text-xs font-semibold text-center px-2 py-0.5 pr-5 transition-opacity ${
        saving ? 'opacity-50 cursor-wait' : 'cursor-pointer'
    } ${className}`;

    if (readOnly) {
        return (
            <span
                className="inline-block rounded border text-xs font-semibold px-2 py-0.5 whitespace-nowrap"
                style={pillStyle}
                title={`Stage: ${stage}`}
            >
                {label}
            </span>
        );
    }

    return (
        <div className="relative inline-block shrink-0" onClick={(e) => e.stopPropagation()}>
            <select
                value={stage}
                disabled={saving}
                onChange={handleChange}
                className={pillCls}
                style={pillStyle}
                title={`Stage: ${stage} — tap to change`}
                aria-label="Stage"
            >
                {STAGE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                ))}
            </select>
            {/* Chevron — purely decorative; the native select owns the interaction. */}
            <svg
                className="pointer-events-none absolute right-1 top-1/2 -translate-y-1/2 opacity-60"
                width="9" height="9" viewBox="0 0 11 11" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
                style={{ color: colors?.text }}
                aria-hidden="true"
            >
                <path d="M2 4l3.5 3.5L9 4" />
            </svg>
        </div>
    );
}
