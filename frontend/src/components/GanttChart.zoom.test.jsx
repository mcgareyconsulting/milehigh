/**
 * Timeline zoom keeps your place (BUG-21).
 *
 * Zooming used to dump you at whatever column happened to be leftmost. The re-anchor effect derived
 * the left-edge date from `scrollLeft` AFTER React had committed the narrower column width — by
 * which point the browser had already clamped `scrollLeft` to the new, smaller maximum, so the
 * date it recovered was not the date that had been on screen.
 *
 * jsdom has no layout, so the clamp that causes the bug has to be modelled: the scroll container
 * gets a `scrollLeft` that clamps against its own content width, exactly as a real browser does.
 * With that in place the test fails on the old implementation and passes on the fix.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('./ReleaseHubModal', () => ({ ReleaseHubModal: () => null }));
vi.mock('./PdfMarkupModal', () => ({ PdfMarkupModal: () => null }));

vi.mock('../utils/auth', () => ({ checkAuth: () => Promise.resolve({ is_admin: false }) }));
vi.mock('../services/jobsApi', () => ({
    jobsApi: { getInstallerTeams: () => Promise.resolve(['Crew A']) },
}));

const mockJobs = vi.hoisted(() => ({ current: [] }));
vi.mock('../context/ReleasesContext', () => ({
    useReleases: () => ({ jobs: mockJobs.current, loading: false }),
}));

import GanttChart from './GanttChart';

// The chart falls back to a 1280px viewport pre-measure; that leaves (1280 - 200 - 192) = 888px of
// date columns, split into whatever the zoom level asks for. Default is 7 (one day each); one step
// out is 14.
const VIEWPORT_W = 1280;
const CHART_W = VIEWPORT_W - 200 - 192;
const COL_PX_DEFAULT = CHART_W / 7;
const COL_PX_ONE_OUT = CHART_W / 14;

// Far enough out that the chart is several viewports wide at both zoom levels, so there is room for
// the anchor to sit past the point where the zoomed-out chart clamps.
const ANCHOR_DAYS = 90;

const addDays = (n) => {
    const d = new Date();
    d.setDate(d.getDate() + n);
    return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-');
};

const rel = (over = {}) => ({
    id: 1,
    'Job #': 560,
    'Release #': '923',
    'Job': 'Alta Metro',
    'Description': 'Bldg C stair',
    'Stage': 'Store at MHMW',
    'Start install': addDays(120),
    start_install_formulaTF: false,
    start_install_asap: false,
    installer: 'Crew A',
    ...over,
});

/**
 * Give the scroll container a browser's scrollLeft: writes and reads are both clamped to
 * (content width − viewport). The content width is read live off the chart body, so it shrinks the
 * instant a zoom-out commits — which is the whole mechanism of the bug.
 */
const clampLikeABrowser = (el) => {
    let stored = 0;
    const maxScroll = () => {
        const content = parseFloat(el.firstElementChild?.style?.width || '0');
        return Math.max(0, content - VIEWPORT_W);
    };
    Object.defineProperty(el, 'scrollLeft', {
        configurable: true,
        get: () => Math.min(stored, maxScroll()),
        set: (v) => { stored = Math.min(Math.max(0, v), maxScroll()); },
    });
    return maxScroll;
};

const renderChart = async () => {
    const view = render(<GanttChart />);
    await screen.findByText('Crew A');
    return view;
};

beforeEach(() => {
    mockJobs.current = [rel()];
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ orders: [] }) }));
});

describe('zooming the timeline', () => {
    it('keeps the left-edge date when zooming out, even though the browser clamps scrollLeft first', async () => {
        const { container } = await renderChart();
        const scroller = container.querySelector('[data-timeline-scroll]');
        const maxScroll = clampLikeABrowser(scroller);

        scroller.scrollLeft = ANCHOR_DAYS * COL_PX_DEFAULT;
        const before = scroller.scrollLeft;
        expect(before).toBeCloseTo(ANCHOR_DAYS * COL_PX_DEFAULT, 0);   // the anchor is reachable at this zoom

        fireEvent.click(screen.getByTitle('Zoom out'));

        // The test only means anything if the clamp actually bites — i.e. the zoomed-out chart is
        // too narrow to hold the old pixel offset, so reading scrollLeft after the render would
        // have returned a corrupted value.
        expect(maxScroll()).toBeLessThan(before);
        expect(scroller.scrollLeft).toBeCloseTo(ANCHOR_DAYS * COL_PX_ONE_OUT, 0);
    });

    it('keeps the left-edge date when zooming back in', async () => {
        const { container } = await renderChart();
        const scroller = container.querySelector('[data-timeline-scroll]');
        clampLikeABrowser(scroller);

        fireEvent.click(screen.getByTitle('Zoom out'));
        scroller.scrollLeft = ANCHOR_DAYS * COL_PX_ONE_OUT;

        fireEvent.click(screen.getByTitle('Zoom in'));

        expect(scroller.scrollLeft).toBeCloseTo(ANCHOR_DAYS * COL_PX_DEFAULT, 0);
    });
});
