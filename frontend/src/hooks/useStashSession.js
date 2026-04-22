/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Encapsulate the Thursday review-meeting stash session — fetch active session, queue edits, preview, apply, and discard.
 * exports:
 *   useStashSession: Hook returning { activeSession, changesByKey, viewMode, setViewMode, ... handlers }
 *   stashKey: Helper to build the (job, release, field) lookup key used by callers
 * imports_from: [react, ../services/jobsApi]
 * imported_by: [../pages/JobLog.jsx, ../components/JobsTableRow.jsx, ../components/StashPreviewModal.jsx]
 * invariants:
 *   - At most one active session visible at a time (server enforces via partial unique index)
 *   - viewMode persisted in localStorage under 'jl_stashViewMode' ('print' | 'pending', default 'print')
 *   - stash() upserts locally in changesByKey so the UI reflects queued values without refetch
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { jobsApi } from '../services/jobsApi';

const STORAGE_KEY = 'jl_stashViewMode';

export function stashKey(job, release, field) {
    return `${job}-${release}-${field}`;
}

function indexChanges(changes = []) {
    const map = {};
    for (const c of changes) {
        map[stashKey(c.job, c.release, c.field)] = c;
    }
    return map;
}

export function useStashSession({ enabled = true } = {}) {
    const [activeSession, setActiveSession] = useState(null);
    const [changesByKey, setChangesByKey] = useState({});
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const [viewMode, setViewModeState] = useState(() => {
        try {
            return window.localStorage.getItem(STORAGE_KEY) || 'print';
        } catch {
            return 'print';
        }
    });

    const setViewMode = useCallback((mode) => {
        setViewModeState(mode);
        try {
            window.localStorage.setItem(STORAGE_KEY, mode);
        } catch {
            // ignore quota / access errors
        }
    }, []);

    const hasFetchedRef = useRef(false);

    const refresh = useCallback(async () => {
        if (!enabled) return;
        setLoading(true);
        setError(null);
        try {
            const data = await jobsApi.getActiveStashSession();
            if (data && data.session) {
                setActiveSession({
                    id: data.session.id,
                    started_by_id: data.session.started_by_id,
                    status: data.session.status,
                    started_at: data.session.started_at,
                    ended_at: data.session.ended_at,
                });
                setChangesByKey(indexChanges(data.session.changes || []));
            } else {
                setActiveSession(null);
                setChangesByKey({});
            }
        } catch (err) {
            console.error('[stash] failed to fetch active session', err);
            setError(err.message || 'Failed to fetch stash session');
        } finally {
            setLoading(false);
        }
    }, [enabled]);

    useEffect(() => {
        if (!enabled) return;
        if (hasFetchedRef.current) return;
        hasFetchedRef.current = true;
        refresh();
    }, [enabled, refresh]);

    const start = useCallback(async () => {
        try {
            const data = await jobsApi.startStashSession();
            setActiveSession(data.session);
            setChangesByKey({});
            return data.session;
        } catch (err) {
            console.error('[stash] start failed', err);
            throw err;
        }
    }, []);

    const stash = useCallback(async (job, release, field, newValue) => {
        if (!activeSession) throw new Error('No active stash session');
        const data = await jobsApi.stashChange(activeSession.id, {
            job, release, field, newValue,
        });
        const change = data.change;
        setChangesByKey((prev) => ({
            ...prev,
            [stashKey(change.job, change.release, change.field)]: change,
        }));
        return change;
    }, [activeSession]);

    const remove = useCallback(async (changeId) => {
        if (!activeSession) return;
        await jobsApi.removeStashedChange(activeSession.id, changeId);
        setChangesByKey((prev) => {
            const next = { ...prev };
            for (const k of Object.keys(next)) {
                if (next[k].id === changeId) delete next[k];
            }
            return next;
        });
    }, [activeSession]);

    const preview = useCallback(async () => {
        if (!activeSession) throw new Error('No active stash session');
        return await jobsApi.getStashPreview(activeSession.id);
    }, [activeSession]);

    const apply = useCallback(async () => {
        if (!activeSession) throw new Error('No active stash session');
        const data = await jobsApi.applyStashSession(activeSession.id);
        setActiveSession(null);
        setChangesByKey({});
        return data;
    }, [activeSession]);

    const discard = useCallback(async () => {
        if (!activeSession) return;
        await jobsApi.discardStashSession(activeSession.id);
        setActiveSession(null);
        setChangesByKey({});
    }, [activeSession]);

    return {
        activeSession,
        changesByKey,
        changeCount: Object.keys(changesByKey).length,
        loading,
        error,
        viewMode,
        setViewMode,
        refresh,
        start,
        stash,
        remove,
        preview,
        apply,
        discard,
    };
}
