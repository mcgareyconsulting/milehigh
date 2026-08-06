/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Manages independent dark-mode, old-man-mode, and left-sidebar-mode state; persists to localStorage; applies theme classes to document root.
 * exports:
 *   ThemeProvider: Context provider that syncs theme flags to DOM and localStorage
 *   useTheme: Hook returning { isDark, isOldMan, isSidebarMode, toggleDark, toggleOldMan, toggleSidebarMode }
 * imports_from: [react]
 * imported_by: [main.jsx, components/AppShell.jsx, components/JobsTableRow.jsx, components/Rail.jsx]
 * invariants:
 *   - isDark, isOldMan, and isSidebarMode are fully independent — any combination is valid
 *   - Falls back to OS prefers-color-scheme for dark mode when no localStorage value exists
 *   - isSidebarMode defaults to false (top header is the default chrome layout)
 *   - useTheme throws if called outside ThemeProvider
 */
import { createContext, useContext, useEffect, useState } from 'react';

const THEME_KEY = 'mhmw-theme';
const OLD_MAN_KEY = 'mhmw-old-man';
const SIDEBAR_MODE_KEY = 'mhmw-sidebar-mode';

const ThemeContext = createContext(null);

function getInitialDark() {
  if (typeof window === 'undefined') return false;
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === 'dark') return true;
  if (stored === 'light') return false;
  // Legacy: 'old-man' was light-based
  if (stored === 'old-man') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function getInitialOldMan() {
  if (typeof window === 'undefined') return false;
  const stored = localStorage.getItem(OLD_MAN_KEY);
  if (stored === 'true') return true;
  if (stored === 'false') return false;
  // Legacy: if theme was 'old-man', migrate to old man mode on
  const theme = localStorage.getItem(THEME_KEY);
  return theme === 'old-man';
}

function getInitialSidebarMode() {
  if (typeof window === 'undefined') return false;
  // Default off: top header is the default layout. Only explicit 'true' enables the rail.
  return localStorage.getItem(SIDEBAR_MODE_KEY) === 'true';
}

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(getInitialDark);
  const [isOldMan, setIsOldMan] = useState(getInitialOldMan);
  const [isSidebarMode, setIsSidebarMode] = useState(getInitialSidebarMode);

  useEffect(() => {
    const root = document.documentElement;
    isDark ? root.classList.add('dark') : root.classList.remove('dark');
    localStorage.setItem(THEME_KEY, isDark ? 'dark' : 'light');
  }, [isDark]);

  useEffect(() => {
    const root = document.documentElement;
    isOldMan ? root.classList.add('old-man') : root.classList.remove('old-man');
    localStorage.setItem(OLD_MAN_KEY, String(isOldMan));
  }, [isOldMan]);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_MODE_KEY, String(isSidebarMode));
  }, [isSidebarMode]);

  const toggleDark = () => setIsDark((prev) => !prev);
  const toggleOldMan = () => setIsOldMan((prev) => !prev);
  const toggleSidebarMode = () => setIsSidebarMode((prev) => !prev);

  return (
    <ThemeContext.Provider value={{ isDark, isOldMan, isSidebarMode, toggleDark, toggleOldMan, toggleSidebarMode }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
