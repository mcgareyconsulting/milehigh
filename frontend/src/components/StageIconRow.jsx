/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Banana Code progress indicator — renders 7 department icons (Admin → Install) per release, colored by the stage's position in the spec mapping.
 * exports:
 *   StageIconRow: Per-row indicator. Props: stage (string), iconSize (number).
 *   BananaCodeHeader: Column header (title + 7 dept short labels), aligned to StageIconRow.
 * imports_from: [react, ../utils/stageProgress, ../utils/holdFlag]
 * imported_by: [frontend/src/components/JobsTableRow.jsx, frontend/src/pages/JobLog.jsx, frontend/src/pages/Archive.jsx]
 * invariants:
 *   - Icon assets live at /icons/<dept>_<state>.png (gray/green/half/yellow).
 *   - Hold stage overlays a small red flag on the Weld slot via shared geometry.
 *   - Source PNGs are 2:3 portrait; rendered at that aspect ratio.
 */
import React from 'react';
import {
    DEPARTMENTS,
    DEPARTMENT_LABELS,
    DEPARTMENT_LABELS_SHORT,
    BANANA_CODE_ICON_SIZE,
    getStageIconRow,
    isHoldStage,
} from '../utils/stageProgress';
import {
    HOLD_FLAG_VIEWBOX,
    HOLD_FLAG_COLORS,
    HOLD_FLAG_POLE,
    HOLD_FLAG_POINTS,
    HOLD_FLAG_STROKE_WIDTH,
} from '../utils/holdFlag';

const ICON_BASE = '/icons';
const ICON_ASPECT_W_OVER_H = 2 / 3;
const HOLD_FLAG_PATH_D = `M ${HOLD_FLAG_POINTS.map(([x, y]) => `${x} ${y}`).join(' L ')} Z`;

function HoldFlag({ width }) {
    const flagSize = Math.max(10, Math.round(width * 0.7));
    return (
        <svg
            width={flagSize}
            height={flagSize}
            viewBox={`0 0 ${HOLD_FLAG_VIEWBOX} ${HOLD_FLAG_VIEWBOX}`}
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
            <line
                x1={HOLD_FLAG_POLE.x1} y1={HOLD_FLAG_POLE.y1}
                x2={HOLD_FLAG_POLE.x2} y2={HOLD_FLAG_POLE.y2}
                stroke={HOLD_FLAG_COLORS.pole}
                strokeWidth={HOLD_FLAG_POLE.width}
                strokeLinecap="round"
            />
            <path
                d={HOLD_FLAG_PATH_D}
                fill={HOLD_FLAG_COLORS.fill}
                stroke={HOLD_FLAG_COLORS.stroke}
                strokeWidth={HOLD_FLAG_STROKE_WIDTH}
                strokeLinejoin="round"
            />
        </svg>
    );
}

function StageIconRowImpl({ stage, iconSize = BANANA_CODE_ICON_SIZE }) {
    const row = getStageIconRow(stage);
    const hold = isHoldStage(stage);
    const titleStage = stage || 'Released';
    const w = iconSize;
    const h = Math.round(iconSize / ICON_ASPECT_W_OVER_H);

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

export const StageIconRow = React.memo(StageIconRowImpl);

// Column header for the Banana Code column. Renders the "Banana Code" title
// stacked over 7 short dept labels whose per-slot width matches StageIconRow's
// per-icon width — pass the same iconSize to keep them aligned.
export function BananaCodeHeader({ iconSize = BANANA_CODE_ICON_SIZE }) {
    return (
        <div className="flex flex-col items-center leading-tight">
            <span>Banana Code</span>
            <div className="flex items-center justify-center gap-1 mt-0.5 text-[8px] font-medium normal-case tracking-normal text-gray-500 dark:text-slate-400">
                {DEPARTMENT_LABELS_SHORT.map((d) => (
                    <span
                        key={d}
                        className="inline-block text-center overflow-hidden"
                        style={{ width: iconSize }}
                    >
                        {d}
                    </span>
                ))}
            </div>
        </div>
    );
}
