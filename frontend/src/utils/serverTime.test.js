import { describe, it, expect } from 'vitest';
import { formatMountain, parseServerTime } from './serverTime.js';

describe('parseServerTime', () => {
    it('treats a naive ISO string as UTC', () => {
        expect(parseServerTime('2026-09-15T20:30:45').toISOString()).toBe('2026-09-15T20:30:45.000Z');
    });

    it('accepts Python microsecond precision', () => {
        expect(parseServerTime('2026-09-15T20:30:45.123456').toISOString()).toBe('2026-09-15T20:30:45.123Z');
    });

    it('leaves strings that already carry a zone alone', () => {
        expect(parseServerTime('2026-09-15T20:30:45Z').toISOString()).toBe('2026-09-15T20:30:45.000Z');
        expect(parseServerTime('2026-09-15T14:30:45-06:00').toISOString()).toBe('2026-09-15T20:30:45.000Z');
        expect(parseServerTime('2026-09-15T20:30:45+00:00').toISOString()).toBe('2026-09-15T20:30:45.000Z');
    });

    it('returns null for empty or garbage input', () => {
        expect(parseServerTime(null)).toBeNull();
        expect(parseServerTime('')).toBeNull();
        expect(parseServerTime('not a date')).toBeNull();
    });
});

describe('formatMountain', () => {
    it('shows naive UTC in Mountain Daylight Time (UTC-6)', () => {
        expect(formatMountain('2026-09-15T20:30:45')).toBe('Sep 15, 2:30 PM');
    });

    it('shows naive UTC in Mountain Standard Time (UTC-7)', () => {
        expect(formatMountain('2026-01-15T20:30:00')).toBe('Jan 15, 1:30 PM');
    });

    it('rolls the day back when UTC has already crossed midnight', () => {
        expect(formatMountain('2026-09-16T03:15:00')).toBe('Sep 15, 9:15 PM');
    });

    it('is empty for missing input', () => {
        expect(formatMountain(null)).toBe('');
    });
});
