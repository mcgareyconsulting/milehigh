// Ordered Job Log stage progression with short display labels.
// Mirrors the inline list in JobsTableRow.jsx — keep in
// lock-step with those (and app/api/helpers.py STAGE_PROGRESSION_RANK) when
// stages change. Used by the touch-view StageEditor dropdown.
export const STAGE_OPTIONS = [
    { value: 'Released', label: 'Released' },
    { value: 'Material Ordered', label: 'Mat. Order' },
    { value: 'Cut Start', label: 'Cut Start' },
    { value: 'Cut Complete', label: 'Cut comp' },
    { value: 'Fitup Start', label: 'Fitup start' },
    { value: 'Fitup Complete', label: 'Fitup comp' },
    { value: 'Weld Start', label: 'Weld start' },
    { value: 'Weld Complete', label: 'Weld comp' },
    { value: 'Welded QC', label: 'Welded QC' },
    { value: 'Paint Start', label: 'Paint Start' },
    { value: 'Paint Complete', label: 'Paint comp' },
    { value: 'Hold', label: 'Hold' },
    { value: 'Store at MHMW', label: 'Store' },
    { value: 'Ship Planning', label: 'Ship plan' },
    { value: 'Ship Complete', label: 'Ship comp' },
    { value: 'Install Start', label: 'Install start' },
    { value: 'Install Complete', label: 'Install comp' },
    { value: 'Complete', label: 'Complete' },
];

// Stage progression rank — mirrors app/api/helpers.py STAGE_PROGRESSION_RANK.
export const STAGE_PROGRESSION_RANK = {
    'Released':         0, 'Material Ordered': 1, 'Cut Start':       2, 'Cut Complete':     3,
    'Fitup Start':      4, 'Fitup Complete':   5, 'Weld Start':      6, 'Weld Complete':    7,
    'Welded QC':        9, 'Paint Start':     10, 'Paint Complete': 11,
    'Store at MHMW':   12, 'Ship Planning':   13, 'Ship Complete':  14,
    'Install Start':   15, 'Install Complete':16, 'Complete':       17,
    'Hold':            99,
};

// BUG-11: where a hard install date loses its colour. The trigger is the release
// reaching the Install Start STAGE — NOT a start_install date being set, and not the
// ship stages. A release can carry a hard date for weeks before install begins, and
// its colour (green, or yellow once overdue) has to stay readable that whole time:
// a yellow overdue date is a scored EOS metric, so hiding it early buries the problem.
// Keep in lock-step with is_at_or_past_color_dump() in
// app/brain/job_log/features/start_install/shipping_stage_date_discipline.py.
export const COLOR_DUMP_STAGE = 'Install Start';

export const isAtOrPastColorDump = (stage) => {
    const rank = STAGE_PROGRESSION_RANK[stage];
    // Hold (99) is a parking spot, not progress past install.
    return rank !== undefined && rank >= STAGE_PROGRESSION_RANK[COLOR_DUMP_STAGE] && rank < 99;
};
