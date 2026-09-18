/**
 * The Splices tab after its facelift (Design canvas "Splices Tab Facelift", Option A).
 *
 * What these protect: every hours number on the tab is the server's, read straight off the
 * pool summary, and the bar and the table agree — the same 12-hour pool, 10 spliced, 2 left,
 * +14 additional, 26 total that the 555-551 screenshot showed. The table is numbers only
 * (2026-09-18): Budget Hours for the original is what it still installs ITSELF (2), so the
 * column sums straight to the pool; 0 or blank reads 0. Clicking a row opens a side panel
 * with that release's schedule, details and to-dos.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

const api = vi.hoisted(() => ({
    getSplices: vi.fn(),
    getRelease: vi.fn(),
}));
vi.mock('../services/jobsApi', () => ({ jobsApi: api }));
vi.mock('./SpliceReleaseModal', () => ({ SpliceReleaseModal: () => <div data-testid="splice-modal" /> }));
// The details body is JobDetailsBody's own concern (JobDetailsBody.compact.test.jsx); here we
// only care which release it gets and that it is the compact variant.
vi.mock('./JobDetailsBody', () => ({
    JobDetailsBody: (props) => (
        <div data-testid="details-body" data-release-id={props.releaseId} data-compact={String(!!props.compact)} />
    ),
}));

import { SplicesPane } from './SplicesPane';

// Exactly what GET /splices returns for the 555-551 group in the screenshot.
const SUMMARY = {
    parent_id: 1, job: 555, release: '551',
    total_install_hrs: 12, allocated_install_hrs: 10, remaining_install_hrs: 2,
    additional_install_hrs: 14, group_install_hrs: 26,
    next_splice_number: '551.3', is_splice: false,
    parent: {
        id: 1, job: 555, release: '551', job_name: 'Test', description: 'Test',
        stage: 'Install Complete', installer: 'Saul 1', install_hrs: 12, fab_hrs: 12,
    },
    splices: [
        {
            id: 2, job: 555, release: '551.1', description: 'Test - Splice 1', install_hrs: 10,
            budget_install_hrs: 10, additional_install_hrs: null, additional_install_note: null,
            stage: 'Released', installer: null, start_install: null,
        },
        {
            id: 3, job: 555, release: '551.2', description: 'Extra budget', install_hrs: 14,
            budget_install_hrs: 0, additional_install_hrs: 14, additional_install_note: 'Test',
            stage: 'Weld Start', installer: 'Saul 1', start_install: null,
        },
    ],
};

const mount = async (props = {}) => {
    const utils = render(<SplicesPane releaseId={1} onOpenRelease={vi.fn()} {...props} />);
    await screen.findByTestId('hours-bar');
    return utils;
};

beforeEach(() => {
    api.getSplices.mockReset();
    api.getRelease.mockReset();
    api.getSplices.mockResolvedValue(SUMMARY);
    api.getRelease.mockImplementation((id) => Promise.resolve({ id, Stage: 'Released' }));
});

describe('SplicesPane hours math', () => {
    it('headlines the group total the server sent', async () => {
        await mount();
        expect(screen.getByText('26 hrs')).toBeInTheDocument();
        expect(screen.getByText(/12 from the budget pool, 14 additional/)).toBeInTheDocument();
    });

    it('draws one continuous bar weighted by hours: original | splices | additional', async () => {
        await mount();
        const bar = within(screen.getByTestId('hours-bar')).getByRole('img');
        expect(bar).toHaveAccessibleName('Install hours: 2 left on 555-551, 10 spliced off, 14 additional');
        const [own, spliceGroup, addl] = Array.from(bar.children);
        expect(own).toHaveStyle({ flex: '2 1 0%' });
        expect(own).toHaveTextContent('2');
        expect(spliceGroup).toHaveStyle({ flex: '10 1 0%' });
        // Only the splice that drew budget hours gets a slice; 551.2 drew 0.
        expect(spliceGroup.children).toHaveLength(1);
        expect(spliceGroup.children[0]).toHaveTextContent('10555-551.1');
        expect(addl).toHaveStyle({ flex: '14 1 0%' });
        expect(addl).toHaveTextContent('+14');
    });

    it('leaves splices with no budget hours out of the bar legend', async () => {
        await mount();
        const legend = screen.getByTestId('hours-bar');
        expect(legend).toHaveTextContent('555-551.1 10');
        expect(legend).not.toHaveTextContent('555-551.2 0');
        expect(screen.queryByTestId('hours-ledger')).toBeNull();
    });

    it('table is numbers only: budget sums straight to the pool, additional beside it', async () => {
        await mount();
        const table = within(screen.getByTestId('group-table'));
        expect(table.getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
            'Release', 'Description', 'Stage', 'Installer', 'Budget Hours', 'Additional Hours',
        ]);
        const rows = table.getAllByRole('row');
        const cells = (row) => within(row).getAllByRole('cell').map((c) => c.textContent.trim());
        // header, original, 551.1, 551.2, subtotal
        expect(rows).toHaveLength(5);
        expect(cells(rows[1]).slice(4)).toEqual(['2', '0']);
        expect(cells(rows[2]).slice(4)).toEqual(['10', '0']);
        expect(cells(rows[3]).slice(4)).toEqual(['0', '14']);
        expect(cells(rows[4]).slice(4)).toEqual(['12', '14']);
        expect(rows[1]).toHaveAttribute('aria-current', 'true');
        // No hour controls in the table.
        expect(table.queryByRole('button', { name: /additional hours/i })).toBeNull();
    });

    it('reads blank hours as 0, never a dash', async () => {
        api.getSplices.mockResolvedValue({
            ...SUMMARY,
            parent: { ...SUMMARY.parent, fab_hrs: null },
            splices: [{ ...SUMMARY.splices[0], budget_install_hrs: null, install_hrs: null, additional_install_hrs: null }],
        });
        await mount();
        const rows = within(screen.getByTestId('group-table')).getAllByRole('row');
        expect(within(rows[2]).getAllByRole('cell').map((c) => c.textContent.trim()).slice(4)).toEqual(['0', '0']);
    });

    it('opens another release of the group from its number, never the one being viewed', async () => {
        const onOpenRelease = vi.fn();
        await mount({ onOpenRelease });
        fireEvent.click(screen.getByRole('button', { name: '555-551.1' }));
        expect(onOpenRelease).toHaveBeenCalledWith(2);
        expect(screen.queryByRole('button', { name: '555-551' })).toBeNull();
    });

    it('opens a row in the side panel, and closes it again', async () => {
        await mount();
        expect(screen.queryByTestId('release-peek')).toBeNull();
        const rows = within(screen.getByTestId('group-table')).getAllByRole('row');
        fireEvent.click(rows[3]);                                     // 555-551.2
        const peek = await screen.findByTestId('release-peek');
        expect(rows[3]).toHaveAttribute('aria-selected', 'true');
        expect(within(peek).getByText('555-551.2')).toBeInTheDocument();
        expect(within(peek).getByText('Extra budget')).toBeInTheDocument();
        expect(api.getRelease).toHaveBeenCalledWith(3);
        const body = await within(peek).findByTestId('details-body');
        expect(body).toHaveAttribute('data-release-id', '3');
        expect(body).toHaveAttribute('data-compact', 'true');

        fireEvent.click(within(peek).getByRole('button', { name: 'Close details' }));
        expect(screen.queryByTestId('release-peek')).toBeNull();

        // Clicking the selected row again also closes it.
        fireEvent.click(rows[2]);
        await screen.findByTestId('release-peek');
        fireEvent.click(rows[2]);
        expect(screen.queryByTestId('release-peek')).toBeNull();
    });

    it('opens the full release from the panel, and the number never just selects the row', async () => {
        const onOpenRelease = vi.fn();
        await mount({ onOpenRelease });
        fireEvent.click(screen.getByRole('button', { name: '555-551.1' }));
        expect(onOpenRelease).toHaveBeenCalledWith(2);
        expect(screen.queryByTestId('release-peek')).toBeNull();

        fireEvent.click(within(screen.getByTestId('group-table')).getAllByRole('row')[3]);
        const peek = await screen.findByTestId('release-peek');
        fireEvent.click(within(peek).getByRole('button', { name: 'Open' }));
        expect(onOpenRelease).toHaveBeenCalledWith(3);
    });

    it('offers no Open link for the release being viewed', async () => {
        await mount();
        fireEvent.click(within(screen.getByTestId('group-table')).getAllByRole('row')[1]);
        const peek = await screen.findByTestId('release-peek');
        expect(within(peek).queryByRole('button', { name: 'Open' })).toBeNull();
    });

    it('says so when the row no longer exists', async () => {
        api.getRelease.mockResolvedValue(null);
        await mount();
        fireEvent.click(within(screen.getByTestId('group-table')).getAllByRole('row')[2]);
        expect(await screen.findByRole('alert')).toHaveTextContent('That release no longer exists');
    });

    it('reports the splice count for the tab badge', async () => {
        const onCount = vi.fn();
        await mount({ onCount });
        expect(onCount).toHaveBeenCalledWith(2);
    });
});

describe('SplicesPane without a pool', () => {
    it('says so instead of drawing a bar', async () => {
        api.getSplices.mockResolvedValue({
            ...SUMMARY,
            total_install_hrs: null, allocated_install_hrs: 0, remaining_install_hrs: null,
            additional_install_hrs: 0, group_install_hrs: null,
            parent: { ...SUMMARY.parent, install_hrs: null },
            splices: [],
        });
        render(<SplicesPane releaseId={1} />);
        expect(await screen.findByText('No install hours on 555-551')).toBeInTheDocument();
        expect(screen.queryByTestId('hours-bar')).toBeNull();
        expect(screen.getByText(/No splices yet/)).toBeInTheDocument();
    });
});
