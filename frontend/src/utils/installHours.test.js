// The one reading of a release's install hours (T9 splices): a release with splices
// under it keeps the WHOLE pool in install_hrs, so every view shows the pool minus
// what those splices drew — 150 with 50 spliced reads 100.
import { describe, it, expect } from 'vitest';
import {
    additionalHrs,
    budgetHrs,
    hasSplicedHours,
    installHrsNote,
    installHrsOwn,
    installHrsTotal,
    isSplice,
    parentPoolHrs,
    splicedHrs,
} from './installHours';

// Job Log rows key hours as 'Install HRS'; Subs rows as install_hrs. Both carry the split.
const jobLogRow = (over = {}) => ({
    id: 1, 'Install HRS': 150, spliced_install_hrs: 50, remaining_install_hrs: 100, ...over,
});
const subsRow = (over = {}) => ({
    id: 1, install_hrs: 150, spliced_install_hrs: 50, remaining_install_hrs: 100, ...over,
});

describe('installHours', () => {
    it('reads the netted hours off both payload shapes', () => {
        expect(installHrsOwn(jobLogRow())).toBe(100);
        expect(installHrsOwn(subsRow())).toBe(100);
        expect(installHrsTotal(jobLogRow())).toBe(150);
        expect(installHrsTotal(subsRow())).toBe(150);
    });

    it('leaves an unspliced release on its own hours', () => {
        const plain = { 'Install HRS': 80, spliced_install_hrs: null, remaining_install_hrs: null };
        expect(installHrsOwn(plain)).toBe(80);
        expect(installHrsTotal(plain)).toBe(80);
        expect(splicedHrs(plain)).toBe(0);
        expect(hasSplicedHours(plain)).toBe(false);
        expect(installHrsNote(plain)).toBeNull();
    });

    it('treats a splice row (nothing spliced off IT) as carrying its own hours', () => {
        const splice = { install_hrs: 50, parent_release_id: 1, spliced_install_hrs: null, remaining_install_hrs: null };
        expect(installHrsOwn(splice)).toBe(50);
        expect(hasSplicedHours(splice)).toBe(false);
    });

    it('explains a netted number in one line', () => {
        expect(installHrsNote(jobLogRow())).toBe(
            '150 total install hrs · 50 spliced off to splices · 100 left on this release',
        );
    });

    it('handles a release with no install hours at all', () => {
        const none = { 'Install HRS': null, spliced_install_hrs: null, remaining_install_hrs: null };
        expect(installHrsOwn(none)).toBeNull();
        expect(installHrsTotal(none)).toBeNull();
        expect(installHrsNote(none)).toBeNull();
    });

    it('nets to zero rather than negative when the whole pool is spliced away', () => {
        expect(installHrsOwn(jobLogRow({ spliced_install_hrs: 150, remaining_install_hrs: 0 }))).toBe(0);
    });

    it('survives a missing row', () => {
        expect(installHrsOwn(null)).toBeNull();
        expect(splicedHrs(undefined)).toBe(0);
        expect(hasSplicedHours(null)).toBe(false);
    });
});

describe('installHours — splice rows', () => {
    const splice = (over = {}) => ({
        id: 3, 'Install HRS': 14, parent_release_id: 1, parent_install_hrs: 12, additional_install_hrs: 4, ...over,
    });

    it('knows a splice by its parent id', () => {
        expect(isSplice(splice())).toBe(true);
        expect(isSplice(jobLogRow())).toBe(false);
        expect(isSplice(null)).toBe(false);
    });

    it('splits a splice into budget and additional hours', () => {
        expect(additionalHrs(splice())).toBe(4);
        expect(budgetHrs(splice())).toBe(10);
        expect(budgetHrs(splice({ additional_install_hrs: null }))).toBe(14);
        // Never negative, and nothing to split without hours.
        expect(budgetHrs(splice({ 'Install HRS': 3 }))).toBe(0);
        expect(budgetHrs(splice({ 'Install HRS': null }))).toBeNull();
        expect(additionalHrs(null)).toBe(0);
    });

    it('reads the group pool off parent_install_hrs', () => {
        expect(parentPoolHrs(splice())).toBe(12);
        expect(parentPoolHrs(splice({ parent_install_hrs: null }))).toBeNull();
        expect(parentPoolHrs(null)).toBeNull();
    });
});
