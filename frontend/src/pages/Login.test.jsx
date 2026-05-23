// Smoke + flow tests for the Login page (email → set-password / login branches).
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Login from './Login';

function renderLogin() {
    return render(
        <MemoryRouter>
            <Login />
        </MemoryRouter>
    );
}

function jsonResponse(body, ok = true) {
    return Promise.resolve({
        ok,
        json: () => Promise.resolve(body),
    });
}

describe('Login page', () => {
    beforeEach(() => {
        vi.stubGlobal('fetch', vi.fn());
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('mounts in the email step', async () => {
        global.fetch.mockReturnValueOnce(jsonResponse({}, false));
        renderLogin();
        expect(await screen.findByPlaceholderText('Email')).toBeInTheDocument();
    });

    it('transitions to login step when account exists with password set', async () => {
        global.fetch
            .mockReturnValueOnce(jsonResponse({}, false))
            .mockReturnValueOnce(jsonResponse({
                exists: true, needs_password_setup: false,
            }));

        renderLogin();
        const user = userEvent.setup();
        const emailInput = await screen.findByPlaceholderText('Email');
        await user.type(emailInput, 'alice@example.com');
        await user.click(screen.getByRole('button', { name: /continue/i }));

        // The login form's password placeholder appears
        await waitFor(() =>
            expect(screen.getByPlaceholderText('Password')).toBeInTheDocument()
        );
    });

    it('transitions to set-password step on first login', async () => {
        global.fetch
            .mockReturnValueOnce(jsonResponse({}, false))
            .mockReturnValueOnce(jsonResponse({
                exists: true, needs_password_setup: true,
            }));

        renderLogin();
        const user = userEvent.setup();
        const emailInput = await screen.findByPlaceholderText('Email');
        await user.type(emailInput, 'alice@example.com');
        await user.click(screen.getByRole('button', { name: /continue/i }));

        await waitFor(() =>
            expect(
                screen.getByPlaceholderText('Password (minimum 8 characters)')
            ).toBeInTheDocument()
        );
    });

    it('shows error when account does not exist', async () => {
        global.fetch
            .mockReturnValueOnce(jsonResponse({}, false))
            .mockReturnValueOnce(jsonResponse({ exists: false }));

        renderLogin();
        const user = userEvent.setup();
        const emailInput = await screen.findByPlaceholderText('Email');
        await user.type(emailInput, 'ghost@example.com');
        await user.click(screen.getByRole('button', { name: /continue/i }));

        expect(
            await screen.findByText(/no account found for that email/i)
        ).toBeInTheDocument();
    });
});
