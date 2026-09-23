/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The Splices tab of the sub release page — the release family (original + splices)
 *          as rows: number, scope, crew, stage, start date, install hours. Rows on the sub's own
 *          crew navigate to that release's page; rows on another crew are listed for context but
 *          not tappable (the sub cannot open a release that is not theirs).
 * exports:
 *   SubReleaseSplices: ({ releaseId, onCount })
 * imports_from: [react, react-router-dom, ../../services/subPortalApi]
 * imported_by: [pages/SubcontractorRelease.jsx]
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getSubSplices } from '../../services/subPortalApi';

const fmtDate = (iso) => {
    if (!iso) return null;
    const d = new Date(`${iso}T00:00:00`);
    return isNaN(d) ? iso : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

export default function SubReleaseSplices({ releaseId, onCount }) {
    const navigate = useNavigate();
    const [rows, setRows] = useState(null);
    const [error, setError] = useState(null);

    const load = useCallback(async () => {
        try {
            const family = await getSubSplices(releaseId);
            setRows(family);
            setError(null);
            onCount?.(Math.max(0, family.filter((r) => !r.is_parent).length));
        } catch (e) {
            setError(e?.response?.data?.error || 'Could not load splices');
        }
    }, [releaseId, onCount]);
    useEffect(() => { load(); }, [load]);

    const splices = (rows || []).filter((r) => !r.is_parent);
    const parent = (rows || []).find((r) => r.is_parent);

    return (
        <div className="flex-1 min-h-0 overflow-y-auto pb-6">
            {error && <p className="px-4 py-3 text-sm text-red-600">{error}</p>}
            {!rows && !error && <p className="px-4 py-3 text-sm text-ink-3">Loading…</p>}
            {rows && (
                <>
                    {parent && (
                        <section className="sub-section">
                            <h3 className="sub-section-label">Original</h3>
                            <Row r={parent} navigate={navigate} />
                        </section>
                    )}
                    <section className="sub-section">
                        <h3 className="sub-section-label">Splices</h3>
                        {splices.length === 0 && <p className="sub-quiet">This release has no splices.</p>}
                        {splices.map((r) => <Row key={r.id} r={r} navigate={navigate} />)}
                    </section>
                </>
            )}
        </div>
    );
}

function Row({ r, navigate }) {
    const tappable = r.on_crew && !r.is_this;
    return (
        <button type="button" className="sub-splice" disabled={!tappable}
            onClick={() => tappable && navigate(`/sub/releases/${r.id}`)}>
            <span className="min-w-0 flex-1">
                <span className="code">{r.code}{r.is_this ? ' · this' : ''}</span>
                {r.description && <span className="desc block">{r.description}</span>}
                <span className="meta">
                    <span>{r.installer || 'Unassigned'}{!r.on_crew ? ' (other crew)' : ''}</span>
                    {r.stage && <span>{r.stage}</span>}
                    {r.start_install && <span>{fmtDate(r.start_install)}</span>}
                    {r.install_hrs != null && <span>{r.install_hrs} h</span>}
                </span>
            </span>
            {tappable && <span className="text-ink-3" aria-hidden="true">›</span>}
        </button>
    );
}
