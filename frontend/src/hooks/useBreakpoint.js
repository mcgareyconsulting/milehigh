/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Reactive viewport breakpoint hook mirroring Tailwind's screens config (sm/md/lg/xl/2xl/3xl) for components that need to branch on width.
 * exports:
 *   useBreakpoint: Returns { width, isMobile, isTablet, isDesktop, is3xl } reactive to window resize.
 *   useIsTabletOrSmaller: Boolean alias — true at iPad-sized screens and below (< xl, i.e. < 1280px).
 * imports_from: [react]
 * imported_by: [frontend/src/components/AppShell.jsx, frontend/src/pages/JobLog.jsx, frontend/src/pages/Archive.jsx, frontend/src/pages/DraftingWorkLoad.jsx, frontend/src/components/JobLogCard.jsx]
 * invariants:
 *   - SSR-safe: defaults to desktop (1440px) when window is undefined.
 *   - Breakpoint thresholds match tailwind.config.js exactly; keep them in sync.
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

export function useBreakpoint() {
    const [width, setWidth] = useState(getWidth);

    useEffect(() => {
        if (typeof window === 'undefined') return undefined;
        const handler = () => setWidth(window.innerWidth);
        window.addEventListener('resize', handler);
        return () => window.removeEventListener('resize', handler);
    }, []);

    return {
        width,
        isMobile: width < BREAKPOINTS.md,                        // < 768px (phone)
        isTablet: width >= BREAKPOINTS.md && width < BREAKPOINTS.xl, // 768–1279 (iPad-ish)
        isDesktop: width >= BREAKPOINTS.xl,                      // >= 1280
        is3xl: width >= BREAKPOINTS['3xl'],                      // >= 1920 (27"+ / TV)
    };
}

// Auto-card threshold: anything iPad-sized or smaller.
export function useIsTabletOrSmaller() {
    const { width } = useBreakpoint();
    return width < BREAKPOINTS.xl;
}
