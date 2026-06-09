// Router-aware tests for the Table/Board/Timeline segmented switcher:
// active segment derives from the location, clicks navigate, and the
// timeline deep link (?view=timeline) is honored.
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
    it('renders the three views', () => {
        renderAt('/job-log');
        expect(tab('Table')).toBeInTheDocument();
        expect(tab('Board')).toBeInTheDocument();
        expect(tab('Timeline')).toBeInTheDocument();
    });

    it('marks Table active on /job-log', () => {
        renderAt('/job-log');
        expect(tab('Table')).toHaveAttribute('aria-selected', 'true');
        expect(tab('Board')).toHaveAttribute('aria-selected', 'false');
    });

    it('marks Board active on /pm-board without a view param', () => {
        renderAt('/pm-board');
        expect(tab('Board')).toHaveAttribute('aria-selected', 'true');
        expect(tab('Timeline')).toHaveAttribute('aria-selected', 'false');
    });

    it('marks Timeline active on the ?view=timeline deep link', () => {
        renderAt('/pm-board?view=timeline');
        expect(tab('Timeline')).toHaveAttribute('aria-selected', 'true');
        expect(tab('Board')).toHaveAttribute('aria-selected', 'false');
    });

    it('navigates between views on click', () => {
        renderAt('/job-log');
        fireEvent.click(tab('Timeline'));
        expect(screen.getByTestId('location')).toHaveTextContent('/pm-board?view=timeline');
        fireEvent.click(tab('Board'));
        expect(screen.getByTestId('location')).toHaveTextContent('/pm-board');
        fireEvent.click(tab('Table'));
        expect(screen.getByTestId('location')).toHaveTextContent('/job-log');
    });

    it('does not re-navigate when the active view is clicked', () => {
        renderAt('/pm-board?view=timeline');
        fireEvent.click(tab('Timeline'));
        expect(screen.getByTestId('location')).toHaveTextContent('/pm-board?view=timeline');
    });
});
