// Stage-completeness and stage-icon helpers shared between the on-screen
// Job Log row and the print/PDF view.

// Defensive Complete check — tolerates whitespace + case drift in the stage value.
export const isCompleteStage = (stage) =>
    (stage || '').toString().trim().toLowerCase() === 'complete';

// Defensive Hold check — used to overlay a red flag on the Weld icon.
export const isHoldStage = (stage) =>
    (stage || '').toString().trim().toLowerCase() === 'hold';

// Department order shown in the Banana Code column, left → right.
export const DEPARTMENTS = ['admin', 'cut', 'fitup', 'weld', 'paint', 'ship', 'install'];

// Display labels paired with DEPARTMENTS (1:1 by index). Used for tooltips.
export const DEPARTMENT_LABELS = ['Admin', 'Cut', 'Fitup', 'Weld', 'Paint', 'Ship', 'Install'];

// Short forms used in the Banana Code column header above each icon. Same
// 1:1 alignment with DEPARTMENTS — keep in lock-step.
export const DEPARTMENT_LABELS_SHORT = ['Adm', 'Cut', 'Fit', 'Weld', 'Paint', 'Ship', 'Inst'];

// Single source of truth for icon size + per-slot width. Rendering sites must
// pass this through so header sub-labels and the icon row stay aligned.
export const BANANA_CODE_ICON_SIZE = 26;

// Valid icon states. Mirrors the suffix of the icon filenames in /icons.
export const ICON_STATES = ['gray', 'green', 'half', 'yellow'];

// Authoritative stage → 7-icon-state mapping (MHMW Banana Code spec).
// Each value is a tuple aligned to DEPARTMENTS:
//   'gray'   = stage not yet reached
//   'green'  = stage just started
//   'half'   = stage in progress (half green/yellow)
//   'yellow' = stage complete
// Hold is a special case: shows yellow through Fitup and gray weld+after,
// with a red-flag overlay on the Weld slot rendered by StageIconRow.
export const STAGE_TO_ICON_ROW = {
    'Released':         ['gray',   'gray',   'gray',   'gray',   'gray',   'gray',   'gray'],
    'Material Ordered': ['green',  'gray',   'gray',   'gray',   'gray',   'gray',   'gray'],
    'Cut Start':        ['yellow', 'green',  'gray',   'gray',   'gray',   'gray',   'gray'],
    'Cut Complete':     ['yellow', 'yellow', 'gray',   'gray',   'gray',   'gray',   'gray'],
    'Fitup Start':      ['yellow', 'yellow', 'green',  'gray',   'gray',   'gray',   'gray'],
    'Fitup Complete':   ['yellow', 'yellow', 'yellow', 'gray',   'gray',   'gray',   'gray'],
    'Weld Start':       ['yellow', 'yellow', 'yellow', 'green',  'gray',   'gray',   'gray'],
    'Weld Complete':    ['yellow', 'yellow', 'yellow', 'yellow', 'gray',   'gray',   'gray'],
    'Welded QC':        ['yellow', 'yellow', 'yellow', 'yellow', 'gray',   'gray',   'gray'],
    'Hold':             ['yellow', 'yellow', 'yellow', 'gray',   'gray',   'gray',   'gray'],
    'Paint Start':      ['yellow', 'yellow', 'yellow', 'yellow', 'green',  'gray',   'gray'],
    'Paint Complete':   ['yellow', 'yellow', 'yellow', 'yellow', 'yellow', 'gray',   'gray'],
    'Store at MHMW':    ['yellow', 'yellow', 'yellow', 'yellow', 'yellow', 'gray',   'gray'],
    'Ship Planning':    ['yellow', 'yellow', 'yellow', 'yellow', 'yellow', 'green',  'gray'],
    'Ship Complete':    ['yellow', 'yellow', 'yellow', 'yellow', 'yellow', 'yellow', 'gray'],
    'Install Start':    ['yellow', 'yellow', 'yellow', 'yellow', 'yellow', 'yellow', 'green'],
    'Install Complete': ['yellow', 'yellow', 'yellow', 'yellow', 'yellow', 'yellow', 'half'],
    'Complete':         ['yellow', 'yellow', 'yellow', 'yellow', 'yellow', 'yellow', 'yellow'],
};

const RELEASED_ROW = STAGE_TO_ICON_ROW['Released'];

// Returns the 7-state tuple for a given stage. Unknown stages fall back to
// the all-gray Released row so the UI never crashes on stale data.
export const getStageIconRow = (stage) => STAGE_TO_ICON_ROW[stage] || RELEASED_ROW;
