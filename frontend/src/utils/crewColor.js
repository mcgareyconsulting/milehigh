/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Map installer crews to their palette colour so a crew reads the same on every surface.
 * exports:
 *   orderedCrews: (roster, extraCrews) -> string[] — roster order, then off-roster names as given.
 *   buildCrewColors: (roster, extraCrews) -> Map<crew, hex>
 *   crewFilterOptions: (roster, seenCrews) -> string[] for the installer picker.
 *   UNASSIGNED_CREW: the backend's bucket name for releases with no installer.
 * imports_from: [../constants/installerPalette]
 * imported_by: [../components/installSchedule/DaySchedule.jsx]
 * invariants:
 *   - Colour is keyed to the crew's index in the /brain/installer-teams ROSTER, not its position in
 *     whatever data the current view happens to hold — otherwise filtering the view would recolour
 *     the crews. Off-roster crews present in the data are appended in the order given, so no crew
 *     ever renders colourless.
 *   - This mirrors the lane-colour rule in GanttChart.jsx (`lanesMeta`, ~line 804), which keeps its
 *     own inline copy because its version also interleaves the two shipping lanes. Change one, change
 *     the other: a crew showing blue on the Timeline and green here is the bug this comment exists
 *     to prevent.
 *   - UNASSIGNED never takes a palette colour; it is a gap to fill, not a crew, and every view marks
 *     it amber. Callers handle that case before consulting the map.
 *   - THE PICKER LISTS EVERY INSTALLER, not just the ones with work in the current window, and it is
 *     built from the ROSTER rather than from the response. Building it from the response is a trap:
 *     the payload is filtered, so choosing a crew narrows `summary.crews` to that one crew and the
 *     dropdown collapses to a single option — you could no longer switch to a different installer
 *     without clearing the filter first. Off-roster names seen in the data are unioned in so nobody
 *     who actually has installs is unreachable, and Unassigned sorts last because it is a gap to
 *     fill rather than a person.
 */
import { INSTALLER_PALETTE } from '../constants/installerPalette';

export const UNASSIGNED_CREW = 'Unassigned';

export function orderedCrews(roster = [], extraCrews = []) {
    const ordered = [...roster];
    const seen = new Set(ordered);
    extraCrews.forEach((crew) => {
        if (crew && crew !== UNASSIGNED_CREW && !seen.has(crew)) {
            seen.add(crew);
            ordered.push(crew);
        }
    });
    return ordered;
}

export function buildCrewColors(roster = [], extraCrews = []) {
    const colors = new Map();
    orderedCrews(roster, extraCrews).forEach(
        (crew, i) => colors.set(crew, INSTALLER_PALETTE[i % INSTALLER_PALETTE.length]),
    );
    return colors;
}

export function crewFilterOptions(roster = [], seenCrews = []) {
    const named = orderedCrews(roster, seenCrews);
    // Offer the gap bucket only once something has actually landed in it.
    return seenCrews.includes(UNASSIGNED_CREW) ? [...named, UNASSIGNED_CREW] : named;
}
