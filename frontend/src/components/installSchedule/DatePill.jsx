/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The coloured Hard/ASAP/Projected/Done chip both Installation Schedule views stamp on a card.
 * exports:
 *   DatePill: ({kind}) -> the chip for a card's date_kind.
 * imports_from: [../../utils/installScheduleFormat]
 * imported_by: [./DaySchedule.jsx, ../../pages/InstallSchedule.jsx]
 * invariants:
 *   - An unrecognised kind renders as `projected` (the neutral, non-committal label) rather than
 *     blank — a card with no pill reads as "no date set", which is a stronger claim than we can make.
 */
import { DATE_KIND } from '../../utils/installScheduleFormat';

export function DatePill({ kind }) {
    const meta = DATE_KIND[kind] || DATE_KIND.projected;
    return <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${meta.cls}`}>{meta.label}</span>;
}

export default DatePill;
