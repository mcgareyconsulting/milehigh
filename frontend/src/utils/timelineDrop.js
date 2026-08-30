/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Pure geometry for the Timeline's drag-to-assign — turn the pointer position where a card
 *   was released into the calendar date of the column underneath it. Extracted from GanttChart so
 *   the arithmetic that decides a real scheduling write is unit-testable without a DOM.
 * exports:
 *   columnAtDropX: Which chart column (0-based, clamped to the chart) a viewport X lands in
 *   dateAtDropX: The ISO date that column starts on — what a drop writes to start_install
 * imports_from: []
 * imported_by: [../components/GanttChart.jsx]
 * invariants:
 *   - dropX and laneLeft are BOTH viewport coordinates (getBoundingClientRect space). The lane's
 *     chart element spans the full chart width and moves with horizontal scroll, so subtracting its
 *     live left edge already accounts for scrollLeft — no scroll term belongs in this math.
 *   - The column is clamped into [0, totalCols-1]: releasing past either end of the chart schedules
 *     to the nearest real column rather than silently doing nothing.
 *   - At week zoom (colDays=7) a column resolves to the date it STARTS on. chartRange.firstDay is
 *     always a Monday, so week columns resolve to Mondays.
 *   - No weekend or business-day adjustment. A dropped date is written exactly where the user put
 *     it — the timeline shows weekends, and silently sliding a card off the day someone chose would
 *     automate away the control this feature exists to give them.
 */

/** Add whole calendar days to a YYYY-MM-DD string, returning YYYY-MM-DD. */
const addDays = (isoDate, days) => {
    const d = new Date(isoDate + 'T00:00:00');
    d.setDate(d.getDate() + days);
    return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-');
};

/**
 * The 0-based chart column under a drop.
 *
 * @param {number} dropX     viewport X where the pointer let go
 * @param {number} laneLeft  viewport X of the lane's chart area left edge (live rect)
 * @param {number} colPx     rendered width of one column
 * @param {number} totalCols how many columns the chart has
 */
export function columnAtDropX(dropX, laneLeft, colPx, totalCols) {
    if (!(colPx > 0) || !(totalCols > 0)) return null;
    const col = Math.floor((dropX - laneLeft) / colPx);
    return Math.min(Math.max(col, 0), totalCols - 1);
}

/**
 * The date a drop schedules to: the first day of the column the pointer let go over.
 *
 * @param {number} dropX     viewport X where the pointer let go
 * @param {number} laneLeft  viewport X of the lane's chart area left edge (live rect)
 * @param {object} geom      { colPx, colDays, firstDay, totalCols } — the chart's current geometry
 * @returns {string|null}    YYYY-MM-DD, or null if the geometry isn't ready
 */
export function dateAtDropX(dropX, laneLeft, { colPx, colDays, firstDay, totalCols }) {
    if (!firstDay) return null;
    const col = columnAtDropX(dropX, laneLeft, colPx, totalCols);
    if (col === null) return null;
    return addDays(firstDay, col * (colDays || 1));
}
