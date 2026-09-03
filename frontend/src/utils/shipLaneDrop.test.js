import { describe, it, expect } from 'vitest';
import { hasHardInstall, shipLaneDropOutcome, shipLabelFor, SHIP_COMPLETE_STAGE } from './shipLaneDrop';

const row = (over = {}) => ({
    'Stage': 'Ship Planning',
    'Start install': '2026-09-10',
    start_install_formulaTF: false,
    ...over,
});

describe('hasHardInstall', () => {
    it('is true only for an explicit, non-formula date', () => {
        expect(hasHardInstall(row())).toBe(true);
    });

    it('is false for a projected date — the scheduler can move it, so it anchors nothing', () => {
        expect(hasHardInstall(row({ start_install_formulaTF: true }))).toBe(false);
    });

    it('is false when there is no date at all', () => {
        expect(hasHardInstall(row({ 'Start install': null }))).toBe(false);
    });

    it('survives a missing row rather than throwing mid-drag', () => {
        expect(hasHardInstall(null)).toBe(false);
        expect(hasHardInstall(undefined)).toBe(false);
    });
});

describe('shipLaneDropOutcome', () => {
    it('writes the stage on a genuine move', () => {
        expect(shipLaneDropOutcome(row(), SHIP_COMPLETE_STAGE)).toEqual({
            kind: 'write',
            label: 'Set stage → Ship Complete',
        });
    });

    it('is a no-op when the card is dropped on the lane it already lives in', () => {
        expect(shipLaneDropOutcome(row(), 'Ship Planning').kind).toBe('noop');
    });

    it('blocks Ship Complete without a hard Start install — the lane is anchored on that date', () => {
        const projected = row({ start_install_formulaTF: true });
        const outcome = shipLaneDropOutcome(projected, SHIP_COMPLETE_STAGE);
        expect(outcome.kind).toBe('blocked');
        expect(outcome.label).toBe('Needs a hard Start install');
        // The toast reads as a sentence; the chip does not. Reusing one for the other would either
        // mangle the field name "Start install" or read as a fragment.
        expect(outcome.reason).toMatch(/hard Start install/);
    });

    it('blocks Ship Complete with no date at all', () => {
        expect(shipLaneDropOutcome(row({ 'Start install': null }), SHIP_COMPLETE_STAGE).kind).toBe('blocked');
    });

    it('does NOT apply that guard to Ship Planning, which falls back to an estimated ship date', () => {
        const projected = row({ 'Stage': 'Ship Complete', start_install_formulaTF: true });
        expect(shipLaneDropOutcome(projected, 'Ship Planning').kind).toBe('write');
    });

    it('lets a release arrive from outside the shipping stages', () => {
        expect(shipLaneDropOutcome(row({ 'Stage': 'Paint Complete' }), 'Ship Planning').kind).toBe('write');
        expect(shipLaneDropOutcome(row({ 'Stage': 'Paint Complete' }), SHIP_COMPLETE_STAGE).kind).toBe('write');
    });

    it('treats a missing stage as "not there yet" rather than matching', () => {
        expect(shipLaneDropOutcome(row({ 'Stage': undefined }), 'Ship Planning').kind).toBe('write');
    });
});

describe('shipLabelFor', () => {
    it('never names a date — a shipping drop writes none', () => {
        expect(shipLabelFor(row(), SHIP_COMPLETE_STAGE)).not.toMatch(/\d{4}-\d{2}-\d{2}/);
    });

    it('says what will happen, not just that something will', () => {
        expect(shipLabelFor(row(), SHIP_COMPLETE_STAGE)).toContain('Ship Complete');
    });
});
