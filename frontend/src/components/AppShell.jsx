import { useState } from 'react';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { logout } from '../utils/auth';
import { useTheme } from '../context/ThemeContext';
import QuickSearch from './QuickSearch';

const SIDEBAR_LINKS = [
  { path: '/dashboard', label: 'Dashboard' },
  { path: '/events', label: 'Events' },
];

function AppShell({ isAuthenticated }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { isDark, toggleTheme } = useTheme();

  const handleLogout = async () => {
    await logout();
    window.location.href = '/login';
  };

  const handleNav = (path) => {
    navigate(path);
    setSidebarOpen(false);
  };

  const isActive = (path) => {
    if (path === '/dashboard') return location.pathname === '/dashboard';
    return location.pathname.startsWith(path);
  };

  return (
    <div className="flex flex-col w-full min-h-screen bg-[#f8fafc] dark:bg-slate-900">
      {/* Top bar */}
      <header className="relative flex items-center h-14 px-4 gap-2 bg-white dark:bg-slate-800 border-b border-gray-200 dark:border-slate-600 sticky top-0 z-40 shrink-0">
        {/* Hamburger */}
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          className="shrink-0 p-2 rounded-lg text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 hover:text-gray-900 dark:hover:text-white focus:outline-none focus:ring-2 focus:ring-accent-500"
          aria-label="Open menu"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        {/* Quick search */}
        <QuickSearch />

        {/* Centered title */}
        <h1 className="absolute left-1/2 -translate-x-1/2 text-xl font-bold bg-gradient-to-r from-accent-500 to-accent-600 dark:from-accent-300 dark:to-accent-400 bg-clip-text text-transparent pointer-events-none">
          MHMW Brain
        </h1>

        {/* Right cluster */}
        <div className="ml-auto flex items-center gap-2">
          {/* Job Log shortcut */}
          <button
            type="button"
            onClick={() => navigate('/job-log')}
            className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              isActive('/job-log')
                ? 'bg-accent-500 text-white'
                : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
            }`}
          >
            Job Log
          </button>

          {/* Drafting Work Load shortcut */}
          <button
            type="button"
            onClick={() => navigate('/drafting-work-load')}
            className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              isActive('/drafting-work-load')
                ? 'bg-accent-500 text-white'
                : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
            }`}
          >
            Drafting WL
          </button>

          {/* Theme toggle */}
          <button
            type="button"
            onClick={toggleTheme}
            className="p-2 rounded-lg text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-accent-500"
            aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {isDark ? (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" /></svg>
            ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" /></svg>
            )}
          </button>

          {/* Login / Logout */}
          {isAuthenticated ? (
            <button
              type="button"
              onClick={handleLogout}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
            >
              Logout
            </button>
          ) : (
            <button
              type="button"
              onClick={() => navigate('/login')}
              className="px-4 py-2 text-sm font-medium text-white bg-accent-500 hover:bg-accent-600 rounded-lg shadow-md ring-2 ring-accent-400 ring-offset-2 dark:ring-offset-slate-800 focus:outline-none focus:ring-2 focus:ring-accent-500"
            >
              Log in
            </button>
          )}
        </div>
      </header>

      {/* Overlay sidebar */}
      {sidebarOpen && (
        <>
          <div
            className="fixed inset-0 bg-black/40 z-40 transition-opacity"
            aria-hidden="true"
            onClick={() => setSidebarOpen(false)}
          />
          <aside
            className="fixed top-0 left-0 bottom-0 w-64 bg-white dark:bg-slate-800 shadow-xl z-50 flex flex-col border-r border-gray-200 dark:border-slate-600 animate-fade-in"
            aria-label="Navigation"
          >
            <div className="flex items-center justify-between h-14 px-4 border-b border-gray-200 dark:border-slate-600">
              <span className="font-semibold text-gray-800 dark:text-slate-100">Menu</span>
              <button
                type="button"
                onClick={() => setSidebarOpen(false)}
                className="p-2 rounded-lg text-gray-500 dark:text-slate-400 hover:bg-gray-100 dark:hover:bg-slate-700 focus:outline-none"
                aria-label="Close menu"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <nav className="p-3 flex flex-col gap-1">
              {SIDEBAR_LINKS.map(({ path, label }) => (
                <button
                  key={path}
                  type="button"
                  onClick={() => handleNav(path)}
                  className={`text-left px-4 py-3 rounded-lg font-medium transition-colors ${
                    isActive(path)
                      ? 'bg-accent-500 text-white'
                      : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
                  }`}
                >
                  {label}
                </button>
              ))}
            </nav>
          </aside>
        </>
      )}

      {/* Main content */}
      <main className="flex-1 w-full min-h-0 flex flex-col">
        <Outlet />
      </main>
    </div>
  );
}

export default AppShell;
