/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Collapsible left-hand navigation rail used in place of the top header for pilot users on cramped laptop screens. Hosts QuickSearch, the nav links, location filter, notification bell, theme menu, and logout so the top bar can be removed entirely (frees vertical space).
 * exports:
 *   Sidebar: Left nav rail. Props: isAuthenticated, isAdmin, canSeeReport, onLogout.
 * imports_from: [react, react-router-dom, ../context/ThemeContext, ../context/LocationContext, ./QuickSearch, ./NotificationBell]
 * imported_by: [frontend/src/components/AppShell.jsx]
 * invariants:
 *   - Collapsed/expanded state persists in localStorage ('mhmw_sidebar_collapsed').
 *   - Nav routes/labels and role gating mirror AppShell's top-bar nav exactly.
 *   - Consumes Theme/Location contexts directly (rendered inside their providers).
 */
import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTheme } from '../context/ThemeContext';
import { useLocationContext } from '../context/LocationContext';
import QuickSearch from './QuickSearch';
import NotificationBell from './NotificationBell';

const STORAGE_KEY = 'mhmw_sidebar_collapsed';

// Inline stroke icons (the codebase has no icon library by convention).
const Icon = ({ d }) => (
  <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    {Array.isArray(d)
      ? d.map((p, i) => <path key={i} strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={p} />)
      : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={d} />}
  </svg>
);

const ICONS = {
  map: 'M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7',
  jobLog: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01',
  draft: 'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z',
  board: 'M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2',
  events: 'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z',
  todos: ['M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2', 'M9 14l2 2 4-4'],
  invoicing: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 9v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  meetings: 'M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 4a4 4 0 11-8 0 4 4 0 018 0z',
  bug: 'M12 9v2m0 4h.01M5.07 19h13.86a2 2 0 001.71-3l-6.93-12a2 2 0 00-3.42 0l-6.93 12a2 2 0 001.71 3z',
  search: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
  logout: 'M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1',
  location: 'M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0zM15 11a3 3 0 11-6 0 3 3 0 016 0z',
};

// Mirrors AppShell / MobileNavDrawer nav set + role gating.
const NAV_ITEMS = [
  { label: 'Map', path: '/jobsite-map', icon: ICONS.map },
  { label: 'Job Log', path: '/job-log', icon: ICONS.jobLog },
  { label: 'Drafting WL', path: '/drafting-work-load', icon: ICONS.draft },
  { label: 'PM Board', path: '/pm-board', icon: ICONS.board },
  { label: 'Events', path: '/events', icon: ICONS.events },
  { label: 'To-Dos', path: '/todos', icon: ICONS.todos },
];

