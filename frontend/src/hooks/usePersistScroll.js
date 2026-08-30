/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Keep an overflow container's scrollTop across remounts and iOS
 *   Safari orientation resets (BUG-14). The store ref must live on a parent
 *   that survives the cards/table swap; the element itself may not.
 * exports:
 *   usePersistScroll: Returns { ref, onScroll } to put on the scroller.
 * imports_from: [react]
 * imported_by: [frontend/src/pages/JobLogContent.jsx, frontend/src/components/JobLogCardGrid.jsx,
 *   frontend/src/components/ReleaseHubModal.jsx, frontend/src/pages/Archive.jsx,
 *   frontend/src/pages/DraftingWorkLoad.jsx]
 */

import { useCallback, useEffect, useRef } from 'react';

function applyScroll(el, y) {
    if (!el || !(y > 0)) return;
    if (Math.abs(el.scrollTop - y) > 1) el.scrollTop = y;
}

export function usePersistScroll(storeRef) {
    const elRef = useRef(null);
    const timersRef = useRef([]);

    const restore = useCallback(() => {
        const y = storeRef.current;
        const run = () => applyScroll(elRef.current, y);
        timersRef.current.forEach(clearTimeout);
        timersRef.current = [];
        run();
        requestAnimationFrame(run);
        // iOS Safari often resets overflow after the first layout pass.
        timersRef.current.push(setTimeout(run, 50), setTimeout(run, 250));
    }, [storeRef]);

    const ref = useCallback((node) => {
        elRef.current = node;
        if (node) applyScroll(node, storeRef.current);
    }, [storeRef]);

    const onScroll = useCallback((e) => {
        storeRef.current = e.currentTarget.scrollTop;
    }, [storeRef]);

    useEffect(() => {
        window.addEventListener('orientationchange', restore);
        window.addEventListener('resize', restore);
        return () => {
            window.removeEventListener('orientationchange', restore);
            window.removeEventListener('resize', restore);
            timersRef.current.forEach(clearTimeout);
            timersRef.current = [];
        };
    }, [restore]);

    return { ref, onScroll, elRef };
}
