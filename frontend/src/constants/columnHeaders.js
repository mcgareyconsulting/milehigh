// Display-only header label overrides for the Job Log table. The column key
// (data field) is unchanged; this only renames what the user sees in the
// `<th>`. Kept out of CSS / inline state so JobLog and Archive render the
// same labels without duplication.
export const HEADER_OVERRIDES = {
    'Job #': 'Job',
    'Release #': 'Rel',
    'Job': 'Job Name',
    'Install HRS': 'Install Hrs',
    'Paint color': 'Paint Color',
    'BY': 'By',
    'Start install': 'Start Install',
    'Comp. ETA': 'Comp ETA',
    'Job Comp': 'Install Prog',
    'Mat. Ord.': 'Mats',
};
