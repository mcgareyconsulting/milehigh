/**
 * @milehigh-header
 * schema_version: 1
 * purpose: /m/job-log — the employee's phone Job Log: the Timeline as the vertical day calendar
 *          (DaySchedule), with ONE lane filter — "Shipping Planning" (every crew's releases sitting
 *          in the Ship Planning stage) first, then each installer crew — and the month chips. A
 *          card opens the normal staff ReleaseHubModal, so every release action a PM has at a desk
 *          is available on the phone.
 * exports:
 *   StaffMobileJobLog: Page component under StaffMobileShell.
 * imports_from: [react, ../../hooks/useDaySchedule, ../../components/installSchedule/DaySchedule,
 *                ../../components/ReleaseHubModal, ../../components/sub/SubEmpty]
 * imported_by: [App.jsx]
 * invariants:
 *   - The lane list is the roster (GET /brain/installer-teams) behind the fixed Shipping Planning
 *     entry; the selection persists in localStorage so a PM lands on the lane they last used.
 *   - Month mode drops relative day labels ("Tomorrow"), like the sub portal.
 */
import { useEffect, useMemo, useState } from 'react';
import { useDaySchedule, useReleaseHub } from '../../hooks/useDaySchedule';
import DaySchedule from '../../components/installSchedule/DaySchedule';
import { ReleaseHubModal } from '../../components/ReleaseHubModal';
import SubEmpty from '../../components/sub/SubEmpty';

const SHIP = { key: 'ship', label: 'Shipping Planning', stage: 'Ship Planning' };
const LANE_KEY = 'mobile-joblog-lane';

function monthOptions(today = new Date()) {
    const out = [];
    for (let i = -1; i <= 4; i += 1) {
        const d = new Date(today.getFullYear(), today.getMonth() + i, 1);
        const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
        const label = d.toLocaleDateString('en-US', d.getFullYear() === today.getFullYear() ? { month: 'short' } : { month: 'short', year: '2-digit' });
        out.push({ key, label });
    }
    return out;
}

export default function StaffMobileJobLog() {
    const [lane, setLane] = useState(() => { try { return localStorage.getItem(LANE_KEY) || SHIP.key; } catch { return SHIP.key; } });
    const [month, setMonth] = useState(null);
    const months = useMemo(() => monthOptions(), []);
    useEffect(() => { try { localStorage.setItem(LANE_KEY, lane); } catch { /* ignore */ } }, [lane]);

    const isShip = lane === SHIP.key;
    const { data, loading, error, reload, roster } = useDaySchedule({
        days: 14, pastDays: 14,
        installer: isShip ? null : lane,
        stage: isShip ? SHIP.stage : null,
        month,
    });
    const { hubJob, openRelease, closeHub } = useReleaseHub();

    const laneLabel = isShip ? SHIP.label : lane;
    const nothing = data && !data.past_due.length && data.summary.scheduled === 0;

    return (
        <div className="flex-1 min-h-0 overflow-y-auto flex flex-col">
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
            <div className="sub-months" role="tablist" aria-label="Time window">
                <button type="button" role="tab" aria-selected={month === null} className={month === null ? 'active' : ''} onClick={() => setMonth(null)}>Upcoming</button>
                {months.map((m) => (
                    <button key={m.key} type="button" role="tab" aria-selected={month === m.key} className={month === m.key ? 'active' : ''} onClick={() => setMonth(m.key)}>{m.label}</button>
                ))}
            </div>

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

            <ReleaseHubModal isOpen={!!hubJob} job={hubJob} releaseId={hubJob?.id} viewerUrl={hubJob?.viewer_url}
                initialTab="details" onClose={closeHub} onJobUpdate={reload} />
        </div>
    );
}
