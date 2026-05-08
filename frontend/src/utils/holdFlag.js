// Shared geometry + colors for the red-flag overlay drawn on the Weld slot
// when a release is on Hold. Used by the React SVG renderer (StageIconRow)
// and the canvas-rasterized PDF export (jobLogPdf).

export const HOLD_FLAG_VIEWBOX = 16;
export const HOLD_FLAG_COLORS = {
    pole: '#1f2937',
    fill: '#dc2626',
    stroke: '#7f1d1d',
};
export const HOLD_FLAG_POLE = { x1: 3, y1: 1, x2: 3, y2: 15, width: 1.5 };
export const HOLD_FLAG_POINTS = [
    [3, 2],
    [13, 4],
    [9, 6.5],
    [13, 9],
    [3, 7.5],
];
export const HOLD_FLAG_STROKE_WIDTH = 0.75;
