/**
 * The + Splice form's zero-hour path (training handout 2026-09-21, "Watch for: zero-hour
 * splice bug"). A drop-ship or material-only splice carries no install hours and no installer;
 * the form used to hold Create disabled until hours were typed, so PMs typed 0.5 to get past
 * it. Now no hours means a zero-hour splice: the form says so, waives the installer, and sends
 * the create with both blank. Hours typed back in bring the installer requirement back.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const api = vi.hoisted(() => ({
    getSplices: vi.fn(),
    getInstallerTeams: vi.fn(),
    createSplice: vi.fn(),
}));
vi.mock('../services/jobsApi', () => ({ jobsApi: api }));

import { SpliceReleaseModal } from './SpliceReleaseModal';

const POOL = {
    parent_id: 1, job: 555, release: '551', next_splice_number: '551.3',
    total_install_hrs: 12, allocated_install_hrs: 10, remaining_install_hrs: 2,
    splices: [],
};

const open = () => render(
    <SpliceReleaseModal
        isOpen
        onClose={() => {}}
        parentId={1}
        jobNumber={555}
        releaseNumber="551"
        jobName="Test"
        description="Test"
        pool={POOL}
    />,
);

beforeEach(() => {
    api.getSplices.mockReset().mockResolvedValue(POOL);
    api.getInstallerTeams.mockReset().mockResolvedValue([{ name: 'Saul 1' }]);
    api.createSplice.mockReset().mockResolvedValue({ splice: { id: 9 } });
});

describe('SpliceReleaseModal zero-hour splice', () => {
    it('creates with no hours and no installer, and says why that is fine', async () => {
        open();
        fireEvent.change(screen.getByLabelText(/New description/), { target: { value: 'Embeds — drop ship' } });
        expect(screen.getByTestId('zero-hour-note')).toHaveTextContent(/no install hours, so no installer/);

        const create = screen.getByRole('button', { name: 'Create 555-551.3' });
        expect(create).toBeEnabled();
        fireEvent.click(create);
        await waitFor(() => expect(api.createSplice).toHaveBeenCalledTimes(1));
        expect(api.createSplice.mock.calls[0][1]).toMatchObject({
            description: 'Embeds — drop ship', installer: null, install_hrs: null, additional_install_hrs: null,
        });
    });

    it('brings the installer requirement back as soon as hours are typed', async () => {
        open();
        fireEvent.change(screen.getByLabelText(/New description/), { target: { value: 'Level 3 rails' } });
        fireEvent.change(screen.getByLabelText(/Budget install hours/), { target: { value: '2' } });
        expect(screen.queryByTestId('zero-hour-note')).toBeNull();
        expect(screen.getByRole('button', { name: 'Create 555-551.3' })).toBeDisabled();

        await waitFor(() => expect(screen.getByRole('option', { name: 'Saul 1' })).toBeInTheDocument());
        fireEvent.change(screen.getByLabelText(/Installer/), { target: { value: 'Saul 1' } });
        expect(screen.getByRole('button', { name: 'Create 555-551.3' })).toBeEnabled();
    });
});
