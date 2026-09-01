/**
 * Timeline drag-to-assign (T1c/T1d) — the timeline's first write.
 *
 * jsdom has no layout, so dnd-kit's collision detection can't run a real pointer drag here. These
 * tests drive `onDragEnd` through the DndContext the component actually mounts, with the lane rects
 * stubbed, which exercises the real handler: which PATCH goes out, what the optimistic patch does,
 * and what happens when the write is rejected.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';

vi.mock('./ReleaseHubModal', () => ({ ReleaseHubModal: () => null }));
vi.mock('./PdfMarkupModal', () => ({ PdfMarkupModal: () => null }));

const authUser = vi.hoisted(() => ({ current: { is_admin: true } }));
vi.mock('../utils/auth', () => ({ checkAuth: () => Promise.resolve(authUser.current) }));

const updateStartInstall = vi.hoisted(() => vi.fn());
vi.mock('../services/jobsApi', () => ({
    jobsApi: {
        getInstallerTeams: () => Promise.resolve(['Crew A', 'Crew B']),
        updateStartInstall: (...a) => updateStartInstall(...a),
    },
}));

// Capture the DndContext's handlers so a drop can be fired without real layout.
const dnd = vi.hoisted(() => ({ handlers: null }));
vi.mock('@dnd-kit/core', async (importOriginal) => {
    const actual = await importOriginal();
    return {
        ...actual,
        DndContext: ({ children, onDragEnd, onDragMove, onDragStart, onDragCancel }) => {
            dnd.handlers = { onDragEnd, onDragMove, onDragStart, onDragCancel };
            return children;
        },
        DragOverlay: ({ children }) => children ?? null,
    };
});

const mockJobs = vi.hoisted(() => ({ current: [] }));
const patchJob = vi.hoisted(() => vi.fn());
vi.mock('../context/ReleasesContext', () => ({
    useReleases: () => ({ jobs: mockJobs.current, loading: false, patchJob }),
}));

import GanttChart from './GanttChart';

const rel = (over = {}) => ({
    id: 1,
    'Job #': 560,
    'Release #': '923',
    'Job': 'Alta Metro',
    'Description': 'Bldg C stair',
    'Stage': 'Paint Complete',
    'Start install': null,
    start_install_formulaTF: true,
    start_install_asap: false,
    installer: null,
    ...over,
});

const renderChart = async () => {
    const view = render(<GanttChart />);
    await screen.findByText('Crew A');
    return view;
};

/**
 * Pin every lane's chart area to a known rect so the drop geometry is deterministic.
 * Column 0 starts at viewport x=0; colPx comes from the fallback 1280px viewport.
 */
const stubLaneRects = (container) => {
    container.querySelectorAll('[data-lane]').forEach((laneEl) => {
        const chart = laneEl.lastElementChild;
        if (chart) chart.getBoundingClientRect = () => ({ left: 0, top: 0, right: 9999, bottom: 40, width: 9999, height: 40 });
    });
};

// The chart falls back to a 1280px viewport pre-measure; at the default zoom (7 day-columns)
// that leaves (1280 - 168 - 192) / 7 = 131.43px per column.
const COL_PX = (1280 - 168 - 192) / 7;

const drop = async ({ row, fromLane = null, overId, clientX = 0 }) =>
    act(async () => {
        await dnd.handlers.onDragEnd({
            active: { id: 'x', data: { current: { row, fromLane } } },
            over: overId ? { id: overId } : null,
            activatorEvent: { clientX },
            delta: { x: 0, y: 0 },
        });
    });

beforeEach(() => {
    mockJobs.current = [];
    patchJob.mockClear();
    updateStartInstall.mockReset().mockResolvedValue({ status: 'success' });
    authUser.current = { is_admin: true };
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ orders: [] }) }));
});

