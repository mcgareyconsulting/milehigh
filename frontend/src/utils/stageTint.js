/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Maps a release stage to the design-token pill tint used by the Job Log table and the release modal, and gives the canonical stage ladder for the modal's progress bar.
 * exports:
 *   stageTint: (stage) => { bg, fg } CSS var pair for a stage pill
 *   STAGE_LADDER: canonical stage progression, least to most complete
 *   stageLadderIndex: (stage) => position in STAGE_LADDER, or -1
 * imports_from: []
 * imported_by: [frontend/src/components/ReleaseHubModal.jsx, frontend/src/components/JobDetailsBody.jsx]
 * invariants:
 *   - The stage->hue mapping mirrors `stageColors` in hooks/useJobsFilters.js. Both must change
 *     together, or the table pill and the modal pill disagree for the same release.
 */

// The Aug 2026 handoff's prototype collapses every stage into green/blue/purple.
// The app has always shown Welded QC in amber, and the handoff README says to
// keep the existing stage->color mapping rather than invent hues — so this keeps
// the app's four and expresses them in the handoff's palette.
const HUE_BY_STAGE = {
    'Released': 'blue',
    'Material Ordered': 'blue',
    'Cut Start': 'blue',
    'Cut Complete': 'blue',
    'Fitup Start': 'blue',
    'Fitup Complete': 'blue',
    'Weld Start': 'blue',
    'Weld Complete': 'blue',
    'Hold': 'blue',
    'Welded QC': 'amber',
    'Paint Start': 'blue',
    'Paint Complete': 'green',
    'Store at MHMW': 'green',
    'Ship Planning': 'green',
    'Ship Complete': 'purple',
    'Install Start': 'purple',
    'Install Complete': 'purple',
    'Complete': 'purple',
};

export function stageTint(stage) {
    const hue = HUE_BY_STAGE[(stage || '').toString().trim()] || 'blue';
    return { bg: `var(--st-${hue}-bg)`, fg: `var(--st-${hue}-fg)` };
}

// The real progression, not the handoff prototype's shortened 10-step list —
// that one omits Material Ordered, both Cut stages, Fitup Complete, Weld
// Complete, Store at MHMW and Complete, so a release sitting in any of them
// would fall off the ladder entirely.
export const STAGE_LADDER = [
    'Released',
    'Material Ordered',
    'Cut Start',
    'Cut Complete',
    'Fitup Start',
    'Fitup Complete',
    'Weld Start',
    'Weld Complete',
    'Welded QC',
    'Paint Start',
    'Paint Complete',
    'Store at MHMW',
    'Ship Planning',
    'Ship Complete',
    'Install Start',
    'Install Complete',
    'Complete',
];

export const stageLadderIndex = (stage) =>
    STAGE_LADDER.indexOf((stage || '').toString().trim());
