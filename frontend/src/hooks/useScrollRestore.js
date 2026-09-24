/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Keep a scroll container's position across a push/back navigation — the sub portal's
 *   Job Log pushes /sub/releases/:id and the back arrow must land where the reader left off
 *   (release-mobile-recommendations.md §1). React Router remounts the page on back, so the
 *   position is stashed in sessionStorage under a caller-chosen key and restored once the page
 *   reports it has data to scroll.
 * exports:
 *   useScrollRestore: (key, ready) -> ref to attach to the scroll container.
 * imports_from: [react]
 * imported_by: [pages/SubcontractorJobLog.jsx, pages/mobile/StaffMobileJobLog.jsx]
 * invariants:
 *   - Saves on every scroll (cheap: one sessionStorage write per scroll end via rAF) and on unmount.
 *   - Restores exactly once per mount, only after `ready` is true, so an empty loading shell is
 *     never scrolled and then jumped.
 *   - All storage access is try/catch — private mode or blocked storage degrades to no restore.
 */
import { useEffect, useRef } from 'react';

export function useScrollRestore(key, ready) {
    const ref = useRef(null);
    const restored = useRef(false);

    useEffect(() => {
        const el = ref.current;
        if (!el) return undefined;
        let frame = null;
        const save = () => {
            if (frame != null) return;
            frame = requestAnimationFrame(() => {
                frame = null;
                try { sessionStorage.setItem(`scroll:${key}`, String(el.scrollTop)); } catch { /* ignore */ }
            });
        };
        el.addEventListener('scroll', save, { passive: true });
        return () => {
            el.removeEventListener('scroll', save);
            if (frame != null) cancelAnimationFrame(frame);
            try { sessionStorage.setItem(`scroll:${key}`, String(el.scrollTop)); } catch { /* ignore */ }
        };
    }, [key]);

    useEffect(() => {
        if (!ready || restored.current || !ref.current) return;
        restored.current = true;
        let top = 0;
        try { top = Number(sessionStorage.getItem(`scroll:${key}`)) || 0; } catch { /* ignore */ }
        if (top > 0) requestAnimationFrame(() => { if (ref.current) ref.current.scrollTop = top; });
    }, [key, ready]);

    return ref;
}
