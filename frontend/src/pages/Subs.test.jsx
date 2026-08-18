// Subs → Invoice Paid: the read-only Job Log columns (Install Prog, Budget) and
// the release-name hyperlink that opens the same hub modal the Job Log opens.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

vi.mock('../utils/auth', () => ({
    checkAuth: vi.fn(() => Promise.resolve({ is_admin: true })),
}));

vi.mock('../services/subsApi', () => ({
    fetchSubsReleases: vi.fn(),
    updateInstallerInvoicePaid: vi.fn(() => Promise.resolve({})),
    updateInstallerInvoiceProgress: vi.fn(() => Promise.resolve({})),
    updateInstallerInvoiceNumbers: vi.fn(() => Promise.resolve({})),
}));

// The hub itself is covered by ReleaseHubModal.test.jsx — here we only care that
// the page hands it the clicked release row.
const hubProps = { current: null };
vi.mock('../components/ReleaseHubModal', () => ({
    ReleaseHubModal: (props) => {
        hubProps.current = props;
        return props.isOpen ? <div data-testid="hub">{props.job?.description}</div> : null;
    },
}));

import Subs from './Subs.jsx';
import { fetchSubsReleases } from '../services/subsApi';

const row = (over = {}) => ({
    id: 11,
    job: 560,
    release: '923',
    job_name: 'Alta Metro',
    description: 'Bldg C stairs',
    installer: 'Saul 2',
    stage: 'Install Start',
    start_install: '2026-06-01',
    job_comp: '75',
    install_hrs: 12.5,
    is_archived: false,
    installer_invoice_paid: false,
    installer_invoice_progress: null,
    installer_invoice_numbers: '',
    ...over,
});

const load = (releases) => {
    fetchSubsReleases.mockResolvedValue({
        releases,
        installers: [...new Set(releases.map((r) => r.installer))],
    });
    return render(<Subs />);
};

const cellsOf = async (description) => {
    const cell = await screen.findByText(description);
    return within(cell.closest('tr')).getAllByRole('cell');
};

describe('Subs — Invoice Paid columns', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        hubProps.current = null;
    });

    it('shows the Job Log install progress as its own read-only column', async () => {
        load([row()]);
        const cells = await cellsOf('Bldg C stairs');
        // Job, Rel, Job name, Description, Stage, Start install, Status, Install Prog
        expect(cells[7]).toHaveTextContent('75%');
        // The editable installer_invoice_progress input is a separate column.
        expect(screen.getByLabelText('Progress percent')).toHaveValue('');
    });

    it('renders X and — for the non-numeric Job Comp values', async () => {
        load([
            row({ job_comp: 'X' }),
            row({ id: 12, release: '924', description: 'Bldg D rails', job_comp: null }),
        ]);
        expect((await cellsOf('Bldg C stairs'))[7]).toHaveTextContent('X');
        expect((await cellsOf('Bldg D rails'))[7]).toHaveTextContent('—');
    });

    it('computes Budget as Install Hrs × $55.00', async () => {
        load([row()]);
        // 12.5 hrs × $55 = $687.50
        expect((await cellsOf('Bldg C stairs'))[8]).toHaveTextContent('$687.50');
    });

    it('leaves Budget blank when the release has no install hours', async () => {
        load([row({ install_hrs: null })]);
        expect((await cellsOf('Bldg C stairs'))[8]).toHaveTextContent('—');
    });
});

describe('Subs — release hub modal', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        hubProps.current = null;
    });

    it('opens the hub from the release name with the full row', async () => {
        load([row()]);
        fireEvent.click(await screen.findByText('Bldg C stairs'));
        await waitFor(() => expect(screen.getByTestId('hub')).toBeInTheDocument());
        expect(hubProps.current.job).toMatchObject({ job: 560, release: '923' });
        expect(hubProps.current.releaseId).toBe(11);
        expect(hubProps.current.initialTab).toBe('details');
    });

    it('opens the same hub from the job name', async () => {
        load([row()]);
        fireEvent.click(await screen.findByText('Alta Metro'));
        await waitFor(() => expect(screen.getByTestId('hub')).toBeInTheDocument());
        expect(hubProps.current.job).toMatchObject({ job: 560, release: '923' });
    });

    it('stays closed until a release is clicked', async () => {
        load([row()]);
        await screen.findByText('Bldg C stairs');
        expect(screen.queryByTestId('hub')).not.toBeInTheDocument();
    });
});

describe('Subs — Est. Billable', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        hubProps.current = null;
    });

    it('bills the install-progress share of the budget', async () => {
        load([row({ job_comp: '90', install_hrs: 10 })]);
        const cells = await cellsOf('Bldg C stairs');
        // 10 hrs × $55 = $550 budget; 90% install prog = $495.00 billable.
        expect(cells[8]).toHaveTextContent('$550.00');
        expect(cells[9]).toHaveTextContent('$495.00');
    });

    it('reads job_comp with the percent sign already in it', async () => {
        // How the Job Log actually stores it (free text, e.g. 410-107 = "90%").
        load([row({ job_comp: '90%', install_hrs: 34.9 })]);
        const cells = await cellsOf('Bldg C stairs');
        expect(cells[7]).toHaveTextContent('90%');
        expect(cells[8]).toHaveTextContent('$1,919.50');
        expect(cells[9]).toHaveTextContent('$1,727.55');
    });

    it('reads a decimal progress', async () => {
        load([row({ job_comp: '12.5%', install_hrs: 10 })]);
        expect((await cellsOf('Bldg C stairs'))[9]).toHaveTextContent('$68.75');
    });

    it('clamps over-100 progress to the full budget', async () => {
        load([row({ job_comp: '110%', install_hrs: 10 })]);
        expect((await cellsOf('Bldg C stairs'))[9]).toHaveTextContent('$550.00');
    });

    it('treats the X complete marker as 100% of the budget', async () => {
        load([row({ job_comp: 'X', install_hrs: 10 })]);
        expect((await cellsOf('Bldg C stairs'))[9]).toHaveTextContent('$550.00');
    });

    it('bills nothing at 0% but still shows the dollar figure', async () => {
        load([row({ job_comp: '0', install_hrs: 10 })]);
        expect((await cellsOf('Bldg C stairs'))[9]).toHaveTextContent('$0.00');
    });

    it('blanks — rather than $0 — when progress or hours are unknown', async () => {
        load([
            row({ job_comp: null, install_hrs: 10 }),
            row({ id: 12, release: '924', description: 'Bldg D rails', job_comp: '50', install_hrs: null }),
        ]);
        // No progress: the budget is known, what is earned of it is not.
        expect((await cellsOf('Bldg C stairs'))[9]).toHaveTextContent('—');
        // No hours: no budget to take a share of.
        expect((await cellsOf('Bldg D rails'))[9]).toHaveTextContent('—');
    });
});
