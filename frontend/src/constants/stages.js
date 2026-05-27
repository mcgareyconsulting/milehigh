// Ordered Job Log stage progression with short display labels.
// Mirrors the inline lists in JobsTableRow.jsx and PMBoardList.jsx — keep in
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
