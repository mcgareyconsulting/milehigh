/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Login page for both identity spaces — an Employee/Subcontractor toggle over one
 *          shared card, rather than two separate pages, so a person who doesn't know which
 *          URL they need still lands in the right place. Both tabs show email+password
 *          together immediately (no email-first gate); the only extra step is the rare
 *          genuine-first-login case, where the employee flow doesn't yet have a password to
 *          check and instead prompts to set one (a subcontractor's first-login already
 *          happened via the invite-accept link, so that case never applies there).
 * exports:
 *   Login: Page component. Rendered at both /login and /sub/login (App.jsx) — the route just
 *     picks which tab is preselected; the component and its behavior are identical either way.
 * imports_from: [react, react-router-dom, ../utils/api, ../components/FloatingBananas]
 * imported_by: [App.jsx]
 * invariants:
 *   - mode='employee'|'subcontractor' is local UI state, seeded from the current pathname
 *     (/sub/... preselects subcontractor) but freely toggle-able afterward without navigating.
 *   - Already-authenticated employees are immediately redirected to /dashboard on mount.
 *   - Employee submit calls /api/auth/check-user BEFORE /api/auth/login (never calls login
 *     directly) because /api/auth/login's check_password_hash blows up on a null hash — an
 *     account that's never set a password has no hash to verify against. check-user is what
 *     detects that case and reroutes to set-password instead, all from one submit action.
 *   - Switching modes resets step/error/fields so stale state from one flow never leaks into
 *     the other (e.g. an in-progress set-password step doesn't linger after flipping tabs).
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { API_BASE_URL } from '../utils/api';
import FloatingBananas from '../components/FloatingBananas';

function Login({ onLogin }) {
    const location = useLocation();
    const [mode, setMode] = useState(location.pathname.startsWith('/sub') ? 'subcontractor' : 'employee');
    const [step, setStep] = useState('form'); // 'form', 'set-password' (employee mode only)
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    useEffect(() => {
        // Check if user is already logged in
        checkAuth();
    }, []);

    const switchMode = (next) => {
        setMode(next);
        setStep('form');
        setError('');
        setUsername('');
        setPassword('');
        setNewPassword('');
        setConfirmPassword('');
    };

    const checkAuth = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
                credentials: 'include'
            });
            if (response.ok) {
                // User is already logged in, redirect to dashboard
                if (onLogin) onLogin();
                navigate('/dashboard');
            }
        } catch (err) {
            // Not logged in, stay on login page
        }
    };

    const handleEmployeeSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const checkResponse = await fetch(`${API_BASE_URL}/api/auth/check-user`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({ username }),
            });
            const checkData = await checkResponse.json();

            if (!checkData.exists) {
                setError('No account found for that email');
                return;
            }
            if (checkData.needs_password_setup) {
                // Genuine first login: no password to check yet, so this
                // account switches to setting one instead of signing in.
                setStep('set-password');
                return;
            }

            const loginResponse = await fetch(`${API_BASE_URL}/api/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({ username, password }),
            });
            const loginData = await loginResponse.json();

            if (loginResponse.ok) {
                if (onLogin) onLogin();
                navigate('/dashboard');
            } else {
                setError(loginData.error || 'An error occurred');
            }
        } catch (err) {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const handleSetPassword = async (e) => {
        e.preventDefault();
        setError('');

        // Client-side validation
        if (newPassword !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }
        if (newPassword.length < 8) {
            setError('Password must be at least 8 characters');
            return;
        }

        setLoading(true);

        try {
            const response = await fetch(`${API_BASE_URL}/api/auth/set-password`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({
                    username,
                    new_password: newPassword,
                    confirm_password: confirmPassword,
                }),
            });

            const data = await response.json();

            if (response.ok) {
                // Success - auto-login and redirect
                if (onLogin) onLogin();
                navigate('/dashboard');
            } else {
                setError(data.error || 'An error occurred');
            }
        } catch (err) {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const handleSubLogin = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const response = await fetch(`${API_BASE_URL}/api/subcontractor-auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({ email: username, password }),
            });

            const data = await response.json();

            if (response.ok) {
                navigate('/sub/tickets');
            } else {
                setError(data.error || 'An error occurred');
            }
        } catch (err) {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 relative overflow-hidden">
            {/* Floating bananas background */}
            <div className="absolute inset-0 z-0">
                <FloatingBananas className="w-full h-full" />
            </div>

            {/* Login form on top */}
            <div className="relative z-10 w-full max-w-md px-4 py-12">
                <div className="bg-white/95 dark:bg-slate-800/95 backdrop-blur-sm rounded-2xl shadow-xl border border-gray-200 dark:border-slate-600 p-8 space-y-6">
                    <div>
                        <h2 className="text-center text-3xl font-extrabold text-gray-900 dark:text-white">
                            {mode === 'employee' && step === 'form' && 'Sign in to your account'}
                            {mode === 'employee' && step === 'set-password' && 'Set your password'}
                            {mode === 'subcontractor' && 'Subcontractor sign in'}
                        </h2>
                        <p className="mt-2 text-center text-sm text-gray-600 dark:text-slate-400">
                            MHMW Brain
                        </p>
                    </div>

                    <div className="flex rounded-lg border border-gray-300 dark:border-slate-600 p-1 bg-gray-100 dark:bg-slate-900/40">
                        <button type="button" onClick={() => switchMode('employee')}
                            className={`flex-1 py-1.5 text-sm font-semibold rounded-md transition-colors ${mode === 'employee' ? 'bg-accent-500 text-white shadow' : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200'}`}>
                            Employee
                        </button>
                        <button type="button" onClick={() => switchMode('subcontractor')}
                            className={`flex-1 py-1.5 text-sm font-semibold rounded-md transition-colors ${mode === 'subcontractor' ? 'bg-accent-500 text-white shadow' : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200'}`}>
                            Subcontractor
                        </button>
                    </div>

                    {/* Employee sign-in: email + password shown together immediately. One
                        submit checks the account and either signs in or, for a genuine
                        first-ever login, switches to the set-password step below. */}
                    {mode === 'employee' && step === 'form' && (
                        <form className="space-y-6" onSubmit={handleEmployeeSubmit}>
                            {error && (
                                <div className="rounded-md bg-red-50 dark:bg-red-900/30 p-4 border border-red-200 dark:border-red-800">
                                    <div className="text-sm text-red-800 dark:text-red-200">{error}</div>
                                </div>
                            )}
                            <div className="rounded-md shadow-sm -space-y-px">
                                <div>
                                    <label htmlFor="username" className="sr-only">
                                        Email
                                    </label>
                                    <input
                                        id="username"
                                        name="username"
                                        type="email"
                                        required
                                        autoComplete="username"
                                        className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 dark:border-slate-500 placeholder-gray-500 dark:placeholder-slate-400 text-gray-900 dark:text-slate-100 bg-white dark:bg-slate-700 rounded-t-md focus:outline-none focus:ring-accent-500 focus:border-accent-500 focus:z-10 sm:text-sm"
                                        placeholder="Email"
                                        value={username}
                                        onChange={(e) => setUsername(e.target.value)}
                                    />
                                </div>
                                <div>
                                    <label htmlFor="password" className="sr-only">
                                        Password
                                    </label>
                                    <input
                                        id="password"
                                        name="password"
                                        type="password"
                                        required
                                        autoComplete="current-password"
                                        className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 dark:border-slate-500 placeholder-gray-500 dark:placeholder-slate-400 text-gray-900 dark:text-slate-100 bg-white dark:bg-slate-700 rounded-b-md focus:outline-none focus:ring-accent-500 focus:border-accent-500 focus:z-10 sm:text-sm"
                                        placeholder="Password"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                    />
                                </div>
                            </div>
                            <button
                                type="submit"
                                disabled={loading}
                                className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-accent-500 hover:bg-accent-600 focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-slate-800 focus:ring-accent-500 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {loading ? 'Please wait...' : 'Sign in'}
                            </button>
                        </form>
                    )}

                    {/* Set password step — only reached for a genuine first-ever login
                        (check-user reported needs_password_setup), not part of the normal path. */}
                    {mode === 'employee' && step === 'set-password' && (
                        <form className="space-y-6" onSubmit={handleSetPassword}>
                            {error && (
                                <div className="rounded-md bg-red-50 dark:bg-red-900/30 p-4 border border-red-200 dark:border-red-800">
                                    <div className="text-sm text-red-800 dark:text-red-200">{error}</div>
                                </div>
                            )}
                            <p className="text-sm text-gray-600 dark:text-slate-400">
                                Welcome! Please create a password for your account.
                            </p>
                            <div className="space-y-4">
                                <div>
                                    <label htmlFor="new-password" className="sr-only">
                                        New Password
                                    </label>
                                    <input
                                        id="new-password"
                                        name="new-password"
                                        type="password"
                                        required
                                        minLength="8"
                                        className="appearance-none relative block w-full px-3 py-2 border border-gray-300 dark:border-slate-500 placeholder-gray-500 dark:placeholder-slate-400 text-gray-900 dark:text-slate-100 bg-white dark:bg-slate-700 rounded-md focus:outline-none focus:ring-accent-500 focus:border-accent-500 focus:z-10 sm:text-sm"
                                        placeholder="Password (minimum 8 characters)"
                                        value={newPassword}
                                        onChange={(e) => setNewPassword(e.target.value)}
                                    />
                                </div>
                                <div>
                                    <label htmlFor="confirm-password" className="sr-only">
                                        Confirm Password
                                    </label>
                                    <input
                                        id="confirm-password"
                                        name="confirm-password"
                                        type="password"
                                        required
                                        minLength="8"
                                        className="appearance-none relative block w-full px-3 py-2 border border-gray-300 dark:border-slate-500 placeholder-gray-500 dark:placeholder-slate-400 text-gray-900 dark:text-slate-100 bg-white dark:bg-slate-700 rounded-md focus:outline-none focus:ring-accent-500 focus:border-accent-500 focus:z-10 sm:text-sm"
                                        placeholder="Confirm password"
                                        value={confirmPassword}
                                        onChange={(e) => setConfirmPassword(e.target.value)}
                                    />
                                </div>
                            </div>
                            <button
                                type="submit"
                                disabled={loading}
                                className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-accent-500 hover:bg-accent-600 focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-slate-800 focus:ring-accent-500 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {loading ? 'Setting password...' : 'Set Password'}
                            </button>
                            <button
                                type="button"
                                onClick={() => {
                                    setStep('form');
                                    setError('');
                                    setNewPassword('');
                                    setConfirmPassword('');
                                }}
                                className="w-full text-sm text-accent-600 dark:text-accent-400 hover:text-accent-700 dark:hover:text-accent-300"
                            >
                                Back
                            </button>
                        </form>
                    )}

                    {/* Subcontractor sign-in: single step (a subcontractor's first-login
                        already happened via the invite-accept link, so there's no
                        email-lookup/set-password branch to reproduce here). */}
                    {mode === 'subcontractor' && (
                        <form className="space-y-6" onSubmit={handleSubLogin}>
                            {error && (
                                <div className="rounded-md bg-red-50 dark:bg-red-900/30 p-4 border border-red-200 dark:border-red-800">
                                    <div className="text-sm text-red-800 dark:text-red-200">{error}</div>
                                </div>
                            )}
                            <div className="rounded-md shadow-sm -space-y-px">
                                <div>
                                    <label htmlFor="sub-username" className="sr-only">
                                        Email
                                    </label>
                                    <input
                                        id="sub-username"
                                        name="username"
                                        type="email"
                                        required
                                        autoComplete="username"
                                        className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 dark:border-slate-500 placeholder-gray-500 dark:placeholder-slate-400 text-gray-900 dark:text-slate-100 bg-white dark:bg-slate-700 rounded-t-md focus:outline-none focus:ring-accent-500 focus:border-accent-500 focus:z-10 sm:text-sm"
                                        placeholder="Email"
                                        value={username}
                                        onChange={(e) => setUsername(e.target.value)}
                                    />
                                </div>
                                <div>
                                    <label htmlFor="sub-password" className="sr-only">
                                        Password
                                    </label>
                                    <input
                                        id="sub-password"
                                        name="password"
                                        type="password"
                                        required
                                        autoComplete="current-password"
                                        className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 dark:border-slate-500 placeholder-gray-500 dark:placeholder-slate-400 text-gray-900 dark:text-slate-100 bg-white dark:bg-slate-700 rounded-b-md focus:outline-none focus:ring-accent-500 focus:border-accent-500 focus:z-10 sm:text-sm"
                                        placeholder="Password"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                    />
                                </div>
                            </div>
                            <button
                                type="submit"
                                disabled={loading}
                                className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-accent-500 hover:bg-accent-600 focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-slate-800 focus:ring-accent-500 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {loading ? 'Please wait...' : 'Sign in'}
                            </button>
                        </form>
                    )}
                </div>
            </div>
        </div>
    );
}

export default Login;
