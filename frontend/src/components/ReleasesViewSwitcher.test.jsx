// Router-aware tests for the Table/Timeline segmented switcher: active segment
// derives from the location, clicks navigate, and old ?view=timeline deep links
// still resolve to the Timeline segment. (Board view removed 2026-07-12.)
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import ReleasesViewSwitcher from './ReleasesViewSwitcher.jsx';

function LocationProbe() {
    const location = useLocation();
    return <div data-testid="location">{location.pathname + location.search}</div>;
}

function renderAt(initialEntry) {
    return render(
        <MemoryRouter initialEntries={[initialEntry]}>
            <Routes>
                <Route path="*" element={<><ReleasesViewSwitcher /><LocationProbe /></>} />
            </Routes>
        </MemoryRouter>
    );
}

const tab = (name) => screen.getByRole('tab', { name });

describe('ReleasesViewSwitcher', () => {
    it('renders the two views (Board removed)', () => {
        renderAt('/job-log');
        expect(tab('Table')).toBeInTheDocument();
        expect(tab('Timeline')).toBeInTheDocument();
        expect(screen.queryByRole('tab', { name: 'Board' })).not.toBeInTheDocument();
    });

    it('marks Table active on /job-log', () => {
        renderAt('/job-log');
        expect(tab('Table')).toHaveAttribute('aria-selected', 'true');
        expect(tab('Timeline')).toHaveAttribute('aria-selected', 'false');
    });

    it('marks Timeline active on /pm-board', () => {
        renderAt('/pm-board');
        expect(tab('Timeline')).toHaveAttribute('aria-selected', 'true');
        expect(tab('Table')).toHaveAttribute('aria-selected', 'false');
    });

    it('marks Timeline active on the legacy ?view=timeline deep link', () => {
        renderAt('/pm-board?view=timeline');
        expect(tab('Timeline')).toHaveAttribute('aria-selected', 'true');
        expect(tab('Table')).toHaveAttribute('aria-selected', 'false');
    });

    it('navigates between views on click', () => {
        renderAt('/job-log');
        fireEvent.click(tab('Timeline'));
        expect(screen.getByTestId('location')).toHaveTextContent('/pm-board');
        fireEvent.click(tab('Table'));
        expect(screen.getByTestId('location')).toHaveTextContent('/job-log');
    });

    it('does not re-navigate when the active view is clicked', () => {
        renderAt('/pm-board?view=timeline');
        fireEvent.click(tab('Timeline'));
        // Legacy query string preserved because no navigation occurred.
        expect(screen.getByTestId('location')).toHaveTextContent('/pm-board?view=timeline');
    });
});
