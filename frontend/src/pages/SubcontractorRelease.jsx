/**
 * @milehigh-header
 * schema_version: 1
 * purpose: A release as a PAGE for subcontractors on a phone (docs/design/release-mobile-
 *          recommendations.md). Route /sub/releases/:id, pushed from a Job Log card or a to-do.
 *          Two-row sticky header (back · number chip · stage chip · ⋯ ; job name / scope · PM),
 *          a sticky horizontal tab strip, and one scrolling tab body. Tabs a sub gets: Details,
 *          Activity (with the note composer), Attachments (reader + photo / file upload). No
 *          Splices tab: a sub sees the release they are assigned, and Attachments already carries
 *          the family's drawings so a sub on a splice sees the original's PDF pack. Issues and
 *          the Change Log are staff-only by decision (ROADMAP T3 2026-09-07) and not rendered.
 * exports:
 *   SubcontractorRelease: Page component, rendered inside SubcontractorShell's Outlet.
 * imports_from: [react, react-router-dom, ../services/subPortalApi, ../components/sub/*]
 * imported_by: [App.jsx]
 * invariants:
 *   - Every field shown comes from the sub allowlist (GET /brain/subcontractor/releases/:id);
 *     off-crew ids 404 and the page says so rather than guessing.
 *   - The stage chip opens the stage picker; the options come from the server (SUB_STAGES: the
 *     field-side stages only), and the change runs the full UpdateStageCommand cascade there.
 *   - The ⋯ menu holds Copy link and Close only — Procore/Trello links are internal identities.
 *   - Header and tab strip are fixed-height flex siblings (flex-shrink 0); only the tab body scrolls.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { getSubRelease, listSubTodos, setSubStage } from '../services/subPortalApi';
import SubReleaseDetails from '../components/sub/SubReleaseDetails';
import SubReleaseActivity from '../components/sub/SubReleaseActivity';
import SubReleaseAttachments from '../components/sub/SubReleaseAttachments';
import SubStageSheet from '../components/sub/SubStageSheet';

const TABS = [
    { key: 'details', label: 'Details' },
    { key: 'activity', label: 'Activity' },
    { key: 'attachments', label: 'Attachments' },
];

const ICONS = {
    back: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>,
    more: <svg viewBox="0 0 24 24" fill="currentColor" stroke="none" aria-hidden="true"><circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" /></svg>,
};

export default function SubcontractorRelease() {
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

    const load = useCallback(async () => {
        setError(null);
        try {
            const [r, t] = await Promise.all([getSubRelease(releaseId), listSubTodos('all').catch(() => [])]);
            setRel(r.release);
            setStageOptions(r.stage_options || []);
            setTodos(t.filter((x) => x.release_id === releaseId));
        } catch (e) {
            setError(e?.response?.status === 404 ? 'This release is not on your crew.' : 'Could not load the release.');
        }
    }, [releaseId]);
    useEffect(() => { load(); }, [load]);

    const goBack = () => {
        if (window.history.length > 1) navigate(-1);
        else navigate('/sub/job-log');
    };
    const copyLink = async () => {
        setMenuOpen(false);
        try { await navigator.clipboard.writeText(window.location.href); } catch { /* clipboard blocked */ }
    };

    const code = rel ? `${rel['Job #']}-${rel['Release #']}` : '';
    const meta = useMemo(() => {
        if (!rel) return '';
        return [rel.Description, rel.PM ? `PM ${rel.PM}` : null, rel.BY ? `Detailed by ${rel.BY}` : null]
            .filter(Boolean).join(' · ');
    }, [rel]);
    const reportCount = useCallback((key, n) => setCounts((c) => (c[key] === n ? c : { ...c, [key]: n })), []);
    const closeStage = useCallback(() => setStageOpen(false), []);
    const pickStage = async (stage) => {
        setStageBusy(true);
        setStageError(null);
        try {
            await setSubStage(releaseId, stage);
            setStageOpen(false);
            await load();
        } catch (e) {
            setStageError(e?.response?.data?.error || 'Could not change the stage');
        } finally {
            setStageBusy(false);
        }
    };

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
                            <SubReleaseActivity releaseId={releaseId} onCount={(n) => reportCount('activity', n)} />
                        )}
                        {tab === 'attachments' && (
                            <SubReleaseAttachments releaseId={releaseId} code={code} onCount={(n) => reportCount('attachments', n)} />
                        )}
                    </div>
                </>
            )}

            {stageOpen && rel && (
                <SubStageSheet current={rel.Stage} options={stageOptions} busy={stageBusy}
                    onPick={pickStage} onClose={closeStage} />
            )}
        </div>
    );
}