describe('dropping an unassigned card on a crew lane', () => {
    it('writes the crew and a hard Start install for the day under the pointer, in one call', async () => {
        const row = rel();
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        // Land in column 2 of the chart.
        await drop({ row, overId: 'lane:Crew A', clientX: COL_PX * 2 + 5 });

        expect(updateStartInstall).toHaveBeenCalledTimes(1);
        const [job, release, date, installer] = updateStartInstall.mock.calls[0];
        expect(job).toBe(560);
        expect(release).toBe('923');
        expect(installer).toBe('Crew A');
        expect(date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });

    it('moves the card immediately instead of waiting for the next poll', async () => {
        const row = rel();
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        await drop({ row, overId: 'lane:Crew B', clientX: 5 });

        expect(patchJob).toHaveBeenCalledWith(1, expect.objectContaining({
            installer: 'Crew B',
            start_install_formulaTF: false,   // the dropped date is HARD, not a formula projection
        }));
    });

    it('puts the card back and says why when the write is rejected', async () => {
        const row = rel();
        mockJobs.current = [row];
        updateStartInstall.mockRejectedValue(new Error('Event already exists'));
        const { container } = await renderChart();
        stubLaneRects(container);

        await drop({ row, overId: 'lane:Crew A', clientX: 5 });

        // Optimistic patch, then a rollback to exactly the values it overwrote.
        expect(patchJob).toHaveBeenCalledTimes(2);
        expect(patchJob.mock.calls[1][1]).toEqual({
            installer: null,
            'Start install': null,
            start_install_formulaTF: true,
        });
        expect(await screen.findByRole('alert')).toHaveTextContent(/560-923.*Event already exists/);
    });
});

describe('dropping a scheduled card back on the tray', () => {
    it('clears the crew and deliberately leaves the date alone', async () => {
        const row = rel({ installer: 'Crew A', 'Start install': '2026-09-10', start_install_formulaTF: false });
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        await drop({ row, fromLane: 'Crew A', overId: 'unassigned-tray' });

        expect(updateStartInstall).toHaveBeenCalledWith(560, '923', null, '');
        expect(patchJob).toHaveBeenCalledWith(1, { installer: null });
    });

    it('does nothing when the card was already unassigned', async () => {
        const row = rel();
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        await drop({ row, overId: 'unassigned-tray' });

        expect(updateStartInstall).not.toHaveBeenCalled();
        expect(patchJob).not.toHaveBeenCalled();
    });
});

describe('drops that must not write', () => {
    it('ignores a release dropped outside any target', async () => {
        const row = rel();
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        await drop({ row, overId: null });
        expect(updateStartInstall).not.toHaveBeenCalled();
    });

    it('ignores a drop on a shipping lane — stage changes are not this feature', async () => {
        const row = rel();
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        // Shipping lanes register no droppable, so `over` can only ever be a lane the user can
        // legitimately hit. Guard the id shape anyway.
        await drop({ row, overId: 'Shipping Planning' });
        expect(updateStartInstall).not.toHaveBeenCalled();
    });

    it('is a no-op when a card is put back on the same crew and the same day', async () => {
        const row = rel({ installer: 'Crew A', 'Start install': null, start_install_formulaTF: false });
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        // Work out the date column 0 resolves to, then claim the row already sits there.
        await drop({ row, overId: 'lane:Crew A', clientX: 5 });
        const landedOn = updateStartInstall.mock.calls[0][2];

        updateStartInstall.mockClear();
        patchJob.mockClear();
        const settled = { ...row, 'Start install': landedOn };
        await drop({ row: settled, fromLane: 'Crew A', overId: 'lane:Crew A', clientX: 5 });

        expect(updateStartInstall).not.toHaveBeenCalled();
        expect(patchJob).not.toHaveBeenCalled();
    });
});

describe('non-admins keep the read-only timeline', () => {
    it('renders staging cards without a grab affordance', async () => {
        authUser.current = { is_admin: false };
        mockJobs.current = [rel()];
        const { container } = await renderChart();
        const card = container.querySelector('[data-staging-tray] [role="button"]');
        expect(card.className).toContain('cursor-pointer');
        expect(card.className).not.toContain('cursor-grab');
    });
});
