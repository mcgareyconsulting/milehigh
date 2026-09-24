/**
 * The one frontend copy of the stage → department map and the photo-gate rule derived from
 * it (T13). These pin the map's shape and the rule's edges; the backend has the same table in
 * tests/brain/test_stage_photo_gate.py, and the two must agree.
 */
import { describe, it, expect } from 'vitest';
import {
    STAGE_TO_GROUP,
    STAGE_GROUP_ORDER,
    GATE_ENTRY_STAGE,
    stageGroupOf,
    gateStageFor,
    stageGateFromError,
} from './stageGroups';

describe('the department map', () => {
    it('maps every stage to one of the four ordered groups', () => {
        expect(STAGE_GROUP_ORDER).toEqual(['FABRICATION', 'PAINT', 'READY_TO_SHIP', 'COMPLETE']);
        for (const group of Object.values(STAGE_TO_GROUP)) {
            expect(STAGE_GROUP_ORDER).toContain(group);
        }
    });

    it('puts exactly Welded QC and Paint Start in PAINT', () => {
        const paint = Object.entries(STAGE_TO_GROUP).filter(([, g]) => g === 'PAINT').map(([s]) => s);
        expect(paint.sort()).toEqual(['Paint Start', 'Welded QC']);
    });

    it('enters each gated department through a stage that belongs to it', () => {
        expect(Object.keys(GATE_ENTRY_STAGE).sort()).toEqual(['COMPLETE', 'PAINT', 'READY_TO_SHIP']);
        for (const [group, stage] of Object.entries(GATE_ENTRY_STAGE)) {
            expect(STAGE_TO_GROUP[stage]).toBe(group);
        }
    });

    it('stageGroupOf trims and returns undefined for the unknown', () => {
        expect(stageGroupOf(' Welded QC ')).toBe('PAINT');
        expect(stageGroupOf('Bogus')).toBeUndefined();
        expect(stageGroupOf(null)).toBeUndefined();
        expect(stageGroupOf(undefined)).toBeUndefined();
    });
});

describe('gateStageFor', () => {
    it.each([
        ['Weld Complete', 'Welded QC', 'Welded QC'],
        ['Hold', 'Welded QC', 'Welded QC'],
        ['Paint Start', 'Welded QC', null],
        ['Welded QC', 'Paint Start', null],
        ['Paint Start', 'Paint Complete', 'Paint Complete'],
        ['Welded QC', 'Store at MHMW', 'Paint Complete'],
        ['Store at MHMW', 'Ship Planning', null],
        ['Ship Planning', 'Ship Complete', 'Ship Complete'],
        ['Ship Planning', 'Complete', 'Ship Complete'],
        ['Weld Complete', 'Ship Complete', 'Ship Complete'],
        ['Ship Complete', 'Ship Planning', null],
        ['Complete', 'Released', null],
        ['Cut Start', 'Fitup Start', null],
        [null, 'Welded QC', null],
        ['Weld Complete', 'Bogus', null],
        ['Ship Complete', 'Install Start', null],
        [' Welded QC ', 'Paint Start', null],
    ])('%s → %s owes %s', (from, to, expected) => {
        expect(gateStageFor(from, to)).toBe(expected);
    });
});

describe('stageGateFromError', () => {
    const body = { code: 'photo_required', stage: 'Ship Complete', requested_stage: 'Complete' };

    it('reads the 422 body from a jobsApi-wrapped error', () => {
        const err = { originalError: { response: { data: body } } };
        expect(stageGateFromError(err)).toEqual({ stage: 'Ship Complete', requestedStage: 'Complete' });
    });

    it('reads a raw axios-shaped error too', () => {
        expect(stageGateFromError({ response: { data: body } }))
            .toEqual({ stage: 'Ship Complete', requestedStage: 'Complete' });
    });

    it('falls back to the gate stage when requested_stage is absent', () => {
        const err = { response: { data: { code: 'photo_required', stage: 'Welded QC' } } };
        expect(stageGateFromError(err)).toEqual({ stage: 'Welded QC', requestedStage: 'Welded QC' });
    });

    it('is null for anything that is not the gate', () => {
        expect(stageGateFromError(null)).toBeNull();
        expect(stageGateFromError(new Error('Event already exists'))).toBeNull();
        expect(stageGateFromError({ response: { data: { error: 'nope' } } })).toBeNull();
        expect(stageGateFromError({ response: { data: { code: 'photo_required' } } })).toBeNull();
        expect(stageGateFromError({ originalError: { response: { data: { code: 'other', stage: 'X' } } } })).toBeNull();
    });
});
