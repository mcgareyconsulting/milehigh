/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Single source of truth for the size of the app's full-size record modals
 *   (Job Log release hub, DWL submittal review). Bill/Daniel 2026-09-02: the DWL modal
 *   matches the Job Log modal, and "if one changes wholistically, both change" — so the
 *   dimensions live here rather than being restated per component.
 * exports:
 *   MODAL_PANEL_SIZE: inline style object with width/height for the modal panel
 * imported_by: [components/ReleaseHubModal.jsx, components/SubmittalDetailsModal.jsx]
 * invariants:
 *   - Size only. Each modal keeps its own border, radius, and shadow treatment.
 *   - dvh tracks the visual viewport on iPad rotate; vh alone jumps with Safari chrome
 *     and dumps the pane scroll (BUG-14). Keep dvh ahead of vh in the min().
 * updated_by_agent: 2026-09-02T00:00:00Z
 */
export const MODAL_PANEL_SIZE = {
    width: 'min(1380px, 96vw)',
    height: 'min(860px, 94dvh, 94vh)',
};
