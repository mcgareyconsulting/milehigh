/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Reactive viewport breakpoint hook mirroring Tailwind's screens config (sm/md/lg/xl/2xl/3xl) for components that need to branch on width.
 * exports:
 *   useBreakpoint: Returns { width, isMobile, isTablet, isDesktop, is3xl }. Re-renders only when a
 *     breakpoint bucket changes, not on every resize pixel — keeps drag-resize smooth on heavy pages.
 *   useIsTabletOrSmaller: Boolean alias — true at iPad-sized screens and below (< xl, i.e. < 1280px).
 * imports_from: [react]
 * imported_by: [frontend/src/pages/JobLog.jsx, frontend/src/pages/Archive.jsx, frontend/src/pages/DraftingWorkLoad.jsx]
 * invariants:
 *   - SSR-safe: defaults to desktop (1440px) when window is undefined.
 *   - Breakpoint thresholds match tailwind.config.js exactly; keep them in sync.
 *   - No consumer reads the raw pixel `width`; it is reported as the width at the last bucket change.
 *     If a future consumer needs pixel-precise width, give it its own throttled listener instead of
 *     reverting this hook to per-pixel state (that re-introduces resize jank on the Job Log table).
 */
import { useEffect, useState } from 'react';

// Mirrors tailwind.config.js — Tailwind defaults plus the custom 3xl.
export const BREAKPOINTS = {
    sm: 640,
    md: 768,
    lg: 1024,
    xl: 1280,
    '2xl': 1536,
    '3xl': 1920,
};

const getWidth = () => (typeof window === 'undefined' ? 1440 : window.innerWidth);

function snapshot(width) {
    return {
        width,
        isMobile: width < BREAKPOINTS.md,                            // < 768px (phone)
        isTablet: width >= BREAKPOINTS.md && width < BREAKPOINTS.xl, // 768–1279 (iPad-ish)
        isDesktop: width >= BREAKPOINTS.xl,                          // >= 1280
        is3xl: width >= BREAKPOINTS['3xl'],                          // >= 1920 (27"+ / TV)
    };
}

function sameBuckets(a, b) {
    return (
        a.isMobile === b.isMobile &&
        a.isTablet === b.isTablet &&
        a.isDesktop === b.isDesktop &&
        a.is3xl === b.is3xl
    );
}

export function useBreakpoint() {
    const [bp, setBp] = useState(() => snapshot(getWidth()));

    useEffect(() => {
        if (typeof window === 'undefined') return undefined;
        let frame = null;
        const handler = () => {
            // Coalesce the burst of resize events fired during a drag into one update per frame…
            if (frame != null) return;
            frame = window.requestAnimationFrame(() => {
                frame = null;
                const next = snapshot(window.innerWidth);
                // …and re-render only when a breakpoint bucket actually changed.
                setBp((prev) => (sameBuckets(prev, next) ? prev : next));
            });
        };
        window.addEventListener('resize', handler);
        handler(); // sync in case the width changed between first render and mount
        return () => {
            window.removeEventListener('resize', handler);
            if (frame != null) window.cancelAnimationFrame(frame);
        };
    }, []);

    return bp;
}

// Auto-card threshold: anything iPad-sized or smaller.
export function useIsTabletOrSmaller() {
    return !useBreakpoint().isDesktop;
}
