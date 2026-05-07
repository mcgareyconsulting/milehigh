/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Banana Code progress indicator — renders 7 department icons (Admin → Install) per release, colored by the stage's position in the spec mapping.
 * exports:
 *   StageIconRow: Per-row indicator. Props: stage (string), iconSize (number, default 20).
 * imports_from: [react, ../utils/stageProgress]
 * imported_by: [frontend/src/components/JobsTableRow.jsx]
 * invariants:
 *   - Icon assets live at /icons/<dept>_<state>.png (gray/green/half/yellow).
 *   - Hold stage overlays a small red flag on the Weld slot.
 *   - Pixel-art icons render with imageRendering: pixelated for crispness.
 */
import React from 'react';
import {
    DEPARTMENTS,
    DEPARTMENT_LABELS,
    getStageIconRow,
    isHoldStage,
} from '../utils/stageProgress';

const ICON_BASE = '/icons';

// Source PNGs are 1024×1536 (2:3 portrait). Render at the same aspect ratio
// so the bananas don't get squashed.
const ICON_ASPECT = 2 / 3;

function HoldFlag({ width }) {
    const flagSize = Math.max(10, Math.round(width * 0.7));
    return (
        <svg
            width={flagSize}
            height={flagSize}
            viewBox="0 0 16 16"
            xmlns="http://www.w3.org/2000/svg"
            style={{
                position: 'absolute',
                top: -2,
                right: -2,
                pointerEvents: 'none',
                filter: 'drop-shadow(0 0 1px rgba(0,0,0,0.45))',
            }}
            aria-hidden="true"
        >
            <line x1="3" y1="1" x2="3" y2="15" stroke="#1f2937" strokeWidth="1.5" strokeLinecap="round" />
            <path d="M3 2 L13 4 L9 6.5 L13 9 L3 7.5 Z" fill="#dc2626" stroke="#7f1d1d" strokeWidth="0.75" strokeLinejoin="round" />
        </svg>
    );
}

export function StageIconRow({ stage, iconSize = 22 }) {
    const row = getStageIconRow(stage);
    const hold = isHoldStage(stage);
    const titleStage = stage || 'Released';
    const w = iconSize;
    const h = Math.round(iconSize / ICON_ASPECT); // 2:3 portrait

    return (
        <div className="flex items-center justify-center gap-1" title={`Stage: ${titleStage}`}>
            {DEPARTMENTS.map((dept, i) => {
                const state = row[i];
                const label = DEPARTMENT_LABELS[i];
                return (
                    <span
                        key={dept}
                        className="relative inline-flex shrink-0"
                        style={{ width: w, height: h }}
                    >
                        <img
                            src={`${ICON_BASE}/${dept}_${state}.png`}
                            alt={`${label} ${state}`}
                            width={w}
                            height={h}
                            draggable={false}
                            style={{ display: 'block' }}
                        />
                        {hold && dept === 'weld' && <HoldFlag width={w} />}
                    </span>
                );
            })}
        </div>
    );
}
