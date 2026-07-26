/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Landing page for a subcontractor invite link (/sub/accept-invite/:token) — validates
 *          the token on mount (GET, no side effect) to pre-fill company/contact and show a
 *          clean expired/invalid state, then a set-password form that consumes the token (POST).
 * exports:
 *   SubcontractorAcceptInvite: Page component.
 * imports_from: [react, react-router-dom, ../utils/api]
 * imported_by: [App.jsx]
 * invariants:
 *   - The GET validation call never mutates state server-side — burning the token happens only
 *     on the POST, so refreshing this page doesn't invalidate the invite.
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../utils/api';

export default function SubcontractorAcceptInvite() {
    const { token } = useParams();
    const navigate = useNavigate();
    const [invite, setInvite] = useState(null);
    const [inviteError, setInviteError] = useState(null);
    const [checking, setChecking] = useState(true);
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        fetch(`${API_BASE_URL}/api/subcontractor-auth/invite/${token}`, { credentials: 'include' })
            .then(async (resp) => {
                const data = await resp.json();
                if (resp.ok) {
                    setInvite(data);
                } else {
                    setInviteError(data.error || 'This invite is no longer valid.');
                }
            })
            .catch(() => setInviteError('Network error. Please try again.'))
            .finally(() => setChecking(false));
    }, [token]);

    const handleAccept = async (e) => {
        e.preventDefault();
        setError('');
        if (password !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }
        if (password.length < 8) {
            setError('Password must be at least 8 characters');
            return;
        }
        setLoading(true);
        try {
            const response = await fetch(`${API_BASE_URL}/api/subcontractor-auth/accept-invite`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ token, password, confirm_password: confirmPassword }),
            });
            const data = await response.json();
            if (response.ok) {
                navigate('/sub/tickets', { replace: true });
            } else {
                setError(data.error || 'An error occurred');
            }
        } catch {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 p-4">
            <div className="w-full max-w-md">
                <div className="bg-white/95 dark:bg-slate-800/95 backdrop-blur-sm rounded-2xl shadow-xl border border-gray-200 dark:border-slate-600 p-8 space-y-6">
                    <div>
                        <h2 className="text-center text-2xl font-extrabold text-gray-900 dark:text-white">You're invited</h2>
                        <p className="mt-2 text-center text-sm text-gray-600 dark:text-slate-400">MHMW Brain</p>
                    </div>

                    {checking ? (
                        <div className="text-center text-sm text-gray-500 dark:text-slate-400">Checking your invite…</div>
                    ) : inviteError ? (
                        <div className="rounded-md bg-red-50 dark:bg-red-900/30 p-4 border border-red-200 dark:border-red-800 text-center">
                            <div className="text-sm text-red-800 dark:text-red-200">{inviteError}</div>
                            <div className="mt-2 text-xs text-red-700 dark:text-red-300">
                                Ask whoever invited you to resend the invite.
                            </div>
                        </div>
                    ) : (
                        <form className="space-y-4" onSubmit={handleAccept}>
                            <p className="text-sm text-gray-600 dark:text-slate-400 text-center">
                                Set a password for <strong>{invite.email}</strong> ({invite.company_name})
                            </p>
                            {error && (
                                <div className="rounded-md bg-red-50 dark:bg-red-900/30 p-3 border border-red-200 dark:border-red-800">
                                    <div className="text-sm text-red-800 dark:text-red-200">{error}</div>
                                </div>
                            )}
                            <div>
                                <label htmlFor="invite-password" className="sr-only">Password</label>
                                <input
                                    id="invite-password" type="password" required minLength="8" autoComplete="new-password"
                                    className="w-full px-3 py-2.5 border border-gray-300 dark:border-slate-500 placeholder-gray-500 dark:placeholder-slate-400 text-gray-900 dark:text-slate-100 bg-white dark:bg-slate-700 rounded-md focus:outline-none focus:ring-accent-500 focus:border-accent-500 text-sm"
                                    placeholder="Password (minimum 8 characters)" value={password}
                                    onChange={e => setPassword(e.target.value)}
                                />
                            </div>
                            <div>
                                <label htmlFor="invite-confirm" className="sr-only">Confirm password</label>
                                <input
                                    id="invite-confirm" type="password" required minLength="8" autoComplete="new-password"
                                    className="w-full px-3 py-2.5 border border-gray-300 dark:border-slate-500 placeholder-gray-500 dark:placeholder-slate-400 text-gray-900 dark:text-slate-100 bg-white dark:bg-slate-700 rounded-md focus:outline-none focus:ring-accent-500 focus:border-accent-500 text-sm"
                                    placeholder="Confirm password" value={confirmPassword}
                                    onChange={e => setConfirmPassword(e.target.value)}
                                />
                            </div>
                            <button
                                type="submit" disabled={loading}
                                className="w-full py-2.5 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-accent-500 hover:bg-accent-600 focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-slate-800 focus:ring-accent-500 disabled:opacity-50"
                            >
                                {loading ? 'Setting password…' : 'Set password & sign in'}
                            </button>
                        </form>
                    )}
                </div>
            </div>
        </div>
    );
}
