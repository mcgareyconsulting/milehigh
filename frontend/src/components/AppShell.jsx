/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Wraps all authenticated pages with the top navigation bar, theme toggle, location controls, and notification bell. Collapses nav into a slide-in drawer below the nav (1440px) breakpoint for iPad (incl. iPad Pro) and phone.
 * exports:
 *   AppShell: Layout shell with nav chrome, renders child routes via Outlet
 * imports_from: [react, react-router-dom, ../utils/auth, ../context/ThemeContext, ../context/LocationContext, ../context/ReleasesContext, ./QuickSearch, ./NotificationBell, ./MobileNavDrawer]
 * imported_by: [frontend/src/App.jsx]
 * invariants:
 *   - Admin-only nav items are gated on checkAuth result
 *   - LocationProvider wraps the inner shell so all children can access geolocation context
 *   - Header height: 3.5rem (h-14) up to 3xl, then 4rem to give 27"+ / TV more room.
 */
import { useState, useEffect } from 'react';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { logout, checkAuth, userCanAccessInvoicing } from '../utils/auth';
import { useTheme } from '../context/ThemeContext';
import { LocationProvider, useLocationContext } from '../context/LocationContext';
import { ReleasesProvider } from '../context/ReleasesContext';
import QuickSearch from './QuickSearch';
import NotificationBell from './NotificationBell';
import MobileNavDrawer from './MobileNavDrawer';
import BBChatWidget from './BBChatWidget';
import PatchNotesModal from './PatchNotesModal';
import { CURRENT_VERSION } from '../data/patchNotes';

