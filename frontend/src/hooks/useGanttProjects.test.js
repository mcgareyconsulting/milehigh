// Unit tests for buildGanttProjects — the frontend replication of the
// /brain/gantt-data grouping. Covers eligibility filters, the filterComplete
// pre-grouping drop, the comp_eta_effective end-date source, project min/max
// grouping, and deterministic color assignment.
import { describe, it, expect } from 'vitest';
import { buildGanttProjects } from './useGanttProjects.js';

const row = (over = {}) => ({
    'Job #': 400,
    'Release #': 'A',
    'Job': 'Acme',
    'Description': 'desc',
    'Start install': '2026-01-05',
    'start_install_formulaTF': false,
    'Install HRS': 40,
    'Stage Group': 'FABRICATION',
    'Stage': 'Cut Start',
    'comp_eta_effective': '2026-01-09',
    'PM': 'Pat',
    'BY': 'Bo',
    ...over,
});

describe('buildGanttProjects eligibility', () => {
    it('includes an eligible release', () => {
        const projects = buildGanttProjects([row()], {});
        expect(projects).toHaveLength(1);
        expect(projects[0].releases).toHaveLength(1);
    });

    it('drops rows without a Start install', () => {
        expect(buildGanttProjects([row({ 'Start install': null })], {})).toHaveLength(0);
    });

    it('drops soft (formula) dates where start_install_formulaTF === true', () => {
        expect(buildGanttProjects([row({ start_install_formulaTF: true })], {})).toHaveLength(0);
    });

    it('keeps rows where formulaTF is null (treated as hard)', () => {
        expect(buildGanttProjects([row({ start_install_formulaTF: null })], {})).toHaveLength(1);
    });

    it('drops rows with non-finite or non-positive Install HRS', () => {
        expect(buildGanttProjects([row({ 'Install HRS': 0 })], {})).toHaveLength(0);
        expect(buildGanttProjects([row({ 'Install HRS': null })], {})).toHaveLength(0);
        expect(buildGanttProjects([row({ 'Install HRS': NaN })], {})).toHaveLength(0);
    });

    it('drops rows whose Stage Group is not eligible', () => {
        expect(buildGanttProjects([row({ 'Stage Group': 'DRAFTING' })], {})).toHaveLength(0);
    });

    it('keeps READY_TO_SHIP and COMPLETE stage groups', () => {
        expect(buildGanttProjects([row({ 'Stage Group': 'READY_TO_SHIP' })], {})).toHaveLength(1);
        expect(buildGanttProjects([row({ 'Stage Group': 'COMPLETE' })], {})).toHaveLength(1);
    });
});

describe('buildGanttProjects filterComplete', () => {
    it('drops Stage === Complete rows when filterComplete is true', () => {
        const rows = [
            row({ 'Release #': 'A', Stage: 'Cut Start' }),
            row({ 'Release #': 'B', Stage: 'Complete', 'Stage Group': 'COMPLETE' }),
        ];
        const projects = buildGanttProjects(rows, { filterComplete: true });
        expect(projects).toHaveLength(1);
        expect(projects[0].releases.map(r => r.release)).toEqual(['A']);
    });

    it('keeps Stage === Complete rows when filterComplete is false', () => {
        const rows = [row({ 'Release #': 'B', Stage: 'Complete', 'Stage Group': 'COMPLETE' })];
        expect(buildGanttProjects(rows, { filterComplete: false })[0].releases).toHaveLength(1);
    });

    it('omits a project entirely when all its releases are filtered out', () => {
        const rows = [row({ Stage: 'Complete', 'Stage Group': 'COMPLETE' })];
        expect(buildGanttProjects(rows, { filterComplete: true })).toHaveLength(0);
    });
});

describe('buildGanttProjects end-date source', () => {
    it('uses comp_eta_effective as the release end date', () => {
        const projects = buildGanttProjects([row({ 'comp_eta_effective': '2026-02-01' })], {});
        expect(projects[0].releases[0].endDate).toBe('2026-02-01');
    });

    it('falls back to Start install when comp_eta_effective is missing', () => {
        const projects = buildGanttProjects([row({ 'comp_eta_effective': null })], {});
        expect(projects[0].releases[0].endDate).toBe('2026-01-05');
    });
});

describe('buildGanttProjects grouping', () => {
    it('groups releases by Job # with project min/max dates', () => {
        const rows = [
            row({ 'Job #': 400, 'Release #': 'A', 'Start install': '2026-01-05', 'comp_eta_effective': '2026-01-09' }),
            row({ 'Job #': 400, 'Release #': 'B', 'Start install': '2026-01-02', 'comp_eta_effective': '2026-01-20' }),
        ];
        const projects = buildGanttProjects(rows, {});
        expect(projects).toHaveLength(1);
        expect(projects[0].project).toBe(400);
        expect(projects[0].startDate).toBe('2026-01-02');
        expect(projects[0].endDate).toBe('2026-01-20');
        // releases sorted by startDate
        expect(projects[0].releases.map(r => r.release)).toEqual(['B', 'A']);
    });

    it('sorts projects by start date', () => {
        const rows = [
            row({ 'Job #': 500, 'Start install': '2026-03-01' }),
            row({ 'Job #': 400, 'Start install': '2026-01-01' }),
        ];
        const projects = buildGanttProjects(rows, {});
        expect(projects.map(p => p.project)).toEqual([400, 500]);
    });
});

describe('buildGanttProjects colors', () => {
    it('assigns deterministic colors by sorted-project index', () => {
        const rows = [
            row({ 'Job #': 400, 'Start install': '2026-01-01' }),
            row({ 'Job #': 500, 'Start install': '2026-02-01' }),
        ];
        const projects = buildGanttProjects(rows, {});
        // First two palette colors from the route, in sorted-key order.
        const byProject = Object.fromEntries(projects.map(p => [p.project, p.color]));
        expect(byProject[400]).toBe('#3B82F6');
        expect(byProject[500]).toBe('#10B981');
    });
});
