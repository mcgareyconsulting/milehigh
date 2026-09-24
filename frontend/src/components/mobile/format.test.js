import { describe, it, expect } from 'vitest';
import { initialsOf, fmtDay, fmtShort, addDays, monthOptions, timeAgo } from './format';

describe('initialsOf', () => {
    it('takes the first letters of the first two words', () => {
        expect(initialsOf('McGarey Construction')).toBe('MC');
        expect(initialsOf('Acme')).toBe('AC');
        expect(initialsOf('')).toBe('?');
    });
});

describe('date helpers', () => {
    it('formats date-only strings without a UTC off-by-one', () => {
        expect(fmtDay('2026-09-03')).toBe('Thu, Sep 3');
        expect(fmtShort('2026-09-03')).toBe('Sep 3');
        expect(fmtDay(null)).toBeNull();
        expect(fmtDay('garbage')).toBeNull();
    });
    it('adds days on the calendar, not in milliseconds', () => {
        expect(addDays('2026-09-28', 7)).toBe('2026-10-05');
    });
    it('describes recency', () => {
        expect(timeAgo(new Date(Date.now() - 5 * 60000).toISOString())).toBe('5m ago');
        expect(timeAgo('nope')).toBe('');
    });
});

describe('monthOptions', () => {
    it('runs from last month through four months out and flags the current one', () => {
        const opts = monthOptions(new Date(2026, 8, 23)); // Sep 2026
        expect(opts.map((m) => m.key)).toEqual(['2026-08', '2026-09', '2026-10', '2026-11', '2026-12', '2027-01']);
        expect(opts.find((m) => m.isCurrent).key).toBe('2026-09');
        expect(opts[0].label).toBe('Aug');
        expect(opts[5].label).toBe("Jan '27"); // a year boundary gets the year
    });
});
