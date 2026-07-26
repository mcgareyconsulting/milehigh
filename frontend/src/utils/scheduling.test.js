import { describe, it, expect } from 'vitest';
import { installDays, installCompleteDate, shipEstimate, businessDaysBetween } from './scheduling';

// 2026-05-25 is a Monday; May 26 Tue, 27 Wed, 28 Thu, 29 Fri; Jun 1 Mon.
describe('installDays', () => {
    it('scales by crew capacity (num_guys * 8)', () => {
        expect(installDays(24, 2)).toBe(2);   // 24 / 16 -> ceil 2
        expect(installDays(24, 3)).toBe(1);   // 24 / 24 -> 1
        expect(installDays(24, 1)).toBe(3);   // 24 / 8  -> 3
        expect(installDays(24, 4)).toBe(1);   // plateau
    });
    it('defaults missing crew to 2 and floors positive hours at 1 day', () => {
        expect(installDays(4, null)).toBe(1);   // 4 / 16 -> ceil 1
        expect(installDays(0.5, 2)).toBe(1);
    });
    it('returns 0 for non-positive/invalid hours', () => {
        expect(installDays(0, 2)).toBe(0);
        expect(installDays(null, 2)).toBe(0);
        expect(installDays(-5, 2)).toBe(0);
    });
});

describe('installCompleteDate', () => {
    it('matches the backend for the 190-398 case', () => {
        expect(installCompleteDate('2026-05-26', 24, 2)).toBe('2026-05-27');
        expect(installCompleteDate('2026-05-26', 24, 3)).toBe('2026-05-26'); // sooner
        expect(installCompleteDate('2026-05-26', 24, 1)).toBe('2026-05-28'); // later
    });
    it('skips weekends', () => {
        // Fri May 29 + 2-day install -> completes Mon Jun 1 (Sat/Sun skipped).
        expect(installCompleteDate('2026-05-29', 24, 2)).toBe('2026-06-01');
    });
    it('is a same-day install when there are no positive hours', () => {
        expect(installCompleteDate('2026-05-26', 0, 2)).toBe('2026-05-26');
    });
    it('returns empty string with no start date', () => {
        expect(installCompleteDate('', 24, 2)).toBe('');
    });
});

describe('shipEstimate', () => {
    it('is one business day before start', () => {
        expect(shipEstimate('2026-05-26')).toBe('2026-05-25'); // Tue -> Mon
        expect(shipEstimate('2026-05-25')).toBe('2026-05-22'); // Mon -> Fri (skip weekend)
    });
});

describe('businessDaysBetween', () => {
    it('counts signed business days, skipping weekends', () => {
        expect(businessDaysBetween('2026-05-26', '2026-05-28')).toBe(2);
        expect(businessDaysBetween('2026-05-28', '2026-05-26')).toBe(-2);
        expect(businessDaysBetween('2026-05-26', '2026-06-01')).toBe(4); // Tue -> next Mon across weekend
        expect(businessDaysBetween('2026-05-26', '2026-05-26')).toBe(0);
    });
});
