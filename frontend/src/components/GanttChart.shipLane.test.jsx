/**
 * Shipping-lane drag — walking a release from Shipping Planning to Shipping Completed on the board.
 *
 * The shipping lanes used to be read-only precisely because a stage change has a much wider blast
 * radius than assigning a crew. Opening them up means the write has to be narrow and predictable:
 * STAGE ONLY, never a date, no-op when nothing changes, and refused outright when the target lane
 * has nowhere to put the card. These tests pin exactly that.
 *
 * jsdom has no layout, so dnd-kit's collision detection can't run a real pointer drag; the handlers
 * are driven through the DndContext the component actually mounts, with lane rects stubbed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, within } from '@testing-library/react';

vi.mock('./ReleaseHubModal', () => ({ ReleaseHubModal: () => null }));
vi.mock('./PdfMarkupModal', () => ({ PdfMarkupModal: () => null }));

const authUser = vi.hoisted(() => ({ current: { is_admin: true } }));
vi.mock('../utils/auth', () => ({ checkAuth: () => Promise.resolve(authUser.current) }));

const updateStartInstall = vi.hoisted(() => vi.fn());
const updateStage = vi.hoisted(() => vi.fn());
vi.mock('../services/jobsApi', () => ({
    jobsApi: {
        getInstallerTeams: () => Promise.resolve(['Crew A']),
        updateStartInstall: (...a) => updateStartInstall(...a),
        updateStage: (...a) => updateStage(...a),
    },
}));

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

const PLANNING = 'Shipping Planning';
const COMPLETED = 'Shipping Completed';

// A release with a HARD start install, so it is anchored on both shipping lanes.
const shipRel = (over = {}) => ({
    id: 7,
    'Job #': 560,
    'Release #': '923',
    'Job': 'Alta Metro',
    'Description': 'Bldg C stair',
    'Stage': 'Ship Planning',
    'Start install': '2026-09-10',
    'Ship Date': null,
    start_install_formulaTF: false,
    start_install_asap: false,
    installer: null,
    ...over,
});

const renderChart = async () => {
    const view = render(<GanttChart />);
    await screen.findByText('Crew A');
    return view;
};

const stubLaneRects = (container) => {
    container.querySelectorAll('[data-lane]').forEach((laneEl) => {
        const chart = laneEl.lastElementChild;
        if (chart) chart.getBoundingClientRect = () => ({ left: 0, top: 0, right: 9999, bottom: 40, width: 9999, height: 40 });
    });
};

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

const laneEl = (container, lane) => container.querySelector(`[data-lane="${lane}"]`);

beforeEach(() => {
    mockJobs.current = [];
    patchJob.mockClear();
    updateStartInstall.mockReset().mockResolvedValue({ status: 'success' });
    updateStage.mockReset().mockResolvedValue({ status: 'success' });
    authUser.current = { is_admin: true };
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ orders: [] }) }));
});

describe('dragging a card from Shipping Planning to Shipping Completed', () => {
    it('writes the stage through the same endpoint the Job Log dropdown uses', async () => {
        const row = shipRel();
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        await drop({ row, fromLane: PLANNING, overId: `lane:${COMPLETED}`, clientX: 5 });

        expect(updateStage).toHaveBeenCalledTimes(1);
        expect(updateStage).toHaveBeenCalledWith(560, '923', 'Ship Complete');
    });

    it('never writes a date, however far along the lane it is dropped', async () => {
        const row = shipRel();
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        // Column 4 — an installer lane would read a date off this X. A shipping lane must not.
        await drop({ row, fromLane: PLANNING, overId: `lane:${COMPLETED}`, clientX: COL_PX * 4 + 5 });

        expect(updateStartInstall).not.toHaveBeenCalled();
        expect(patchJob).toHaveBeenCalledWith(7, { Stage: 'Ship Complete' });
    });

    it('moves the card between lanes immediately instead of waiting for the next poll', async () => {
        const row = shipRel();
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        await drop({ row, fromLane: PLANNING, overId: `lane:${COMPLETED}`, clientX: 5 });

        expect(patchJob.mock.calls[0]).toEqual([7, { Stage: 'Ship Complete' }]);
    });

    it('works in reverse, so a mis-drop can be walked back on the board', async () => {
        const row = shipRel({ 'Stage': 'Ship Complete' });
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        await drop({ row, fromLane: COMPLETED, overId: `lane:${PLANNING}`, clientX: 5 });

        expect(updateStage).toHaveBeenCalledWith(560, '923', 'Ship Planning');
    });

    it('puts the stage back and says why when the write is rejected', async () => {
        const row = shipRel();
        mockJobs.current = [row];
        updateStage.mockRejectedValue(new Error('Event already exists'));
        const { container } = await renderChart();
        stubLaneRects(container);

        await drop({ row, fromLane: PLANNING, overId: `lane:${COMPLETED}`, clientX: 5 });

        expect(patchJob).toHaveBeenCalledTimes(2);
        expect(patchJob.mock.calls[1][1]).toEqual(expect.objectContaining({ Stage: 'Ship Planning' }));
        expect(await screen.findByRole('alert')).toHaveTextContent(/560-923.*Event already exists/);
    });
});

describe('shipping-lane drops that must not happen', () => {
    it('is a no-op when the card is dropped back on the lane it came from', async () => {
        const row = shipRel();
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        await drop({ row, fromLane: PLANNING, overId: `lane:${PLANNING}`, clientX: COL_PX * 3 });

        expect(updateStage).not.toHaveBeenCalled();
        expect(patchJob).not.toHaveBeenCalled();
    });

    it('refuses Shipping Completed when the release has no hard Start install', async () => {
        // The Completed lane is anchored on that date and the backend blanks estimated dates on the
        // way in — allowing this drop would make the card disappear off the board.
        const row = shipRel({ 'Start install': '2026-09-10', start_install_formulaTF: true, 'Ship Date': '2026-09-09' });
        mockJobs.current = [row];
        const { container } = await renderChart();
        stubLaneRects(container);

        await drop({ row, fromLane: PLANNING, overId: `lane:${COMPLETED}`, clientX: 5 });

        expect(updateStage).not.toHaveBeenCalled();
        expect(patchJob).not.toHaveBeenCalled();
        expect(await screen.findByRole('alert')).toHaveTextContent(/hard Start install/);
    });
});

// The hover hint's DOM branch needs dnd-kit's real `isOver`, which the mocked DndContext above
// cannot drive; its wording and its three cases are unit-tested in utils/shipLaneDrop.test.js.

describe('who can drag a shipping card', () => {
    it('gives admins a grab handle on the card', async () => {
        mockJobs.current = [shipRel()];
        const { container } = await renderChart();
        const card = within(laneEl(container, PLANNING)).getByText(/560-923/);
        expect(card.closest('.cursor-grab')).not.toBeNull();
    });

    it('leaves the card read-only for everyone else', async () => {
        authUser.current = { is_admin: false };
        mockJobs.current = [shipRel()];
        const { container } = await renderChart();
        const card = within(laneEl(container, PLANNING)).getByText(/560-923/);
        expect(card.closest('.cursor-grab')).toBeNull();
        expect(card.closest('.cursor-pointer')).not.toBeNull();
    });
});
