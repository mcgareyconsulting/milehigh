/**
 * The banner is a fixed overlay that shares the top of the viewport with the notification pod
 * and the Carmen launcher (both live in the upper-right corner). It used to be a full-bleed
 * strip at the same z as that chrome, so the pod painted over its Reload/Dismiss buttons.
 * These tests pin the geometry that keeps the two apart.
 */
import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import UpdateAvailableBanner from './UpdateAvailableBanner';

vi.mock('../utils/versionCheck', () => ({
    checkVersion: vi.fn(),
}));

import { checkVersion } from '../utils/versionCheck';

const wrap = () => screen.getByTestId('update-available-banner-wrap');
const pill = () => screen.getByTestId('update-available-banner');

describe('UpdateAvailableBanner', () => {
    beforeEach(() => {
        checkVersion.mockReset();
        sessionStorage.clear();
    });
    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('renders nothing when the client is current', async () => {
        checkVersion.mockResolvedValue({ stale: false, server: '1.50' });
        render(<UpdateAvailableBanner />);
        await waitFor(() => expect(checkVersion).toHaveBeenCalled());
        expect(screen.queryByTestId('update-available-banner')).not.toBeInTheDocument();
    });

    it('shows the reload control when the client is stale', async () => {
        checkVersion.mockResolvedValue({ stale: true, server: '1.51' });
        render(<UpdateAvailableBanner />);
        expect(await screen.findByRole('button', { name: 'Reload' })).toBeInTheDocument();
    });

    it('is a centred pill, not a full-bleed strip', async () => {
        checkVersion.mockResolvedValue({ stale: true, server: '1.51' });
        render(<UpdateAvailableBanner />);
        await screen.findByTestId('update-available-banner');
        expect(wrap().className).toContain('justify-center');
        // A full-bleed bar would stretch the pill edge to edge and put it under the corner pod.
        expect(pill().classList.contains('w-full')).toBe(false);
        expect(pill().classList.contains('inset-x-0')).toBe(false);
        expect(pill().className).toContain('rounded-full');
    });

    it('reserves the notification-pod gutter on the right so it cannot slide under the bell', async () => {
        checkVersion.mockResolvedValue({ stale: true, server: '1.51' });
        render(<UpdateAvailableBanner />);
        await screen.findByTestId('update-available-banner');
        expect(wrap().style.paddingRight).toContain('--notif-pod-gutter');
    });

    it('sits above the top bar and the pod (z-50) but below their dropdowns', async () => {
        checkVersion.mockResolvedValue({ stale: true, server: '1.51' });
        render(<UpdateAvailableBanner />);
        await screen.findByTestId('update-available-banner');
        const z = wrap().className.match(/z-\[(\d+)\]/);
        expect(z).not.toBeNull();
        expect(Number(z[1])).toBeGreaterThan(50);
        expect(Number(z[1])).toBeLessThan(60);
    });

    it('lets clicks through the empty strip either side of the pill', async () => {
        checkVersion.mockResolvedValue({ stale: true, server: '1.51' });
        render(<UpdateAvailableBanner />);
        await screen.findByTestId('update-available-banner');
        expect(wrap().className).toContain('pointer-events-none');
        expect(pill().className).toContain('pointer-events-auto');
    });

    it('dismisses without reloading', async () => {
        checkVersion.mockResolvedValue({ stale: true, server: '1.51' });
        render(<UpdateAvailableBanner />);
        const dismiss = await screen.findByRole('button', { name: 'Dismiss update notification' });
        dismiss.click();
        await waitFor(() =>
            expect(screen.queryByTestId('update-available-banner')).not.toBeInTheDocument(),
        );
    });

    it('stays dismissed when the same pending version is re-confirmed on tab return', async () => {
        // The original bug: every visibilitychange re-ran the check and cleared `dismissed`, so
        // switching tabs and back resurrected a banner the user had already waved off.
        checkVersion.mockResolvedValue({ stale: true, server: '1.51' });
        render(<UpdateAvailableBanner />);
        (await screen.findByRole('button', { name: 'Dismiss update notification' })).click();
        await waitFor(() =>
            expect(screen.queryByTestId('update-available-banner')).not.toBeInTheDocument(),
        );

        const callsBefore = checkVersion.mock.calls.length;
        await act(async () => {
            document.dispatchEvent(new Event('visibilitychange'));
        });
        await waitFor(() => expect(checkVersion.mock.calls.length).toBeGreaterThan(callsBefore));
        expect(screen.queryByTestId('update-available-banner')).not.toBeInTheDocument();
    });

    it('comes back when the server moves to a version the user has not dismissed', async () => {
        checkVersion.mockResolvedValue({ stale: true, server: '1.51' });
        render(<UpdateAvailableBanner />);
        (await screen.findByRole('button', { name: 'Dismiss update notification' })).click();
        await waitFor(() =>
            expect(screen.queryByTestId('update-available-banner')).not.toBeInTheDocument(),
        );

        checkVersion.mockResolvedValue({ stale: true, server: '1.52' });
        await act(async () => {
            document.dispatchEvent(new Event('visibilitychange'));
        });
        expect(await screen.findByTestId('update-available-banner')).toBeInTheDocument();
    });

    it('carries a dismissal across a remount within the same tab', async () => {
        checkVersion.mockResolvedValue({ stale: true, server: '1.51' });
        const first = render(<UpdateAvailableBanner />);
        (await screen.findByRole('button', { name: 'Dismiss update notification' })).click();
        await waitFor(() =>
            expect(screen.queryByTestId('update-available-banner')).not.toBeInTheDocument(),
        );
        first.unmount();

        render(<UpdateAvailableBanner />);
        await waitFor(() => expect(checkVersion).toHaveBeenCalledTimes(2));
        expect(screen.queryByTestId('update-available-banner')).not.toBeInTheDocument();
    });
});
