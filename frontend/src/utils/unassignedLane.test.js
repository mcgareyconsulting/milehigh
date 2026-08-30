import { describe, it, expect } from 'vitest';
import { READY_TO_SHIP_STAGES, isUnassigned, selectUnassigned } from './unassignedLane';

const rel = (over = {}) => ({
    'Job #': 560,
    'Release #': '923',
    'Stage': 'Paint Complete',
    installer: null,
    start_install_asap: false,
    ...over,
});

describe('isUnassigned — membership rule', () => {
    it('accepts all three of Bill\'s shop states when nobody is assigned', () => {
        for (const stage of READY_TO_SHIP_STAGES) {
            expect(isUnassigned(rel({ Stage: stage }))).toBe(true);
        }
    });

    it('rejects a release that already has an installer — it lives in that lane instead', () => {
        expect(isUnassigned(rel({ installer: 'Crew A' }))).toBe(false);
    });

    it('treats a whitespace-only installer as unassigned', () => {
        expect(isUnassigned(rel({ installer: '   ' }))).toBe(true);
    });

    it('rejects upstream drafting and fabrication rows — the column is a work surface, not a dump', () => {
        for (const stage of ['Released', 'Material Ordered', 'Cut Start', 'Fitup Complete', 'Weld Complete', 'Paint Start']) {
            expect(isUnassigned(rel({ Stage: stage }))).toBe(false);
        }
    });

    it('rejects releases already past shipping — those are gone or being installed', () => {
        for (const stage of ['Ship Complete', 'Install Start', 'Install Complete', 'Complete']) {
            expect(isUnassigned(rel({ Stage: stage }))).toBe(false);
        }
    });

    it('rejects Hold', () => {
        expect(isUnassigned(rel({ Stage: 'Hold' }))).toBe(false);
    });

    it('tolerates a padded stage value', () => {
        expect(isUnassigned(rel({ Stage: '  Ship Planning  ' }))).toBe(true);
    });

    it('survives a missing stage or a null row', () => {
        expect(isUnassigned(rel({ Stage: null }))).toBe(false);
        expect(isUnassigned({})).toBe(false);
        expect(isUnassigned(null)).toBe(false);
    });
});

describe('selectUnassigned — staging column order', () => {
    it('floats ASAP rush jobs to the top regardless of job number', () => {
        const out = selectUnassigned([
            rel({ 'Job #': 100, 'Release #': '1' }),
            rel({ 'Job #': 900, 'Release #': '2', start_install_asap: true }),
        ]);
        expect(out.map((r) => r['Job #'])).toEqual([900, 100]);
    });

    it('sorts by job # then release # numerically, not lexically', () => {
        const out = selectUnassigned([
            rel({ 'Job #': 560, 'Release #': '10' }),
            rel({ 'Job #': 560, 'Release #': '9' }),
            rel({ 'Job #': 90, 'Release #': '1' }),
        ]);
        expect(out.map((r) => `${r['Job #']}-${r['Release #']}`)).toEqual(['90-1', '560-9', '560-10']);
    });

    it('drops everything that fails the membership rule', () => {
        const out = selectUnassigned([
            rel({ 'Release #': 'keep' }),
            rel({ 'Release #': 'assigned', installer: 'Crew B' }),
            rel({ 'Release #': 'upstream', Stage: 'Cut Start' }),
        ]);
        expect(out.map((r) => r['Release #'])).toEqual(['keep']);
    });

    it('does not mutate the caller\'s array', () => {
        const input = [rel({ 'Job #': 900 }), rel({ 'Job #': 100 })];
        const snapshot = [...input];
        selectUnassigned(input);
        expect(input).toEqual(snapshot);
    });

    it('handles an empty or missing dataset', () => {
        expect(selectUnassigned([])).toEqual([]);
        expect(selectUnassigned(undefined)).toEqual([]);
    });
});
