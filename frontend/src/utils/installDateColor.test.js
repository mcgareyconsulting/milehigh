/**
 * BUG-11 lives or dies here. The backend stopped washing hard dates at the ship stages,
 * but three components each carried their own copy of the old `atShippingStage` rule and
 * forced neutral regardless of what the DB said — so the fix was invisible on screen.
 * This is the one copy now.
 */
import { describe, it, expect } from 'vitest';
import {
    COLOR_DUMP_STAGES,
    isInstallStartOrLater,
    classifyInstallDate,
    localTodayYmd,
} from './installDateColor.js';

const hard = (over = {}) => classifyInstallDate({
    stage: 'Ship Planning',
    asap: false,
    noColor: false,
    formulaTF: false,
    installDate: '2026-12-01',
    today: '2026-08-29',
    ...over,
});

describe('the dump zone', () => {
    it('is Install Start and everything after it', () => {
        expect(COLOR_DUMP_STAGES).toEqual(['Install Start', 'Install Complete', 'Complete']);
    });

    it.each(['Install Start', 'Install Complete', 'Complete'])('includes %s', (s) => {
        expect(isInstallStartOrLater(s)).toBe(true);
    });

    it.each(['Ship Planning', 'Ship Complete', 'Paint Complete', 'Store at MHMW'])(
        'excludes %s', (s) => {
            expect(isInstallStartOrLater(s)).toBe(false);
        });
});

describe('hard dates survive the ship stages (BUG-11)', () => {
    it.each(['Ship Planning', 'Ship Complete'])('stays green at %s', (stage) => {
        const c = hard({ stage });
        expect(c.isNoColor).toBe(false);
        expect(c.isHardDate).toBe(true);
    });

    it('still shows an overdue date amber at Ship Planning', () => {
        const c = hard({ stage: 'Ship Planning', installDate: '2026-01-01' });
        expect(c.isHardDatePast).toBe(true);
        expect(c.isNoColor).toBe(false);
    });

    it('keeps ASAP red through the ship stages', () => {
        expect(hard({ stage: 'Ship Planning', asap: true }).isAsap).toBe(true);
        expect(hard({ stage: 'Ship Complete', asap: true }).isAsap).toBe(true);
    });
});

describe('color drops at Install Start or later', () => {
    it.each(['Install Start', 'Install Complete', 'Complete'])('neutral at %s', (stage) => {
        const c = hard({ stage });
        expect(c.isNoColor).toBe(true);
        expect(c.isHardDate).toBe(false);
        expect(c.isHardDatePast).toBe(false);
    });

    it('an overdue date goes neutral too, not amber', () => {
        expect(hard({ stage: 'Install Start', installDate: '2026-01-01' }).isHardDatePast).toBe(false);
    });

    it('a stale ASAP flag cannot repaint the row red', () => {
        expect(hard({ stage: 'Install Start', asap: true }).isAsap).toBe(false);
    });

    it('covers the optimistic window, before the refetch brings back noColor', () => {
        expect(hard({ stage: 'Install Start', noColor: false }).isNoColor).toBe(true);
    });
});

describe('precedence and the rest', () => {
    it('honors the stored noColor flag at any stage', () => {
        expect(hard({ stage: 'Paint Complete', noColor: true }).isNoColor).toBe(true);
    });

    it('treats ASAP as outranking a hard date, matching the backend', () => {
        const c = hard({ stage: 'Paint Complete', asap: true });
        expect(c.isAsap).toBe(true);
        expect(c.isHardDate).toBe(false);
    });

    it('leaves formula rows uncolored', () => {
        const c = hard({ formulaTF: true });
        expect(c.isHardDate).toBe(false);
        expect(c.isNoColor).toBe(false);
    });

    it('is not a hard date without a value', () => {
        expect(hard({ installDate: null }).isHardDate).toBe(false);
    });

    it('reads an ISO timestamp as its calendar day', () => {
        expect(hard({ installDate: '2026-01-01T00:00:00Z' }).isHardDatePast).toBe(true);
    });

    it('builds today from local parts, not UTC', () => {
        expect(localTodayYmd(new Date(2026, 0, 5, 23, 30))).toBe('2026-01-05');
    });
});
