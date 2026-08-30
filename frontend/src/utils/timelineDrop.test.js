import { describe, it, expect } from 'vitest';
import { columnAtDropX, dateAtDropX } from './timelineDrop';

// A chart of 10 day-columns 100px wide, starting Monday 2026-08-31.
const dayGeom = { colPx: 100, colDays: 1, firstDay: '2026-08-31', totalCols: 10 };
const LANE_LEFT = 200;   // the lane's chart area starts 200px into the viewport

describe('columnAtDropX', () => {
    it('maps a drop to the column it lands in', () => {
        expect(columnAtDropX(200, LANE_LEFT, 100, 10)).toBe(0);
        expect(columnAtDropX(299, LANE_LEFT, 100, 10)).toBe(0);
        expect(columnAtDropX(300, LANE_LEFT, 100, 10)).toBe(1);
        expect(columnAtDropX(450, LANE_LEFT, 100, 10)).toBe(2);
    });

    it('clamps a drop past the right edge to the last column, not off the chart', () => {
        expect(columnAtDropX(99999, LANE_LEFT, 100, 10)).toBe(9);
    });

    it('clamps a drop left of the chart to the first column', () => {
        expect(columnAtDropX(-500, LANE_LEFT, 100, 10)).toBe(0);
    });

    it('handles a lane scrolled so its origin is off-screen left', () => {
        // Scrolled right by 350px: the lane's rect.left is now negative.
        expect(columnAtDropX(200, -350, 100, 10)).toBe(5);
    });

    it('refuses to guess when the geometry is not measured yet', () => {
        expect(columnAtDropX(300, LANE_LEFT, 0, 10)).toBeNull();
        expect(columnAtDropX(300, LANE_LEFT, 100, 0)).toBeNull();
    });
});

describe('dateAtDropX', () => {
    it('returns the date of the column dropped on', () => {
        expect(dateAtDropX(200, LANE_LEFT, dayGeom)).toBe('2026-08-31');
        expect(dateAtDropX(350, LANE_LEFT, dayGeom)).toBe('2026-09-01');
    });

    it('crosses a month boundary correctly', () => {
        // Column 1 = Sep 1. firstDay is Aug 31, a 31-day month.
        expect(dateAtDropX(301, LANE_LEFT, dayGeom)).toBe('2026-09-01');
    });

    it('keeps a weekend date exactly where it was dropped', () => {
        // firstDay Mon Aug 31 → col 5 = Sat Sep 5. No business-day nudge.
        expect(dateAtDropX(700, LANE_LEFT, dayGeom)).toBe('2026-09-05');
    });

    it('resolves a week column to the Monday it starts on', () => {
        const weekGeom = { colPx: 100, colDays: 7, firstDay: '2026-08-31', totalCols: 5 };
        expect(dateAtDropX(200, LANE_LEFT, weekGeom)).toBe('2026-08-31');
        expect(dateAtDropX(320, LANE_LEFT, weekGeom)).toBe('2026-09-07');
        expect(dateAtDropX(430, LANE_LEFT, weekGeom)).toBe('2026-09-14');
    });

    it('is timezone-stable — no UTC drift onto the previous day', () => {
        for (let col = 0; col < 10; col++) {
            const iso = dateAtDropX(LANE_LEFT + col * 100 + 5, LANE_LEFT, dayGeom);
            expect(iso).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        }
        expect(dateAtDropX(LANE_LEFT + 5, LANE_LEFT, dayGeom)).toBe('2026-08-31');
    });

    it('returns null before the chart range exists', () => {
        expect(dateAtDropX(300, LANE_LEFT, { ...dayGeom, firstDay: null })).toBeNull();
    });
});
