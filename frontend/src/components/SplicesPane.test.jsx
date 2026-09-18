/**
 * The Splices tab after its facelift (Design canvas "Splices Tab Facelift", Option A).
 *
 * What these protect: every hours number on the tab is the server's, read straight off the
 * pool summary, and the three readings agree — the bar's segments, the ledger's lines and the
 * table's subtotal all say the same 12-hour pool, 10 spliced, 2 left, +14 additional, 26 total
 * that the 555-551 screenshot showed. The original's Install cell is what it still installs
 * ITSELF (2), never its gross 12, so the Install column sums to the group total.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';

const api = vi.hoisted(() => ({
    getSplices: vi.fn(),
    updateSpliceAdditionalHours: vi.fn(),
}));
vi.mock('../services/jobsApi', () => ({ jobsApi: api }));
vi.mock('./SpliceReleaseModal', () => ({ SpliceReleaseModal: () => <div data-testid="splice-modal" /> }));

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
    api.updateSpliceAdditionalHours.mockReset();
    api.getSplices.mockResolvedValue(SUMMARY);
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

    it('ledger reads pool − splices = left, + additional = total', async () => {
        await mount();
        const ledger = within(screen.getByTestId('hours-ledger'));
        expect(ledger.getByText('− 10')).toBeInTheDocument();
        expect(ledger.getByText('− 0')).toBeInTheDocument();
        expect(ledger.getByText('Left on 555-551').nextSibling.nextSibling).toHaveTextContent('2');
        expect(ledger.getByText('+ 14')).toBeInTheDocument();
        expect(ledger.getByText('Group total install hrs').parentElement).toHaveTextContent('26');
    });

    it('table shows the original installing what it still has itself, and the subtotal adds up', async () => {
        await mount();
        const rows = within(screen.getByTestId('group-table')).getAllByRole('row');
        const cells = (row) => within(row).getAllByRole('cell').map((c) => c.textContent.trim());
        // header, original, 551.1, 551.2, subtotal
        expect(rows).toHaveLength(5);
        expect(cells(rows[1]).slice(4)).toEqual(['2 of 12', '—', '2', '12']);
        expect(cells(rows[2]).slice(4)).toEqual(['10', '+ Add', '10', '—']);
        expect(cells(rows[3]).slice(4)).toEqual(['0', '+14Edit', '14', '—']);
        expect(cells(rows[4]).slice(4)).toEqual(['12', '+14', '26', '12']);
        expect(rows[1]).toHaveAttribute('aria-current', 'true');
    });

    it('opens another release of the group from its number, never the one being viewed', async () => {
        const onOpenRelease = vi.fn();
        await mount({ onOpenRelease });
        fireEvent.click(screen.getByRole('button', { name: '555-551.1' }));
        expect(onOpenRelease).toHaveBeenCalledWith(2);
        expect(screen.queryByRole('button', { name: '555-551' })).toBeNull();
    });

    it('edits additional hours in place and refetches', async () => {
        api.updateSpliceAdditionalHours.mockResolvedValue({});
        const onChanged = vi.fn();
        await mount({ onChanged });
        fireEvent.click(screen.getByRole('button', { name: 'Edit additional hours for 555-551.2' }));
        const input = screen.getByLabelText('Additional install hours for 555-551.2');
        fireEvent.change(input, { target: { value: '16' } });
        fireEvent.click(screen.getByRole('button', { name: 'Save' }));
        await waitFor(() => expect(api.updateSpliceAdditionalHours).toHaveBeenCalledWith(3, {
            additional_install_hrs: 16, additional_install_note: null,
        }));
        await waitFor(() => expect(api.getSplices).toHaveBeenCalledTimes(2));
        expect(onChanged).toHaveBeenCalled();
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