export default function Sidebar({ isAuthenticated, isAdmin, canSeeReport, onLogout }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { isDark, isOldMan, toggleDark, toggleOldMan } = useTheme();
  const { locationEnabled, locationRequesting, handleLocationToggle } = useLocationContext();

  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) === '1'; } catch { return false; }
  });
  const [showThemeMenu, setShowThemeMenu] = useState(false);

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0'); } catch { /* ignore */ }
  }, [collapsed]);

  useEffect(() => {
    if (!showThemeMenu) return undefined;
    const handler = (e) => { if (!e.target.closest('[data-theme-menu]')) setShowThemeMenu(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showThemeMenu]);

  const isActive = (path) => location.pathname.startsWith(path);

  const navItems = [
    ...NAV_ITEMS,
    ...(canSeeReport ? [{ label: 'Invoicing', path: '/invoicing-report', icon: ICONS.invoicing }] : []),
    ...(isAdmin ? [
      { label: 'Meetings', path: '/meetings', icon: ICONS.meetings },
      { label: 'Bug Tracker', path: '/board', icon: ICONS.bug },
    ] : []),
  ];

  const navItemClass = (active) =>
    `w-full flex items-center ${collapsed ? 'justify-center' : 'gap-3'} px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
      active ? 'bg-accent-500 text-white' : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
    }`;

  const chromeBtnClass =
    `flex items-center ${collapsed ? 'justify-center w-full' : 'gap-2'} px-3 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors`;

  return (
    <aside
      // No width transition: main content (a ~6,500-cell table) is a flex
      // sibling that reflows each frame while the width animates (~48ms/reflow),
      // which stutters badly. Snapping does one reflow on toggle — far smoother.
      className={`${collapsed ? 'w-14' : 'w-56'} shrink-0 sticky top-0 self-start h-screen z-30 flex flex-col bg-white dark:bg-slate-800 border-r border-gray-200 dark:border-slate-600`}
      style={{ paddingTop: 'env(safe-area-inset-top)' }}
    >
      {/* Brand + collapse toggle */}
      <div className={`flex items-center ${collapsed ? 'justify-center' : 'justify-between'} h-14 px-2 border-b border-gray-200 dark:border-slate-600 shrink-0`}>
        {!collapsed && (
          <span className="px-1 text-lg font-bold bg-gradient-to-r from-accent-500 to-accent-600 dark:from-accent-300 dark:to-accent-400 bg-clip-text text-transparent truncate">
            MHMW Brain
          </span>
        )}
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="p-2 rounded-lg text-gray-500 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-accent-500"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand' : 'Collapse'}
        >
          <span className="w-5 h-5 flex items-center justify-center text-base leading-none">{collapsed ? '»' : '«'}</span>
        </button>
      </div>

      {/* Search */}
      <div className="px-2 py-2 shrink-0">
        {collapsed ? (
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            className={chromeBtnClass}
            aria-label="Search"
            title="Search"
          >
            <Icon d={ICONS.search} />
          </button>
        ) : (
          <QuickSearch />
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-1 space-y-1">
        {navItems.map((item) => (
          <button
            key={item.path}
            type="button"
            onClick={() => navigate(item.path)}
            className={navItemClass(isActive(item.path))}
            title={collapsed ? item.label : undefined}
          >
            <Icon d={item.icon} />
            {!collapsed && <span className="truncate">{item.label}</span>}
          </button>
        ))}
      </nav>

      {/* Footer chrome */}
      <div className="border-t border-gray-200 dark:border-slate-600 p-2 space-y-1 shrink-0" style={{ paddingBottom: 'max(0.5rem, env(safe-area-inset-bottom))' }}>
        {/* Location toggle */}
        <button
          type="button"
          onClick={handleLocationToggle}
          disabled={locationRequesting}
          className={`w-full flex items-center ${collapsed ? 'justify-center' : 'gap-2'} px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
            locationEnabled
              ? 'bg-green-500 text-white hover:bg-green-600'
              : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
          } ${locationRequesting ? 'opacity-70 cursor-wait' : ''}`}
          title={locationEnabled ? 'Turn off location filter' : 'Filter by your current location'}
        >
          {locationRequesting ? (
            <span className="inline-block w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
          ) : (
            <Icon d={ICONS.location} />
          )}
          {!collapsed && <span className="truncate">{locationRequesting ? 'Locating…' : locationEnabled ? 'Location on' : 'Location'}</span>}
        </button>

        {/* Bell + theme + logout */}
        <div className={`flex items-center ${collapsed ? 'flex-col' : ''} gap-1`}>
          {isAuthenticated && (
            <div className={collapsed ? '' : ''} title="Notifications">
              <NotificationBell />
            </div>
          )}

          {/* Theme menu */}
          <div className="relative" data-theme-menu>
            <button
              type="button"
              onClick={() => setShowThemeMenu((p) => !p)}
              className="p-2 rounded-lg text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-accent-500"
              aria-label="Change theme"
              title="Theme"
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
              <div className="absolute bottom-full mb-2 left-0 w-52 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-lg shadow-lg z-50 p-3 space-y-3">
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

          {/* Logout */}
          {isAuthenticated && (
            <button
              type="button"
              onClick={onLogout}
              className={`${collapsed ? 'p-2' : 'ml-auto px-3 py-2 gap-2'} flex items-center rounded-lg text-sm font-medium text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors`}
              aria-label="Logout"
              title="Logout"
            >
              <Icon d={ICONS.logout} />
              {!collapsed && <span>Logout</span>}
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
