// Stage-completeness and banana-progress helpers shared between the on-screen
// Job Log row, the print view, and any other consumer.

// Defensive Complete check — tolerates whitespace + case drift in the stage value.
export const isCompleteStage = (stage) =>
    (stage || '').toString().trim().toLowerCase() === 'complete';

// 5-step banana fill (XXXOO-style). Each stage maps to one of five urgency levels.
export const STAGE_TO_BANANA_STEP = {
    'Released': 0, 'Material Ordered': 1, 'Cut start': 1, 'Cut Complete': 1,
    'Fitup Start': 1, 'Fit Up Complete.': 1, 'Weld Start': 2, 'Weld Complete': 2,
    'Welded QC': 3, 'Paint Start': 4, 'Paint complete': 4,
    'Store at MHMW for shipping': 4, 'Shipping planning': 4,
    'Shipping completed': 5, 'Complete': 5,
};

// Returns 0..1 for BananaIcon. Hold pauses progress at 0; unknown stages → 0.
export const getBananaProgress = (stage) => {
    if (stage === 'Hold') return 0;
    const step = STAGE_TO_BANANA_STEP[stage];
    return step == null ? 0 : step / 5;
};
