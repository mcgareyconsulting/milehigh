/**
 * The two-line install-hours cell shared by the Job Log and Subs → Invoice Paid (T9 splices),
 * on the 555-551 group: the original 551 (12-hr pool, 10 spliced off), splice 551.1 (10 budget
 * hours) and splice 551.2 (0 budget, 14 extra). Bold on top is always the ACTUAL hours.
 */
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';

import { InstallHrsStack } from './InstallHrsStack';

const format = (v) => (v == null ? '—' : Number(v).toFixed(2));
const lines = (row) => {
    const { container } = render(<InstallHrsStack row={row} format={format} />);
    const stack = container.firstChild;
    if (!stack) return null;
    const [top, bottom] = stack.children;
    return { top, bottom };
};

const original = { id: 1, 'Install HRS': 12, spliced_install_hrs: 10, remaining_install_hrs: 2 };
const budgetSplice = { id: 2, 'Install HRS': 10, parent_release_id: 1, parent_install_hrs: 12 };
const extraSplice = {
    id: 3, 'Install HRS': 14, parent_release_id: 1, parent_install_hrs: 12, additional_install_hrs: 14,
};

describe('InstallHrsStack', () => {
    it('original: bold is what it still installs itself, below is its full pool', () => {
        const { top, bottom } = lines(original);
        expect(top).toHaveTextContent('2.00');
        expect(top).toHaveClass('font-bold');
        expect(bottom).toHaveTextContent('12.00');
    });

    it('splice: bold is its own hours, below is the group pool', () => {
        const { top, bottom } = lines(budgetSplice);
        expect(top).toHaveTextContent('10.00');
        expect(bottom.textContent).toBe('12.00');
    });

    it('additional-only splice: below reads just "extra"', () => {
        const { top, bottom } = lines(extraSplice);
        expect(top).toHaveTextContent('14.00');
        expect(bottom.textContent).toBe('extra');
    });

    it('splice with budget and extra hours shows both below', () => {
        const { top, bottom } = lines({ ...extraSplice, 'Install HRS': 8, additional_install_hrs: 3 });
        expect(top).toHaveTextContent('8.00');
        expect(bottom.textContent).toBe('12.00extra');
    });

    it('works off the Subs payload shape too', () => {
        const { top, bottom } = lines({ id: 2, install_hrs: 10, parent_release_id: 1, parent_install_hrs: 12 });
        expect(top).toHaveTextContent('10.00');
        expect(bottom.textContent).toBe('12.00');
    });

    it('renders nothing for a release outside any splice group', () => {
        expect(lines({ id: 9, 'Install HRS': 26.56 })).toBeNull();
    });
});
