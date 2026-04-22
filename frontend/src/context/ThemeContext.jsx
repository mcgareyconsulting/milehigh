/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Manages independent dark-mode and old-man-mode state, persists to localStorage, applies classes to document root.
 * exports:
 *   ThemeProvider: Context provider that syncs both theme flags to DOM and localStorage
 *   useTheme: Hook returning { isDark, isOldMan, toggleDark, toggleOldMan }
 * imports_from: [react]
 * imported_by: [main.jsx, components/AppShell.jsx, components/JobsTableRow.jsx]
 * invariants:
 *   - isDark and isOldMan are fully independent — any combination is valid
 *   - Falls back to OS prefers-color-scheme for dark mode when no localStorage value exists
 *   - useTheme throws if called outside ThemeProvider
 */
import { createContext, useContext, useEffect, useState } from 'react';

const THEME_KEY = 'mhmw-theme';
const OLD_MAN_KEY = 'mhmw-old-man';

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

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(getInitialDark);
  const [isOldMan, setIsOldMan] = useState(getInitialOldMan);

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

  const toggleDark = () => setIsDark((prev) => !prev);
  const toggleOldMan = () => setIsOldMan((prev) => !prev);

  return (
    <ThemeContext.Provider value={{ isDark, isOldMan, toggleDark, toggleOldMan }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
