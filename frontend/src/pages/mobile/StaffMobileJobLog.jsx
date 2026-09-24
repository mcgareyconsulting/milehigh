/**
 * @milehigh-header
 * schema_version: 1
 * purpose: /m/job-log — the employee's phone Job Log: the Timeline as the vertical day calendar
 *          (DaySchedule), with ONE lane filter — "Shipping Planning" (every crew's releases sitting
 *          in the Ship Planning stage) first, then each installer crew — and the month chips. A
 *          card pushes /m/releases/:id — the same phone release page subs get, over staff routes.
 * exports:
 *   StaffMobileJobLog: Page component under StaffMobileShell.
 * imports_from: [react, ../../hooks/useDaySchedule, ../../components/installSchedule/DaySchedule,
 *                ../../components/sub/SubEmpty]
 * imported_by: [App.jsx]
 * invariants:
 *   - The lane list is the roster (GET /brain/installer-teams) behind the fixed Shipping Planning
 *     entry; the selection persists in localStorage so a PM lands on the lane they last used.
 *   - Month mode drops relative day labels ("Tomorrow"), like the sub portal.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDaySchedule } from '../../hooks/useDaySchedule';
import DaySchedule from '../../components/installSchedule/DaySchedule';
import SubEmpty from '../../components/sub/SubEmpty';
import MonthChips from '../../components/mobile/MonthChips';
import { monthOptions } from '../../components/mobile/format';
import { useScrollRestore } from '../../hooks/useScrollRestore';

const SHIP = { key: 'ship', label: 'Shipping Planning', stage: 'Ship Planning' };
const LANE_KEY = 'mobile-joblog-lane';

export default function StaffMobileJobLog() {
    const [lane, setLane] = useState(() => { try { return localStorage.getItem(LANE_KEY) || SHIP.key; } catch { return SHIP.key; } });
    const [month, setMonth] = useState(null);
    const months = useMemo(() => monthOptions(), []);
    useEffect(() => { try { localStorage.setItem(LANE_KEY, lane); } catch { /* ignore */ } }, [lane]);

    const isShip = lane === SHIP.key;
    const navigate = useNavigate();
    const { data, loading, error, roster } = useDaySchedule({
        days: 14, pastDays: 14,
        installer: isShip ? null : lane,
        stage: isShip ? SHIP.stage : null,
        month,
    });
    const openRelease = useCallback((card) => navigate(`/m/releases/${card.release_id}`), [navigate]);

    const laneLabel = isShip ? SHIP.label : lane;
    const scrollRef = useScrollRestore(`staff-job-log:${lane}:${month || 'upcoming'}`, !loading && !!data);
    const nothing = data && !data.past_due.length && data.summary.scheduled === 0;

    return (
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto flex flex-col">
            <div className="sub-page-head">
                <h1>Job Log</h1>
                <div className="sub-ctx">{month ? months.find((m) => m.key === month)?.label : 'next 2 weeks'}</div>
            </div>
            <div className="px-4 pb-2">
                <select value={lane} onChange={(e) => setLane(e.target.value)} aria-label="Lane"
                    className="w-full h-11 px-3 rounded-xl border border-hairline bg-surface text-ink text-[15px] font-bold">
                    <option value={SHIP.key}>{SHIP.label}</option>
                    {roster.map((crew) => <option key={crew} value={crew}>{crew}</option>)}
                </select>
            </div>
            <MonthChips month={month} onChange={setMonth} months={months} />

            {loading && <div className="text-ink-3 text-sm px-4 py-2">Loading timeline…</div>}
            {error && <div className="text-red-600 text-sm px-4 py-2">{error}</div>}
            {!loading && !error && nothing && (
                <SubEmpty icon="calendar" title="Nothing scheduled" body={`No ${laneLabel} installs in this window.`} />
            )}
            {!loading && !error && data && !nothing && (
                <div className="px-4">
                    <DaySchedule data={data} roster={roster} crewFilter={laneLabel} onOpenRelease={openRelease} relativeLabels={!month} />
                </div>
            )}
        </div>
    );
}
