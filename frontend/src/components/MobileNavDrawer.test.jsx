/**
 * The mobile nav drawer, after it absorbed the top bar's overflow.
 *
 * The top bar ran roughly 392px of content on a 390px phone — brand, version badge, search, bell,
 * avatar, theme button, hamburger — so it scrolled sideways and the HAMBURGER sat off the right
 * edge. Since the hamburger is the only way into this drawer, the nav was unreachable without
 * horizontally scrolling a header most people would not think to scroll.
 *
 * The fix moved the two set-once controls in here. What these tests protect is that nothing was
 * simply deleted on the way: the theme toggles still exist somewhere a phone can reach, and so does
 * the patch-notes entry point, which the version badge used to be the only route to.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const theme = vi.hoisted(() => ({
    isDark: false, isOldMan: false, isSidebarMode: false,
    toggleDark: vi.fn(), toggleOldMan: vi.fn(), toggleSidebarMode: vi.fn(),
}));
vi.mock('../context/ThemeContext', () => ({ useTheme: () => theme }));
vi.mock('../data/patchNotes', () => ({ CURRENT_VERSION: 'v2.0.369' }));

import MobileNavDrawer from './MobileNavDrawer';

const open = (props = {}) => render(
    <MemoryRouter>
        <MobileNavDrawer
            open
            onClose={() => {}}
            isAuthenticated
            subcontractor={null}
            isAdmin={false}
            canSeeReport={false}
            locationEnabled={false}
            locationRequesting={false}
            onLocationToggle={() => {}}
            onLogout={() => {}}
            onLogin={() => {}}
            {...props}
        />
    </MemoryRouter>
);

beforeEach(() => vi.clearAllMocks());

describe('MobileNavDrawer', () => {
    it('carries the theme toggles the top bar no longer shows on a phone', () => {
        open();
        expect(screen.getByRole('button', { name: 'Dark Mode' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Old Man Mode' })).toBeInTheDocument();
    });

    it('actually flips dark mode', () => {
        open();
        fireEvent.click(screen.getByRole('button', { name: 'Dark Mode' }));
        expect(theme.toggleDark).toHaveBeenCalled();
    });

    it('keeps a route to the patch notes, which the version badge used to own', () => {
        const onOpenPatchNotes = vi.fn();
        const onClose = vi.fn();
        open({ onOpenPatchNotes, onClose });

        const entry = screen.getByTitle("What's new — view patch notes");
        expect(entry).toHaveTextContent('v2.0.369');

        fireEvent.click(entry);
        expect(onOpenPatchNotes).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();   // the drawer gets out of the modal's way
    });

    it('omits Left Sidebar Mode, which only applies at a width this drawer never sees', () => {
        open();
        expect(screen.queryByRole('button', { name: 'Left Sidebar Mode' })).not.toBeInTheDocument();
    });

    it('shows a subcontractor no staff settings', () => {
        open({ subcontractor: { id: 1 }, isAuthenticated: false });
        expect(screen.queryByRole('button', { name: 'Dark Mode' })).not.toBeInTheDocument();
    });
});
