import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../utils/api';
import FloatingBananas from '../components/FloatingBananas';

function Login({ onLogin }) {
    const [step, setStep] = useState('email'); // 'email', 'set-password', 'login'
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

    const handleCheckUser = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const response = await fetch(`${API_BASE_URL}/api/auth/check-user`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({ username }),
            });

            const data = await response.json();

            if (!data.exists) {
                setError('No account found for that email');
            } else if (data.needs_password_setup) {
                setStep('set-password');
            } else {
                setStep('login');
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

    const handleLogin = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({ username, password }),
            });

            const data = await response.json();

            if (response.ok) {
                // Success - update auth state and redirect to dashboard
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
                            {step === 'email' && 'Sign in to your account'}
                            {step === 'set-password' && 'Set your password'}
                            {step === 'login' && 'Sign in to your account'}
                        </h2>
                        <p className="mt-2 text-center text-sm text-gray-600 dark:text-slate-400">
                            MHMW Brain
                        </p>
                    </div>

                    {/* Email step */}
                    {step === 'email' && (
                        <form className="space-y-6" onSubmit={handleCheckUser}>
                            {error && (
                                <div className="rounded-md bg-red-50 dark:bg-red-900/30 p-4 border border-red-200 dark:border-red-800">
                                    <div className="text-sm text-red-800 dark:text-red-200">{error}</div>
                                </div>
                            )}
                            <div>
                                <label htmlFor="username" className="sr-only">
                                    Email
                                </label>
                                <input
                                    id="username"
                                    name="username"
                                    type="email"
                                    required
                                    className="appearance-none relative block w-full px-3 py-2 border border-gray-300 dark:border-slate-500 placeholder-gray-500 dark:placeholder-slate-400 text-gray-900 dark:text-slate-100 bg-white dark:bg-slate-700 rounded-md focus:outline-none focus:ring-accent-500 focus:border-accent-500 focus:z-10 sm:text-sm"
                                    placeholder="Email"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value)}
                                />
                            </div>
                            <button
                                type="submit"
                                disabled={loading}
                                className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-accent-500 hover:bg-accent-600 focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-slate-800 focus:ring-accent-500 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {loading ? 'Please wait...' : 'Continue'}
                            </button>
                        </form>
                    )}

                    {/* Set password step */}
                    {step === 'set-password' && (
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
                                    setStep('email');
                                    setError('');
                                    setNewPassword('');
                                    setConfirmPassword('');
                                }}
                                className="w-full text-sm text-accent-600 dark:text-accent-400 hover:text-accent-700 dark:hover:text-accent-300"
                            >
                                Back to email
                            </button>
                        </form>
                    )}

                    {/* Login step */}
                    {step === 'login' && (
                        <form className="space-y-6" onSubmit={handleLogin}>
                            {error && (
                                <div className="rounded-md bg-red-50 dark:bg-red-900/30 p-4 border border-red-200 dark:border-red-800">
                                    <div className="text-sm text-red-800 dark:text-red-200">{error}</div>
                                </div>
                            )}
                            <div className="rounded-md shadow-sm -space-y-px">
                                <div>
                                    <label htmlFor="username-login" className="sr-only">
                                        Email
                                    </label>
                                    <input
                                        id="username-login"
                                        name="username"
                                        type="email"
                                        disabled
                                        className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 dark:border-slate-500 placeholder-gray-500 dark:placeholder-slate-400 text-gray-900 dark:text-slate-100 bg-gray-100 dark:bg-slate-600 rounded-t-md focus:outline-none focus:ring-accent-500 focus:border-accent-500 focus:z-10 sm:text-sm cursor-not-allowed opacity-60"
                                        value={username}
                                    />
                                </div>
                                <div>
                                    <label htmlFor="password-login" className="sr-only">
                                        Password
                                    </label>
                                    <input
                                        id="password-login"
                                        name="password"
                                        type="password"
                                        required
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
                            <button
                                type="button"
                                onClick={() => {
                                    setStep('email');
                                    setError('');
                                    setPassword('');
                                }}
                                className="w-full text-sm text-accent-600 dark:text-accent-400 hover:text-accent-700 dark:hover:text-accent-300"
                            >
                                Use a different email
                            </button>
                        </form>
                    )}
                </div>
            </div>
        </div>
    );
}

export default Login;
