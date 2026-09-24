/**
 * @milehigh-header
 * schema_version: 2
 * purpose: A release as a PAGE on a phone (docs/design/release-mobile-recommendations.md), shared
 *          by the subcontractor portal (/sub/releases/:id) and the employee phone shell
 *          (/m/releases/:id). Two-row sticky header (back · number chip · stage chip · ⋯ ; job name
 *          / scope · PM), a sticky tab strip (Details · Activity · Attachments) and one scrolling
 *          tab body. All data goes through a components/mobile/releaseApi adapter, so the same page
 *          reads the sub-scoped routes for a sub and the staff routes for an employee.
 * exports:
 *   MobileReleasePage: ({ api, homePath }) — homePath is where Back lands without history.
 * imports_from: [react, react-router-dom, ../sub/*]
 * imported_by: [pages/SubcontractorRelease.jsx, pages/mobile/StaffMobileRelease.jsx]
 * invariants:
 *   - The stage chip opens the picker; the options come from the adapter (server SUB_STAGES for a
 *     sub, the full progression for staff) and the change runs UpdateStageCommand server-side.
 *   - The department photo gate (T13) is honoured: a 422 photo_required answer opens the gate
 *     sheet, which either uploads a photo tagged with the gate stage or sends a written reason,
 *     and the same stage change is retried.
 *   - The ⋯ menu holds Copy link and Close only.
 *   - Header and tab strip are fixed-height flex siblings (flex-shrink 0); only the tab body scrolls.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import SubReleaseDetails from '../sub/SubReleaseDetails';
import SubReleaseActivity from '../sub/SubReleaseActivity';
import SubReleaseAttachments from '../sub/SubReleaseAttachments';
import SubStageSheet from '../sub/SubStageSheet';
import SubStageGateSheet from '../sub/SubStageGateSheet';

const TABS = [
    { key: 'details', label: 'Details' },
    { key: 'activity', label: 'Activity' },
    { key: 'attachments', label: 'Attachments' },
];

const ICONS = {
    back: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>,
    more: <svg viewBox="0 0 24 24" fill="currentColor" stroke="none" aria-hidden="true"><circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" /></svg>,
};

export default function MobileReleasePage({ api, homePath }) {
    const { id } = useParams();
    const releaseId = Number(id);
    const navigate = useNavigate();
    const [params, setParams] = useSearchParams();
    const tab = TABS.some((t) => t.key === params.get('tab')) ? params.get('tab') : 'details';
    const setTab = (k) => setParams(k === 'details' ? {} : { tab: k }, { replace: true });

    const [rel, setRel] = useState(null);
    const [error, setError] = useState(null);
    const [todos, setTodos] = useState([]);
    const [menuOpen, setMenuOpen] = useState(false);
    const [counts, setCounts] = useState({});
    const [stageOptions, setStageOptions] = useState([]);
    const [stageOpen, setStageOpen] = useState(false);
    const [stageBusy, setStageBusy] = useState(false);
    const [stageError, setStageError] = useState(null);
    const [gate, setGate] = useState(null); // { gateStage, requestedStage } while the photo gate is owed

    const load = useCallback(async () => {
        setError(null);
        try {
            const [r, t] = await Promise.all([api.getRelease(releaseId), api.listTodosForRelease(releaseId).catch(() => [])]);
            setRel(r.release);
            setStageOptions(r.stage_options || []);
            setTodos(t);
        } catch (e) {
            setError(e?.response?.status === 404 ? 'This release is not on your crew.' : 'Could not load the release.');
        }
    }, [releaseId, api]);
    useEffect(() => { load(); }, [load]);

    const goBack = () => {
        if (window.history.length > 1) navigate(-1);
        else navigate(homePath);
    };
    const copyLink = async () => {
        setMenuOpen(false);
        try { await navigator.clipboard.writeText(window.location.href); } catch { /* clipboard blocked */ }
    };

    const code = rel ? `${rel['Job #']}-${rel['Release #']}` : '';
    const meta = useMemo(() => {
        if (!rel) return '';
        // Crew leads the line: a company login sees several crews' releases in one list,
        // so the header says which crew this one belongs to.
        return [rel.installer, rel.Description, rel.PM ? `PM ${rel.PM}` : null, rel.BY ? `Detailed by ${rel.BY}` : null]
            .filter(Boolean).join(' · ');
    }, [rel]);
    const reportCount = useCallback((key, n) => setCounts((c) => (c[key] === n ? c : { ...c, [key]: n })), []);
    const closeStage = useCallback(() => setStageOpen(false), []);
    const pickStage = async (stage, opts = {}) => {
        setStageBusy(true);
        setStageError(null);
        try {
            await api.setStage(releaseId, rel, stage, opts);
            setStageOpen(false);
            setGate(null);
            await load();
        } catch (e) {
            const data = e?.response?.data;
            if (e?.response?.status === 422 && data?.code === 'photo_required') {
                setStageOpen(false);
                setGate({ gateStage: data.stage, requestedStage: data.requested_stage || stage });
            } else {
                setStageError(data?.error || 'Could not change the stage');
                throw e;
            }
        } finally {
            setStageBusy(false);
        }
    };
    const closeGate = useCallback(() => setGate(null), []);

    return (
        <div className="flex-1 min-h-0 flex flex-col">
            <header className="sub-rel-head">
                <div className="sub-rel-row1">
                    <button type="button" className="sub-iconbtn" aria-label="Back" onClick={goBack}>{ICONS.back}</button>
                    {rel && <span className="sub-chip num">{code}</span>}
                    {rel?.Stage && (
                        <button type="button" className="sub-chip stage tappable" onClick={() => setStageOpen(true)} aria-label={`Stage: ${rel.Stage}. Change stage`}>
                            {rel.Stage}
                        </button>
                    )}
                    <span className="flex-1" />
                    <div className="relative">
                        <button type="button" className="sub-iconbtn" aria-label="More" aria-expanded={menuOpen} onClick={() => setMenuOpen((o) => !o)}>{ICONS.more}</button>
                        {menuOpen && (
                            <>
                                <div className="fixed inset-0 z-30" onClick={() => setMenuOpen(false)} aria-hidden="true" />
                                <div className="absolute right-1 mt-1 w-44 rounded-xl border border-hairline bg-surface shadow-lg overflow-hidden z-40">
                                    <button type="button" onClick={copyLink} className="w-full text-left px-4 py-3 text-[15px] font-bold text-ink active:bg-surface-2">Copy link</button>
                                    <button type="button" onClick={goBack} className="w-full text-left px-4 py-3 text-[15px] font-bold text-ink border-t border-hairline active:bg-surface-2">Close</button>
                                </div>
                            </>
                        )}
                    </div>
                </div>
                <div className="sub-rel-row2">
                    <div className="name">{rel?.Job || (error ? 'Release' : '…')}</div>
                    {meta && <div className="meta">{meta}</div>}
                </div>
            </header>

            {error && <p className="px-4 py-6 text-center text-sm text-red-600">{error}</p>}
            {stageError && <p className="px-4 py-2 text-sm text-red-600">{stageError}</p>}

            {rel && (
                <>
                    <nav className="sub-tabstrip" aria-label="Release sections">
                        {TABS.map((t) => (
                            <button key={t.key} type="button" className={tab === t.key ? 'active' : ''} onClick={() => setTab(t.key)}>
                                {t.label}
                                {counts[t.key] > 0 && <span className="count">{counts[t.key]}</span>}
                            </button>
                        ))}
                    </nav>
                    <div className="flex-1 min-h-0 flex flex-col">
                        {tab === 'details' && <SubReleaseDetails rel={rel} todos={todos} />}
                        {tab === 'activity' && (
                            <SubReleaseActivity releaseId={releaseId} rel={rel} api={api} onCount={(n) => reportCount('activity', n)} />
                        )}
                        {tab === 'attachments' && (
                            <SubReleaseAttachments releaseId={releaseId} code={code} api={api} onCount={(n) => reportCount('attachments', n)} />
                        )}
                    </div>
                </>
            )}

            {stageOpen && rel && (
                <SubStageSheet current={rel.Stage} options={stageOptions} busy={stageBusy}
                    onPick={(stage) => pickStage(stage).catch(() => {})} onClose={closeStage} />
            )}
            {gate && (
                <SubStageGateSheet
                    gateStage={gate.gateStage}
                    requestedStage={gate.requestedStage}
                    releaseId={releaseId}
                    api={api}
                    onSatisfied={({ gateExceptionNote } = {}) => pickStage(gate.requestedStage, { gateExceptionNote })}
                    onClose={closeGate}
                />
            )}
        </div>
    );
}
