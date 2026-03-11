import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { logout } from '../utils/auth';
import { useTheme } from '../context/ThemeContext';
import QuickSearch from './QuickSearch';

function AppShell({ isAuthenticated }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { isDark, toggleTheme } = useTheme();

  const handleLogout = async () => {
    await logout();
    window.location.href = '/login';
  };

  const isActive = (path) => location.pathname.startsWith(path);

  return (
    <div className="flex flex-col w-full min-h-screen bg-[#f8fafc] dark:bg-slate-900">
      {/* Top bar */}
      <header className="relative flex items-center h-14 px-4 gap-2 bg-white dark:bg-slate-800 border-b border-gray-200 dark:border-slate-600 sticky top-0 z-40 shrink-0">
        {/* Quick search */}
        <QuickSearch />

        {/* Map shortcut */}
        <button
          type="button"
          onClick={() => navigate('/jobsite-map')}
          className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${isActive('/jobsite-map')
            ? 'bg-accent-500 text-white'
            : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
            }`}
        >
          Map
        </button>

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
            className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${isActive('/job-log')
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
            className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${isActive('/drafting-work-load')
              ? 'bg-accent-500 text-white'
              : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
              }`}
          >
            Drafting WL
          </button>

          {/* Events shortcut */}
          <button
            type="button"
            onClick={() => navigate('/events')}
            className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${isActive('/events')
              ? 'bg-accent-500 text-white'
              : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
              }`}
          >
            Events
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

      {/* Main content */}
      <main className="flex-1 w-full min-h-0 flex flex-col">
        <Outlet />
      </main>
    </div>
  );
}

export default AppShell;
