/**
 * Corner color is the scan; the accessible name is the actual billing tag.
 * Untagged rows stay unmarked so a missing tag is not painted as non-contracted.
 */
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';

import { BillingCornerTag } from './BillingCornerTag';

function corner(tag) {
    const { container } = render(<BillingCornerTag tag={tag} />);
    return container.querySelector('[data-billing-corner]');
}

describe('BillingCornerTag', () => {
    it('draws a green bottom-right triangle for contracted work', () => {
        const el = corner('contracted');
        expect(el).toHaveAttribute('data-billing-corner', 'contracted');
        expect(el).toHaveAttribute('aria-label', 'Contracted');
        expect(el.querySelector('polygon')).toHaveAttribute('fill', '#16a34a');
        expect(el.querySelector('polygon')).toHaveAttribute('points', '12,12 12,0 0,12');
    });

    it('draws a yellow triangle for Change Order and MHMW Cost, named apart', () => {
        const changeOrder = corner('change_order');
        const mhmw = corner('mhmw_cost');
        expect(changeOrder).toHaveAttribute('data-billing-corner', 'other');
        expect(changeOrder).toHaveAttribute('aria-label', 'Change Order');
        expect(mhmw).toHaveAttribute('aria-label', 'MHMW Cost');
        expect(changeOrder.querySelector('polygon')).toHaveAttribute('fill', '#eab308');
        expect(mhmw.querySelector('polygon')).toHaveAttribute('fill', '#eab308');
    });

    it('draws nothing when the release has no billing tag', () => {
        expect(corner(null)).toBeNull();
        expect(corner('')).toBeNull();
        expect(corner(undefined)).toBeNull();
    });
});