function AppShellInner({ isAuthenticated }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { isDark, isOldMan, toggleDark, toggleOldMan } = useTheme();
  const [showThemeMenu, setShowThemeMenu] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { locationEnabled, locationRequesting, handleLocationToggle } = useLocationContext();
  const [isAdmin, setIsAdmin] = useState(false);
  const [canSeeReport, setCanSeeReport] = useState(false);
  const [canUseBBChat, setCanUseBBChat] = useState(false);
  const [showPatchNotes, setShowPatchNotes] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      checkAuth().then(user => {
        setIsAdmin(user?.is_admin || false);
        setCanSeeReport(userCanAccessInvoicing(user));
        // Admins always have BB-chat access; others need the per-user flag.
        setCanUseBBChat(!!user && (user.is_admin || user.is_bb_chat));
      });
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (!showThemeMenu) return;
    const handler = (e) => {
      if (!e.target.closest('[data-theme-menu]')) setShowThemeMenu(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showThemeMenu]);

  const handleLogout = async () => {
    await logout();
    window.location.href = '/login';
  };

  const isActive = (path) => location.pathname.startsWith(path);

  const navBtn = (path, label) => (
    <button
      type="button"
      onClick={() => navigate(path)}
      className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${isActive(path)
        ? 'bg-accent-500 text-white'
        : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
        }`}
    >
      {label}
    </button>
  );

  const navIconBtn = (path, label, icon) => (
    <button
      type="button"
      onClick={() => navigate(path)}
      className={`p-2 rounded-lg transition-colors ${isActive(path)
        ? 'bg-accent-500 text-white'
        : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
        }`}
      aria-label={label}
      title={label}
    >
      {icon}
    </button>
  );

  return (
    <div className="flex flex-col w-full min-h-screen bg-[#f8fafc] dark:bg-slate-900">
      {/* Top bar */}
      <header
        className="relative flex items-center h-14 3xl:h-16 px-3 lg:px-4 gap-2 bg-white dark:bg-slate-800 border-b border-gray-200 dark:border-slate-600 sticky top-0 z-40 shrink-0"
        style={{ paddingTop: 'env(safe-area-inset-top)' }}
      >
        {/* Brand — pinned far left */}
        <h1 className="shrink-0 text-lg 3xl:text-xl font-bold bg-gradient-to-r from-accent-500 to-accent-600 dark:from-accent-300 dark:to-accent-400 bg-clip-text text-transparent whitespace-nowrap select-none">
          MHMW Brain
        </h1>

        {/* Version badge — opens patch notes */}
        <button
          type="button"
          onClick={() => setShowPatchNotes(true)}
          className="shrink-0 px-1.5 py-0.5 text-[11px] font-medium rounded-md text-gray-500 dark:text-slate-400 hover:text-accent-600 dark:hover:text-accent-300 hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors"
          title="What's new — view patch notes"
        >
          {CURRENT_VERSION}
        </button>

        {/* Everything else expands from the right; search is the leftmost item */}
        <div className="ml-auto flex items-center gap-2">
          {/* Quick search — leftmost of the right cluster */}
          <QuickSearch />

          {/* Map + Location shortcuts — visible on 2xl+ only */}
          <div className="hidden min-[1440px]:flex items-center gap-2">
            {navBtn('/jobsite-map', 'Map')}
            <button
              type="button"
              onClick={handleLocationToggle}
              disabled={locationRequesting}
              className={`inline-flex items-center justify-center p-2 rounded-lg shadow-sm transition-all ${
                locationEnabled
                  ? 'bg-green-500 text-white hover:bg-green-600'
                  : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
              } ${locationRequesting ? 'opacity-70 cursor-wait' : 'cursor-pointer'}`}
              aria-label={locationEnabled ? 'Turn off location filter' : 'Filter by your current location'}
              title={locationEnabled ? 'Turn off location filter' : 'Filter by your current location'}
            >
              {locationRequesting ? (
                <span className="inline-block w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
              ) : (
                <span aria-hidden>📍</span>
              )}
            </button>
          </div>

          {/* Inline nav buttons — 2xl+ only */}
          <div className="hidden min-[1440px]:flex items-center gap-2">
            {navBtn('/job-log', 'Job Log')}
            {navBtn('/drafting-work-load', 'Drafting WL')}
            {navBtn('/events', 'Events')}
            {navBtn('/todos', 'To-Dos')}
            {canSeeReport && navBtn('/invoicing-report', 'Invoicing')}
            {/* Rentals nav removed 2026-07-12 (company change) — /rental-reports route + backend stay for direct URL / re-enable */}
            {isAdmin && navBtn('/meetings', 'Meetings')}
            {isAdmin && navIconBtn('/board', 'Bug Tracker', (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                {/* Antennae */}
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 4Q7 1 5 2M15 4Q17 1 19 2" />
                {/* Body */}
                <path strokeLinejoin="round" strokeWidth={1.5} d="M12 4c-3.5 0-6 2.3-6 5.8v4.4c0 3.9 2.5 6.8 6 6.8s6-2.9 6-6.8V9.8C18 6.3 15.5 4 12 4Z" />
                {/* Wing seam */}
                <path strokeLinecap="round" strokeWidth={1.5} d="M12 4v17" />
                {/* Legs, drawn with circuit-trace elbows */}
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 9.5H3V7M6 13.5H2M6.5 17.5l-2.2 1.3-.3 2M18 9.5h3V7M18 13.5h4M17.5 17.5l2.2 1.3.3 2" />
                {/* Circuit nodes inside the body */}
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 11h2.5M9 11v3M9 14h1.8M9.3 14.3 10 17h1.7" />
                <circle cx="9" cy="11" r="0.9" fill="currentColor" stroke="none" />
                <circle cx="9" cy="14" r="0.9" fill="currentColor" stroke="none" />
                <circle cx="10" cy="17" r="0.9" fill="currentColor" stroke="none" />
              </svg>
            ))}
            {isAdmin && navBtn('/admin/submittal-matching', 'Matching')}
          </div>

          {/* Notification bell (always visible if authenticated) */}
          {isAuthenticated && <NotificationBell />}

          {/* Theme picker (always visible) */}
          <div className="relative" data-theme-menu>
            <button
              type="button"
              onClick={() => setShowThemeMenu(prev => !prev)}
              className="p-2 rounded-lg text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-accent-500"
              aria-label="Change theme"
            >
              {isOldMan ? (
                <span className="w-5 h-5 flex items-center justify-center text-sm font-bold leading-none">Aa</span>
              ) : isDark ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" /></svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" /></svg>
              )}
            </button>
            {showThemeMenu && (
              <div className="absolute right-0 mt-1 w-52 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-lg shadow-lg z-50 p-3 space-y-3">
                {/* Dark mode toggle */}
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-gray-700 dark:text-slate-200">Dark Mode</span>
                  <button
                    type="button"
                    onClick={toggleDark}
                    className={`relative flex-shrink-0 w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-accent-500 ${isDark ? 'bg-accent-500' : 'bg-gray-200 dark:bg-slate-600'}`}
                    aria-pressed={isDark}
                  >
                    <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200 ${isDark ? 'translate-x-5' : 'translate-x-0'}`} />
                  </button>
                </div>
                {/* Old Man Mode toggle */}
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-gray-700 dark:text-slate-200">Old Man Mode</span>
                  <button
                    type="button"
                    onClick={toggleOldMan}
                    className={`relative flex-shrink-0 w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-amber-500 ${isOldMan ? 'bg-amber-500' : 'bg-gray-200 dark:bg-slate-600'}`}
                    aria-pressed={isOldMan}
                  >
                    <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200 ${isOldMan ? 'translate-x-5' : 'translate-x-0'}`} />
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Login / Logout — 2xl+ inline, smaller hidden */}
          {isAuthenticated ? (
            <button
              type="button"
              onClick={handleLogout}
              className="hidden min-[1440px]:inline-flex px-4 py-2 text-sm font-medium text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
            >
              Logout
            </button>
          ) : (
            <button
              type="button"
              onClick={() => navigate('/login')}
              className="hidden min-[1440px]:inline-flex px-4 py-2 text-sm font-medium text-white bg-accent-500 hover:bg-accent-600 rounded-lg shadow-md ring-2 ring-accent-400 ring-offset-2 dark:ring-offset-slate-800 focus:outline-none focus:ring-2 focus:ring-accent-500"
            >
              Log in
            </button>
          )}

          {/* Hamburger — visible below xl only */}
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="min-[1440px]:hidden p-2 rounded-lg text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-accent-500 min-h-[44px] min-w-[44px] flex items-center justify-center"
            aria-label="Open menu"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>
      </header>

      <MobileNavDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        isAuthenticated={isAuthenticated}
        isAdmin={isAdmin}
        canSeeReport={canSeeReport}
        locationEnabled={locationEnabled}
        locationRequesting={locationRequesting}
        onLocationToggle={handleLocationToggle}
        onLogout={handleLogout}
        onLogin={() => navigate('/login')}
      />

      <PatchNotesModal isOpen={showPatchNotes} onClose={() => setShowPatchNotes(false)} isAdmin={isAdmin} />

      {/* Main content */}
      <main className="flex-1 w-full min-h-0 flex flex-col">
        <Outlet />
      </main>

      {/* Floating read-only data assistant — flag-gated per user */}
      {isAuthenticated && <BBChatWidget enabled={canUseBBChat} isAdmin={isAdmin} />}
    </div>
  );
}

function AppShell({ isAuthenticated }) {
  return (
    <LocationProvider>
      <ReleasesProvider enabled={!!isAuthenticated}>
        <AppShellInner isAuthenticated={isAuthenticated} />
      </ReleasesProvider>
    </LocationProvider>
  );
}

export default AppShell;
