/**
 * ASAP is a flag, never a date. Toggling it — on OR off — must not drop the Start Install date.
 *
 * The bug this pins: the release hub turned ASAP on by setting the flag and then saving the
 * install date, but handed that save no date. The server reads a dateless save as "clear the
 * date", so ticking ASAP on a hard-dated release wiped the date. Two layers guard it:
 *   - the modal only asks for a date write when the date actually needs writing, and
 *   - setAsapAndAssign never sends a dateless save.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const api = vi.hoisted(() => ({
    getInstallerTeams: vi.fn(() => Promise.resolve([])),
    setStartInstallAsap: vi.fn(() => Promise.resolve({})),
    updateStartInstall: vi.fn(() => Promise.resolve({})),
}));
vi.mock('../services/jobsApi', () => ({ jobsApi: api }));

import { StartInstallDateModal } from './StartInstallDateModal';
import { setAsapAndAssign } from '../utils/asap';

const HARD_DATE = '2026-09-22';

function renderModal(over = {}) {
    const props = {
        isOpen: true,
        onClose: vi.fn(),
        currentDate: HARD_DATE,
        currentShipDate: null,
        currentInstaller: '',
        onSave: vi.fn(),
        onSaveShipDate: vi.fn(),
        onClearHardDate: vi.fn(),
        onSetAsap: vi.fn(),
        onClearAsap: vi.fn(),
        jobNumber: 560,
        releaseNumber: '101',
        startInstallFormulaTF: false,
        isAsap: false,
        stage: 'Paint Start',
        ...over,
    };
    render(<StartInstallDateModal {...props} />);
    return props;
}

beforeEach(() => {
    vi.clearAllMocks();
});

describe('StartInstallDateModal — ASAP toggle keeps the date', () => {
    it('turning ASAP on over an unchanged hard date asks for no date write', () => {
        const props = renderModal();
        fireEvent.click(screen.getByRole('checkbox'));
        fireEvent.click(screen.getByRole('button', { name: 'Set ASAP' }));

        expect(props.onSetAsap).toHaveBeenCalledTimes(1);
        // (installer unchanged, date unchanged) — nothing for the date endpoint to do.
        expect(props.onSetAsap).toHaveBeenCalledWith(undefined, undefined);
        expect(props.onSave).not.toHaveBeenCalled();
    });

    it('turning ASAP on over a formula date saves that date as hard', () => {
        const props = renderModal({ startInstallFormulaTF: true });
        fireEvent.click(screen.getByRole('checkbox'));
        fireEvent.click(screen.getByRole('button', { name: 'Set ASAP' }));

        expect(props.onSetAsap).toHaveBeenCalledWith(undefined, HARD_DATE);
    });

    it('the checkbox can be unticked on an ASAP row, and Save clears the flag only', () => {
        const props = renderModal({ isAsap: true });
        const box = screen.getByRole('checkbox');
        expect(box).toBeChecked();
        expect(box).not.toBeDisabled();

        fireEvent.click(box);
        fireEvent.click(screen.getByRole('button', { name: 'Save' }));

        expect(props.onClearAsap).toHaveBeenCalledTimes(1);
        // No date/installer edit alongside it → no install write at all, so the date can't move.
        expect(props.onSave).not.toHaveBeenCalled();
        expect(props.onClearHardDate).not.toHaveBeenCalled();
    });
});

describe('setAsapAndAssign — never a dateless save', () => {
    it('with no date and no installer, sets the flag and writes nothing else', async () => {
        const ok = await setAsapAndAssign(560, '101', undefined, undefined);

        expect(ok).toBe(true);
        expect(api.setStartInstallAsap).toHaveBeenCalledWith(560, '101', true);
        expect(api.updateStartInstall).not.toHaveBeenCalled();
    });

    it('with a date, writes exactly that date', async () => {
        await setAsapAndAssign(560, '101', undefined, HARD_DATE);

        expect(api.updateStartInstall).toHaveBeenCalledWith(560, '101', HARD_DATE, undefined);
    });
});
