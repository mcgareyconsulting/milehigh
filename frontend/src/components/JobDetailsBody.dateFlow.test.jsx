/**
 * The date-flow hero's alignment invariant.
 *
 * A HARD/ASAP flag used to grow its own cell's label row, pushing that date below its neighbours,
 * and the arrows centred on the stretched cell so they floated between the two rows instead of
 * pointing along the dates. Both are geometry bugs, so these assert geometry: every cell's label
 * row and value row are the same fixed height, whether or not the cell carries a flag.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';

vi.mock('../services/jobsApi', () => ({
    jobsApi: {
        getMaterialOrders: () => Promise.resolve([]),
        updateJobFields: vi.fn(),
    },
}));

import { JobDetailsBody } from './JobDetailsBody';

const job = (over = {}) => ({
    id: 1,
    'Job #': 560,
    'Release #': '923',
    'Released': '2026-03-06',
    'Ship Date': '2026-08-12',
    'Start install': '2026-08-22',
    'Comp. ETA': '2026-08-24',
    'Stage': 'Paint Complete',
    start_install_formulaTF: false,   // → HARD flag
    start_install_asap: false,
    start_install_no_color: false,
    ...over,
});

/** The label row of the cell whose label text is `name`. */
const labelRow = (name) => screen.getByText(name).closest('div');
const valueRow = (name) => labelRow(name).nextElementSibling;

describe('date-flow hero alignment', () => {
    it('gives every label row the same fixed height, flag or no flag', () => {
        render(<JobDetailsBody job={job()} />);
        // Start Install carries the HARD flag; the others do not.
        expect(screen.getByText('HARD')).toBeInTheDocument();

        const rows = ['Released', 'Ship Date', 'Start Install', 'Comp. ETA'].map(labelRow);
        const heights = rows.map((r) => r.style.height);
        expect(new Set(heights).size).toBe(1);
        expect(heights[0]).not.toBe('');       // an explicit height, not content-driven
    });

    it('gives every value row the same fixed height, so the dates share a baseline', () => {
        render(<JobDetailsBody job={job()} />);
        const heights = ['Released', 'Ship Date', 'Start Install', 'Comp. ETA']
            .map((n) => valueRow(n).style.height);
        expect(new Set(heights).size).toBe(1);
        expect(heights[0]).not.toBe('');
    });

    it('keeps the label row from wrapping when a flag is present', () => {
        render(<JobDetailsBody job={job()} />);
        expect(labelRow('Start Install').style.flexWrap).toBe('nowrap');
    });

    it('holds the same geometry for an ASAP release', () => {
        render(<JobDetailsBody job={job({ start_install_asap: true })} />);
        // An ASAP release reads "ASAP" twice — the flag pill and the value it replaces the date
        // with — so scope the flag assertion to the label row.
        const flag = within(labelRow('Start Install')).getByText('ASAP');
        expect(flag).toHaveClass('jl-flag-red');
        const heights = ['Released', 'Ship Date', 'Start Install', 'Comp. ETA']
            .map((n) => labelRow(n).style.height);
        expect(new Set(heights).size).toBe(1);
    });

    it('holds the same geometry when no flag applies at all', () => {
        render(<JobDetailsBody job={job({ start_install_formulaTF: true })} />);
        expect(screen.queryByText('HARD')).not.toBeInTheDocument();
        const labels = ['Released', 'Ship Date', 'Start Install', 'Comp. ETA'].map((n) => labelRow(n).style.height);
        const values = ['Released', 'Ship Date', 'Start Install', 'Comp. ETA'].map((n) => valueRow(n).style.height);
        expect(new Set(labels).size).toBe(1);
        expect(new Set(values).size).toBe(1);
    });

    it('offsets each arrow by exactly the label row, so it sits on the value line', () => {
        const { container } = render(<JobDetailsBody job={job()} />);
        const arrows = [...container.querySelectorAll('svg')].filter(
            (svg) => svg.getAttribute('viewBox') === '0 0 18 10'
        );
        expect(arrows).toHaveLength(3);   // Released → Ship → Start Install → Comp. ETA

        const labelH = labelRow('Released').style.height;
        const valueH = valueRow('Released').style.height;
        for (const svg of arrows) {
            const arrowValueRow = svg.parentElement;
            const spacer = arrowValueRow.previousElementSibling;
            expect(spacer.style.height).toBe(labelH);
            expect(arrowValueRow.style.height).toBe(valueH);
        }
    });
});
