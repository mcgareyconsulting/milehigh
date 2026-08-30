// BUG-14: rotating an iPad crosses the Job Log / Archive breakpoint buckets
// and unmounts the cards tree or the table tree. These snapshots are the
// diagnosis — if a rotate pair returns viewSwapsOnRotate true, any modal
// owned by the unmounted tree is gone.
import { describe, it, expect } from 'vitest';
import { BREAKPOINTS } from '../hooks/useBreakpoint';
import { resolveJobLogView, resolveAutoCardsBelowXl, viewSwapsOnRotate } from './viewportView';

function buckets(width) {
    return {
        isMobile: width < BREAKPOINTS.md,
        isTablet: width >= BREAKPOINTS.md && width < BREAKPOINTS.xl,
        isBelowLg: width < BREAKPOINTS.lg,
        isDesktop: width >= BREAKPOINTS.xl,
        isTabletOrSmaller: width < BREAKPOINTS.xl,
    };
}

function jobLogAt(width, viewMode = 'auto') {
    return resolveJobLogView({ ...buckets(width), viewMode });
}

describe('resolveJobLogView — iPad rotation remounts (BUG-14)', () => {
    it('forces cards in portrait on a 10.2" iPad (768) even when Table is picked', () => {
        expect(jobLogAt(768, 'table')).toBe('cards');
        expect(jobLogAt(768, 'auto')).toBe('cards');
    });

    it('honors Table once landscape hits 1024', () => {
        expect(jobLogAt(1024, 'table')).toBe('table');
    });

    it('portrait Table-pick → landscape Table-pick unmounts cards for the table', () => {
        const portrait = jobLogAt(768, 'table');
        const landscape = jobLogAt(1024, 'table');
        expect(viewSwapsOnRotate(portrait, landscape)).toBe(true);
    });

    it('Auto on 11" iPad (834 → 1194) stays on cards — no remount from the view swap', () => {
        expect(viewSwapsOnRotate(jobLogAt(834, 'auto'), jobLogAt(1194, 'auto'))).toBe(false);
    });

    it('Auto on 12.9" iPad Pro (1024 → 1366) swaps cards → table', () => {
        expect(jobLogAt(1024, 'auto')).toBe('cards');
        expect(jobLogAt(1366, 'auto')).toBe('table');
        expect(viewSwapsOnRotate(jobLogAt(1024, 'auto'), jobLogAt(1366, 'auto'))).toBe(true);
    });
});

describe('resolveAutoCardsBelowXl — Archive / DWL', () => {
    it('Auto swaps cards → table when a 12.9" iPad rotates to desktop width', () => {
        const portrait = resolveAutoCardsBelowXl('auto', buckets(1024).isTabletOrSmaller);
        const landscape = resolveAutoCardsBelowXl('auto', buckets(1366).isTabletOrSmaller);
        expect(portrait).toBe('cards');
        expect(landscape).toBe('table');
        expect(viewSwapsOnRotate(portrait, landscape)).toBe(true);
    });

    it('an explicit Cards pick does not swap on rotate', () => {
        const portrait = resolveAutoCardsBelowXl('cards', buckets(1024).isTabletOrSmaller);
        const landscape = resolveAutoCardsBelowXl('cards', buckets(1366).isTabletOrSmaller);
        expect(viewSwapsOnRotate(portrait, landscape)).toBe(false);
    });
});
