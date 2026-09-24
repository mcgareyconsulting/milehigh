/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The one frontend copy of the stage → stage_group (department) map, plus the
 *   department photo-gate rule derived from it. Mirrors app/api/helpers.py STAGE_TO_GROUP /
 *   STAGE_GROUP_ORDER / GATE_ENTRY_STAGE and features/stage/gate.py — the backend is the
 *   authority (it rejects a gated write with 422 photo_required); this copy lets the UI open
 *   the gate dialog BEFORE writing instead of after a bounce.
 * exports:
 *   STAGE_TO_GROUP: stage → 'FABRICATION' | 'PAINT' | 'READY_TO_SHIP' | 'COMPLETE'
 *   STAGE_GROUP_ORDER: the four groups in shop order (index = "how far along")
 *   GATE_ENTRY_STAGE: group → the stage a release enters it through (the photo tag)
 *   stageGroupOf: (stage) → group, or undefined for an unknown stage
 *   gateStageFor: (fromStage, toStage) → the entry stage whose photo is owed, or null
 *   stageGateFromError: (err) → { stage, requestedStage } when a write bounced off the gate, else null
 * imports_from: []
 * imported_by: [hooks/useJobsFilters.js, utils/jobLogPdf.js, components/JobsTableRow.jsx,
 *   components/JobDetailsBody.jsx, components/GanttChart.jsx]
 * invariants:
 *   - Only a FORWARD crossing gates; same group, backward, or unknown on either side → null.
 *   - The owed photo is tagged with the destination department's ENTRY stage, not the stage
 *     picked — Ship Planning → Complete owes the Ship Complete photo, same as the server.
 *   - PAINT is display-identical to READY_TO_SHIP everywhere a group picks a colour; the split
 *     exists for the gate and the department axis, not for the eye.
 */

export const STAGE_TO_GROUP = {
    'Released':         'FABRICATION',
    'Material Ordered': 'FABRICATION',
    'Cut Start':        'FABRICATION',
    'Cut Complete':     'FABRICATION',
    'Fitup Start':      'FABRICATION',
    'Fitup Complete':   'FABRICATION',
    'Weld Start':       'FABRICATION',
    'Weld Complete':    'FABRICATION',
    'Hold':             'FABRICATION',
    'Welded QC':        'PAINT',
    'Paint Start':      'PAINT',
    'Paint QC':         'READY_TO_SHIP',
    'Store at MHMW':    'READY_TO_SHIP',
    'Ship Planning':    'READY_TO_SHIP',
    'Ship Complete':    'COMPLETE',
    'Install Start':    'COMPLETE',
    'Install Complete': 'COMPLETE',
    'Complete':         'COMPLETE',
};

export const STAGE_GROUP_ORDER = ['FABRICATION', 'PAINT', 'READY_TO_SHIP', 'COMPLETE'];

export const GATE_ENTRY_STAGE = {
    PAINT: 'Welded QC',
    READY_TO_SHIP: 'Paint QC',
    COMPLETE: 'Ship Complete',
};

export const stageGroupOf = (stage) => STAGE_TO_GROUP[String(stage ?? '').trim()];

export const gateStageFor = (fromStage, toStage) => {
    const from = stageGroupOf(fromStage);
    const to = stageGroupOf(toStage);
    if (!from || !to || from === to) return null;
    if (STAGE_GROUP_ORDER.indexOf(to) <= STAGE_GROUP_ORDER.indexOf(from)) return null;
    return GATE_ENTRY_STAGE[to] ?? null;
};

/**
 * jobsApi wraps axios errors in a plain Error (message + originalError + statusCode), so the
 * 422 body lives one hop down. Accept a raw axios error too, for callers that skip the wrapper.
 */
export const stageGateFromError = (err) => {
    const data = err?.originalError?.response?.data ?? err?.response?.data;
    if (data?.code !== 'photo_required' || !data?.stage) return null;
    return { stage: data.stage, requestedStage: data.requested_stage ?? data.stage };
};
