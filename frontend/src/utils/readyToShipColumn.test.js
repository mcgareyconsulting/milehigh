/**
 * Ready-to-Ship column membership + order (utils/readyToShipColumn).
 *
 * The column is two work sections — Paint QC, then Store at MHMW, each soonest-date first —
 * plus a trailing visibility-only block of ASAPs still in Fab or Paint.
 */
import { describe, it, expect } from 'vitest';
import { selectReadyToShip, isReadyToShip, isUpstreamAsap } from './readyToShipColumn';

const rel = (over = {}) => ({
    id: over.id ?? Math.floor(Math.random() * 1e6),
    'Job #': 560,
    'Release #': '100',
    'Stage': 'Paint QC',
    'Stage Group': 'READY_TO_SHIP',
    'Start install': null,
    start_install_formulaTF: true,
    start_install_asap: false,
    ...over,
});

const ids = (rows) => rows.map((r) => r['Release #']);

describe('isReadyToShip', () => {
    it('takes Paint QC and Store at MHMW with no hard date', () => {
        expect(isReadyToShip(rel({ Stage: 'Paint QC' }))).toBe(true);
        expect(isReadyToShip(rel({ Stage: 'Store at MHMW' }))).toBe(true);
    });

    it('treats a projected (formula) date as no date', () => {
        expect(isReadyToShip(rel({ 'Start install': '2026-09-20', start_install_formulaTF: true }))).toBe(true);
    });

    it('drops a release once it has a hard date', () => {
        expect(isReadyToShip(rel({ 'Start install': '2026-09-20', start_install_formulaTF: false }))).toBe(false);
    });

    it('ignores other stages, Ship Planning included', () => {
        expect(isReadyToShip(rel({ Stage: 'Ship Planning' }))).toBe(false);
        expect(isReadyToShip(rel({ Stage: 'Paint Start' }))).toBe(false);
    });
});

describe('isUpstreamAsap', () => {
    it('takes an ASAP in a Paint stage or the FABRICATION band, hard date or not', () => {
        expect(isUpstreamAsap(rel({ Stage: 'Paint Start', start_install_asap: true,
            'Start install': '2026-09-25', start_install_formulaTF: false }))).toBe(true);
        expect(isUpstreamAsap(rel({ Stage: 'Welded QC', start_install_asap: true }))).toBe(true);
        expect(isUpstreamAsap(rel({ Stage: 'Cut Start', 'Stage Group': 'FABRICATION',
            start_install_asap: true, 'Start install': '2026-09-25', start_install_formulaTF: false }))).toBe(true);
    });

    it('needs the ASAP flag', () => {
        expect(isUpstreamAsap(rel({ Stage: 'Paint Start' }))).toBe(false);
        expect(isUpstreamAsap(rel({ Stage: 'Cut Start', 'Stage Group': 'FABRICATION' }))).toBe(false);
    });

    it('leaves out ASAPs outside Fab / Paint', () => {
        expect(isUpstreamAsap(rel({ Stage: 'Released', 'Stage Group': 'DRAFTING', start_install_asap: true }))).toBe(false);
        expect(isUpstreamAsap(rel({ Stage: 'Ship Planning', start_install_asap: true }))).toBe(false);
    });
});

describe('selectReadyToShip', () => {
    it('orders Paint QC, then Store at MHMW, then upstream ASAPs, tagging each section', () => {
        const rows = selectReadyToShip([
            rel({ 'Release #': 'fab', Stage: 'Cut Start', 'Stage Group': 'FABRICATION', start_install_asap: true }),
            rel({ 'Release #': 'store', Stage: 'Store at MHMW' }),
            rel({ 'Release #': 'paint', Stage: 'Paint QC' }),
        ]);
        expect(ids(rows)).toEqual(['paint', 'store', 'fab']);
        expect(rows.map((r) => r._rtsSection)).toEqual(['paint', 'store', 'upstream']);
    });

    it('sorts each section by date, soonest first, undated last', () => {
        const rows = selectReadyToShip([
            rel({ 'Release #': 'none', 'Start install': null }),
            rel({ 'Release #': 'late', 'Start install': '2026-10-01' }),
            rel({ 'Release #': 'early', 'Start install': '2026-09-20T00:00:00' }),
            rel({ 'Release #': 's-late', Stage: 'Store at MHMW', 'Start install': '2026-09-30' }),
            rel({ 'Release #': 's-early', Stage: 'Store at MHMW', 'Start install': '2026-09-01' }),
        ]);
        expect(ids(rows)).toEqual(['early', 'late', 'none', 's-early', 's-late']);
    });

    it('does not float an ASAP above an earlier date inside a section', () => {
        const rows = selectReadyToShip([
            rel({ 'Release #': 'rush', 'Start install': '2026-09-30', start_install_asap: true }),
            rel({ 'Release #': 'plain', 'Start install': '2026-09-10' }),
        ]);
        expect(ids(rows)).toEqual(['plain', 'rush']);
    });

    it('breaks date ties on job # then release # (numeric), so the order is stable', () => {
        const rows = selectReadyToShip([
            rel({ 'Job #': 600, 'Release #': '1', 'Start install': '2026-09-20' }),
            rel({ 'Job #': 500, 'Release #': '10', 'Start install': '2026-09-20' }),
            rel({ 'Job #': 500, 'Release #': '9', 'Start install': '2026-09-20' }),
        ]);
        expect(rows.map((r) => `${r['Job #']}-${r['Release #']}`)).toEqual(['500-9', '500-10', '600-1']);
    });

    it('tags upstream ASAPs with where they still are', () => {
        const rows = selectReadyToShip([
            rel({ 'Release #': 'p', Stage: 'Paint Start', start_install_asap: true }),
            rel({ 'Release #': 'f', Stage: 'Fit Up Complete', 'Stage Group': 'FABRICATION', start_install_asap: true }),
        ]);
        const byId = Object.fromEntries(rows.map((r) => [r['Release #'], r._asapOrigin]));
        expect(byId).toEqual({ p: 'Paint', f: 'Fab' });
    });

    it('does not tag in-shop holds with an origin', () => {
        const [row] = selectReadyToShip([rel({ start_install_asap: true })]);
        expect(row._rtsSection).toBe('paint');
        expect(row._asapOrigin).toBeUndefined();
    });

    it('never mutates the source rows', () => {
        const src = rel({ 'Release #': 'x' });
        selectReadyToShip([src]);
        expect(src._rtsSection).toBeUndefined();
    });

    it('handles an empty or missing dataset', () => {
        expect(selectReadyToShip([])).toEqual([]);
        expect(selectReadyToShip(undefined)).toEqual([]);
    });
});
