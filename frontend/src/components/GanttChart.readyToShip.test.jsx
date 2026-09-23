/**
 * The Timeline's Ready-to-Ship column, rendered: its sections, its counts, which cards can be
 * dragged, and the two chrome fixes that shipped with it (hover tooltip flip, header over folded
 * rails). Selection and sort rules themselves are covered in utils/readyToShipColumn.test.js.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, waitFor, fireEvent } from '@testing-library/react';

vi.mock('./ReleaseHubModal', () => ({ ReleaseHubModal: () => null }));
vi.mock('./PdfMarkupModal', () => ({ PdfMarkupModal: () => null }));

const authUser = vi.hoisted(() => ({ current: { is_admin: true } }));
vi.mock('../utils/auth', () => ({ checkAuth: () => Promise.resolve(authUser.current) }));
vi.mock('../services/jobsApi', () => ({
    jobsApi: { getInstallerTeams: () => Promise.resolve(['Crew A', 'Crew B']) },
}));

const mockJobs = vi.hoisted(() => ({ current: [] }));
vi.mock('../context/ReleasesContext', () => ({
    useReleases: () => ({ jobs: mockJobs.current, loading: false, refetch: () => {}, patchJob: () => {} }),
}));

import GanttChart from './GanttChart';

const rel = (over = {}) => ({
    id: over.id ?? Math.floor(Math.random() * 1e6),
    'Job #': 560,
    'Release #': '923',
    'Job': 'Alta Metro',
    'Description': 'Bldg C stair',
    'Stage': 'Paint Complete',
    'Stage Group': 'READY_TO_SHIP',
    'Start install': null,
    start_install_formulaTF: true,
    start_install_asap: false,
    installer: null,
    ...over,
});

const readyColumn = (container) => container.querySelector('[data-ready-to-ship]');
const cardFor = (container, jr) => within(readyColumn(container)).getByText(jr).closest('[role="button"]');

beforeEach(() => {
    mockJobs.current = [];
    authUser.current = { is_admin: true };
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ orders: [] }) }));
});

const renderChart = async () => {
    const view = render(<GanttChart />);
    await screen.findByText('Crew A');
    return view;
};

const MIXED = () => [
    rel({ id: 1, 'Release #': 'store', Stage: 'Store at MHMW', 'Start install': '2026-09-01' }),
    rel({ id: 2, 'Release #': 'paint-late', 'Start install': '2026-10-01' }),
    rel({ id: 3, 'Release #': 'paint-early', 'Start install': '2026-09-15' }),
    rel({
        id: 4, 'Release #': 'rush', Stage: 'Cut Start', 'Stage Group': 'FABRICATION',
        start_install_asap: true, 'Start install': '2026-09-25', start_install_formulaTF: false,
    }),
];

describe('Ready-to-Ship column sections', () => {
    it('groups Paint Complete, then Store at MHMW, then the Fab/Paint ASAPs, each group by date', async () => {
        mockJobs.current = MIXED();
        const { container } = await renderChart();
        const cards = within(readyColumn(container)).getAllByRole('button').map((b) => b.textContent);
        const pos = (jr) => cards.findIndex((t) => t.includes(jr));

        // Paint section soonest first, then the store card, then the upstream ASAP.
        expect(pos('560-paint-early')).toBeLessThan(pos('560-paint-late'));
        expect(pos('560-paint-late')).toBeLessThan(pos('560-store'));
        expect(pos('560-store')).toBeLessThan(pos('560-rush'));
    });

    it('draws no section headers — each card names its own stage in its pill', async () => {
        mockJobs.current = MIXED();
        const { container } = await renderChart();
        const col = readyColumn(container);
        // Everything in the column is a card; nothing sits between them.
        expect(col.querySelectorAll('[role="button"]').length).toBe(4);
        expect(col.textContent).not.toMatch(/ASAP · in Fab/);
        expect(within(col).getAllByText('Paint Comp').length).toBe(2);
    });

    it('counts only the in-shop holds as needing a ship date', async () => {
        mockJobs.current = MIXED();
        await renderChart();
        expect(screen.getByText('3 need a ship date')).toBeInTheDocument();
    });

    it('tags an upstream ASAP with where it still is', async () => {
        mockJobs.current = MIXED();
        const { container } = await renderChart();
        const card = cardFor(container, '560-rush');
        expect(within(card).getByText('ASAP')).toBeInTheDocument();
        expect(within(card).getByText('in Fab')).toBeInTheDocument();
    });

    it('lets an admin drag the holds but not the upstream ASAPs', async () => {
        mockJobs.current = MIXED();
        const { container } = await renderChart();
        await waitFor(() => expect(cardFor(container, '560-store').className).toContain('cursor-grab'));
        expect(cardFor(container, '560-paint-early').className).toContain('cursor-grab');
        expect(cardFor(container, '560-rush').className).not.toContain('cursor-grab');
    });

    it('tints each section differently and keeps the ASAP red', async () => {
        mockJobs.current = [
            ...MIXED(),
            rel({ id: 5, 'Release #': 'hot-paint', start_install_asap: true }),
        ];
        const { container } = await renderChart();
        expect(cardFor(container, '560-paint-early').className).toContain('bg-sky-50');
        expect(cardFor(container, '560-store').className).toContain('bg-violet-50');
        expect(cardFor(container, '560-hot-paint').className).toContain('bg-red-50');
        expect(cardFor(container, '560-hot-paint').className).not.toContain('bg-sky-50');
    });
});

describe('staging card shape', () => {
    it('gives every card a stage pill, so a card is the same height in both columns', async () => {
        mockJobs.current = [
            ...MIXED(),
            // A dated Store release — the Unassigned tray's card, the one the heights must match.
            rel({ id: 9, 'Release #': 'dated', Stage: 'Store at MHMW',
                'Start install': '2026-09-10', start_install_formulaTF: false }),
        ];
        const { container } = await renderChart();
        const cards = [
            ...container.querySelectorAll('[data-ready-to-ship] [role="button"]'),
            ...container.querySelectorAll('[data-staging-tray] [role="button"]'),
        ];
        expect(cards.length).toBe(5);
        // Every card leads with the same one-line badge row, whether or not it has an ASAP in it.
        for (const card of cards) {
            const row = card.firstElementChild;
            expect(row.className).toContain('min-h-[16px]');
            expect(row.lastElementChild.className).toContain('ml-auto');
        }
    });

    it('abbreviates the long stages and keeps the full name in the title', async () => {
        mockJobs.current = MIXED();
        const { container } = await renderChart();
        expect(within(cardFor(container, '560-store')).getByText('Store').title).toBe('Store at MHMW');
        expect(within(cardFor(container, '560-paint-early')).getByText('Paint Comp').title).toBe('Paint Complete');
        expect(within(cardFor(container, '560-rush')).getByText('Cut Start')).toBeInTheDocument();
    });
});

describe('Timeline chrome', () => {
    it('opens the hover tooltip above the cursor on the lower half of the screen', async () => {
        mockJobs.current = MIXED();
        const { container } = await renderChart();
        fireEvent.mouseMove(cardFor(container, '560-store'), { clientX: 50, clientY: window.innerHeight - 20 });
        const tip = screen.getByText(/^Job 560-store/).parentElement;
        expect(tip.style.bottom).toBe('30px');
        expect(tip.style.top).toBe('');
    });

    it('opens the hover tooltip below the cursor on the upper half', async () => {
        mockJobs.current = MIXED();
        const { container } = await renderChart();
        fireEvent.mouseMove(cardFor(container, '560-store'), { clientX: 50, clientY: 40 });
        const tip = screen.getByText(/^Job 560-store/).parentElement;
        expect(tip.style.top).toBe('50px');
        expect(tip.style.bottom).toBe('');
    });

    it('hangs the pinned columns off the MEASURED header height, so their last card scrolls fully into view', async () => {
        // jsdom reports 0 for every offsetHeight, so stub the header's. The bug this guards was a
        // hard-coded 60px against a real 70px header: the columns hung 10px below the viewport and
        // the last card's bottom border could not be reached until the page itself was scrolled.
        const proto = Object.getPrototypeOf(document.createElement('div'));
        const spy = vi.spyOn(proto, 'offsetHeight', 'get').mockImplementation(function get() {
            return this.className?.includes?.('sticky top-0') ? 70 : 0;
        });
        try {
            mockJobs.current = MIXED();
            const { container } = await renderChart();
            await waitFor(() => expect(container.querySelector('[data-ready-to-ship]').style.top).toBe('70px'));
            expect(container.querySelector('[data-staging-tray]').style.top).toBe('70px');
        } finally {
            spy.mockRestore();
        }
    });

    it('keeps the sticky header above the folded staging rails so the expand controls stay clickable', async () => {
        mockJobs.current = MIXED();
        await renderChart();
        const header = screen.getByLabelText('Collapse ready to ship column').closest('.sticky.top-0');
        expect(header.className).toContain('z-40');
    });
});
