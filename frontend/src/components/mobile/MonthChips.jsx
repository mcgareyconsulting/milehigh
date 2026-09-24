/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The phone Job Log's one time control — "Upcoming" (the rolling ±2-week window) plus a
 *          run of calendar months — shared by the sub portal and the employee shell.
 * exports:
 *   MonthChips: ({ month, onChange, months }) — month null = Upcoming; months from monthOptions().
 * imports_from: [react]
 * imported_by: [pages/SubcontractorJobLog.jsx, pages/mobile/StaffMobileJobLog.jsx]
 */
export default function MonthChips({ month, onChange, months }) {
    return (
        <div className="sub-months" role="tablist" aria-label="Time window">
            <button type="button" role="tab" aria-selected={month === null} className={month === null ? 'active' : ''} onClick={() => onChange(null)}>Upcoming</button>
            {months.map((m) => (
                <button key={m.key} type="button" role="tab" aria-selected={month === m.key}
                    className={month === m.key ? 'active' : ''} onClick={() => onChange(m.key)}>
                    {m.label}
                </button>
            ))}
        </div>
    );
}
