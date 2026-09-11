/**
 * Carmen's answers arrive as light markdown. Before this, `**Needs verification:**`
 * rendered as literal asterisks in the panel — these pin the renderer to the shape she
 * actually writes, using a real answer as the fixture.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { DrawingChat } from './DrawingChat';

vi.mock('../../services/jobsApi', () => ({
    jobsApi: { carmenDrawingChat: vi.fn() },
}));
import { jobsApi } from '../../services/jobsApi';

const REAL_ANSWER = [
    '8 total: 4 OK, 4 need field verification.',
    '',
    '**OK:** handrail height/graspability (1-1/4" pipe at 36"), guard height (42 1/2").',
    '',
    '**Needs verification:**',
    '- Terminal rise at base of flight (F7) — lands on existing concrete pad, see p8.',
    '- Material specs (F2/F4) — no ASTM grades on `TS` or pipe.',
].join('\n');

const ask = async (answer) => {
    jobsApi.carmenDrawingChat.mockResolvedValue({ answer, metrics: null });
    render(<DrawingChat releaseId={1} versionId={2} enabled onCite={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /Summarize this drawing set/ }));
    await screen.findAllByRole('listitem');   // the answer has rendered
};

describe('DrawingChat answer rendering', () => {
    beforeEach(() => vi.clearAllMocks());

    it('renders **bold** as bold, not as asterisks', async () => {
        await ask(REAL_ANSWER);
        const bold = screen.getByText('Needs verification:');
        expect(bold.tagName).toBe('STRONG');
        expect(document.body.textContent).not.toContain('**');
    });

    it('turns "- " lines into a real list', async () => {
        await ask(REAL_ANSWER);
        const items = screen.getAllByRole('listitem');
        expect(items).toHaveLength(2);
        expect(items[0].textContent).toContain('Terminal rise at base of flight');
        expect(document.body.textContent).not.toMatch(/^\s*- /m);
    });

    it('renders `code` spans', async () => {
        await ask(REAL_ANSWER);
        expect(screen.getByText('TS').tagName).toBe('CODE');
        expect(document.body.textContent).not.toContain('`');
    });

    it('keeps page-citation jump chips working inside a bullet', async () => {
        const onCite = vi.fn();
        jobsApi.carmenDrawingChat.mockResolvedValue({ answer: REAL_ANSWER, metrics: null });
        render(<DrawingChat releaseId={1} versionId={2} enabled onCite={onCite} />);
        await userEvent.click(screen.getByRole('button', { name: /Summarize this drawing set/ }));
        const chip = await screen.findByTitle('Jump to page 8');
        await userEvent.click(chip);
        expect(onCite).toHaveBeenCalledWith(8, null);
    });

    it('keeps inch marks and plain prose intact', async () => {
        await ask(REAL_ANSWER);
        expect(document.body.textContent).toContain('1-1/4" pipe at 36"');
        expect(document.body.textContent).toContain('8 total: 4 OK, 4 need field verification.');
    });
});
