// Smoke + flow tests for the Login page — employee (email+password shown together,
// with a rare first-login set-password branch) and subcontractor (single email+password step).
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

    it('mounts with email and password fields both visible immediately', async () => {
        global.fetch.mockReturnValueOnce(jsonResponse({}, false));
        renderLogin();
        expect(await screen.findByPlaceholderText('Email')).toBeInTheDocument();
        expect(screen.getByPlaceholderText('Password')).toBeInTheDocument();
    });

    it('signs in directly when the account exists with a password already set', async () => {
        global.fetch
            .mockReturnValueOnce(jsonResponse({}, false)) // checkAuth on mount
            .mockReturnValueOnce(jsonResponse({ exists: true, needs_password_setup: false })) // check-user
            .mockReturnValueOnce(jsonResponse({ status: 'success' })); // login

        renderLogin();
        const user = userEvent.setup();
        await user.type(await screen.findByPlaceholderText('Email'), 'alice@example.com');
        await user.type(screen.getByPlaceholderText('Password'), 'hunter22');
        await user.click(screen.getByRole('button', { name: /sign in/i }));

        await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining('/api/auth/login'),
            expect.objectContaining({ method: 'POST' }),
        ));
    });

    it('transitions to set-password step on a genuine first login', async () => {
        global.fetch
            .mockReturnValueOnce(jsonResponse({}, false))
            .mockReturnValueOnce(jsonResponse({ exists: true, needs_password_setup: true }));

        renderLogin();
        const user = userEvent.setup();
        await user.type(await screen.findByPlaceholderText('Email'), 'alice@example.com');
        await user.type(screen.getByPlaceholderText('Password'), 'whatever');
        await user.click(screen.getByRole('button', { name: /sign in/i }));

        await waitFor(() =>
            expect(screen.getByPlaceholderText('Password (minimum 8 characters)')).toBeInTheDocument()
        );
        // No second (login) call was made — check-user alone routed here.
        expect(global.fetch).toHaveBeenCalledTimes(2);
    });

    it('shows error when account does not exist', async () => {
        global.fetch
            .mockReturnValueOnce(jsonResponse({}, false))
            .mockReturnValueOnce(jsonResponse({ exists: false }));

        renderLogin();
        const user = userEvent.setup();
        await user.type(await screen.findByPlaceholderText('Email'), 'ghost@example.com');
        await user.type(screen.getByPlaceholderText('Password'), 'whatever');
        await user.click(screen.getByRole('button', { name: /sign in/i }));

        expect(
            await screen.findByText(/no account found for that email/i)
        ).toBeInTheDocument();
    });

    it('switches to the subcontractor tab and submits against the subcontractor login endpoint', async () => {
        global.fetch
            .mockReturnValueOnce(jsonResponse({}, false)) // checkAuth on mount
            .mockReturnValueOnce(jsonResponse({ status: 'success' })); // subcontractor login

        renderLogin();
        const user = userEvent.setup();
        await screen.findByPlaceholderText('Email');

        await user.click(screen.getByRole('button', { name: /subcontractor/i }));
        await user.type(screen.getByPlaceholderText('Email'), 'sam@acme.test');
        await user.type(screen.getByPlaceholderText('Password'), 'hunter22');
        await user.click(screen.getByRole('button', { name: /sign in/i }));

        await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining('/api/subcontractor-auth/login'),
            expect.objectContaining({ method: 'POST' }),
        ));
    });

    it('switching tabs clears in-progress state from the other flow', async () => {
        global.fetch
            .mockReturnValueOnce(jsonResponse({}, false))
            .mockReturnValueOnce(jsonResponse({ exists: true, needs_password_setup: true }));

        renderLogin();
        const user = userEvent.setup();
        await user.type(await screen.findByPlaceholderText('Email'), 'alice@example.com');
        await user.type(screen.getByPlaceholderText('Password'), 'whatever');
        await user.click(screen.getByRole('button', { name: /sign in/i }));
        await screen.findByPlaceholderText('Password (minimum 8 characters)');

        await user.click(screen.getByRole('button', { name: /^employee$/i }));
        expect(await screen.findByPlaceholderText('Email')).toBeInTheDocument();
        expect(screen.getByPlaceholderText('Password')).toBeInTheDocument();
    });
});
