import { useState } from 'react';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { logout } from '../utils/auth';

const SIDEBAR_LINKS = [
  { path: '/dashboard', label: 'Dashboard' },
  { path: '/events', label: 'Events' },
  { path: '/drafting-work-load', label: 'Drafting Work Load' },
  { path: '/job-log', label: 'Job Log' },
  { path: '/job-search', label: 'Job Search' },
];

function AppShell({ isAuthenticated }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

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
    <div className="flex flex-col w-full min-h-screen bg-[#f8fafc]">
      {/* Top bar: hamburger + Login/Logout */}
      <header className="relative flex items-center justify-between h-14 px-4 bg-white border-b border-gray-200 sticky top-0 z-40 shrink-0">
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          className="p-2 rounded-lg text-gray-600 hover:bg-gray-100 hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-accent-500"
          aria-label="Open menu"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <h1 className="absolute left-1/2 -translate-x-1/2 text-xl font-bold bg-gradient-to-r from-accent-500 to-accent-600 bg-clip-text text-transparent pointer-events-none">
          MHMW Brain
        </h1>

        <div className="flex items-center gap-2">
          {isAuthenticated ? (
            <button
              type="button"
              onClick={handleLogout}
              className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            >
              Logout
            </button>
          ) : (
            <button
              type="button"
              onClick={() => navigate('/login')}
              className="px-4 py-2 text-sm font-medium text-white bg-accent-500 hover:bg-accent-600 rounded-lg shadow-md ring-2 ring-accent-400 ring-offset-2 focus:outline-none focus:ring-2 focus:ring-accent-500"
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
            className="fixed top-0 left-0 bottom-0 w-64 bg-white shadow-xl z-50 flex flex-col border-r border-gray-200 animate-fade-in"
            aria-label="Navigation"
          >
            <div className="flex items-center justify-between h-14 px-4 border-b border-gray-200">
              <span className="font-semibold text-gray-800">Menu</span>
              <button
                type="button"
                onClick={() => setSidebarOpen(false)}
                className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 focus:outline-none"
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
                      : 'text-gray-700 hover:bg-gray-100'
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
