/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The installer picker for the day calendar — one dropdown listing every installer, one
 *   selectable at a time. Shared by the Installation Schedule page and the Job Log's phone Timeline
 *   so the two cannot offer different lists.
 * exports:
 *   CrewSelect: ({crews, value, onChange, className}) -> a native single-select.
 * imports_from: []
 * imported_by: [../../pages/InstallSchedule.jsx, ../../pages/PMBoardContent.jsx]
 * invariants:
 *   - A NATIVE <select>, deliberately. It is single-select by construction (no `multiple`), it
 *     collapses a roster of any size to one line, and on iOS it opens the system wheel — a far better
 *     target than a row of 28px chips, which is what this replaced.
 *   - `crews` is the full roster (see utils/crewColor.crewFilterOptions), NOT the crews present in the
 *     current response. Listing only crews with work in the window means the list shrinks to one
 *     entry as soon as you pick something, stranding you on that crew.
 *   - The empty-string option is "All installers" — the unfiltered state — and is reported as null so
 *     callers never have to special-case ''.
 */
export default function CrewSelect({ crews = [], value = null, onChange, className = '' }) {
    return (
        <select
            value={value || ''}
            onChange={(e) => onChange(e.target.value || null)}
            aria-label="Filter by installer"
            className={`px-2.5 py-1.5 text-sm rounded-lg bg-surface text-ink border border-hairline font-medium focus:outline-none focus:ring-2 focus:ring-accent-500 min-w-0 ${className}`}
        >
            <option value="">All installers</option>
            {crews.map((crew) => (
                <option key={crew} value={crew}>{crew}</option>
            ))}
        </select>
    );
}
