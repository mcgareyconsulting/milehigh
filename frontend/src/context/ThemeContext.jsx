/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Manages dark/light theme state, persists preference to localStorage, and toggles the 'dark' class on the document root.
 * exports:
 *   ThemeProvider: Context provider that syncs theme to DOM and localStorage
 *   useTheme: Hook returning { isDark, toggleTheme }
 * imports_from: [react]
 * imported_by: [main.jsx, components/AppShell.jsx]
 * invariants:
 *   - Falls back to OS prefers-color-scheme when no localStorage value exists
 *   - useTheme throws if called outside ThemeProvider
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { createContext, useContext, useEffect, useState } from 'react';

const STORAGE_KEY = 'mhmw-theme';

const ThemeContext = createContext({
  isDark: false,
  toggleTheme: () => {},
});

function getInitialTheme() {
  if (typeof window === 'undefined') return false;
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'dark' || stored === 'light') return stored === 'dark';
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(getInitialTheme);

  useEffect(() => {
    const root = document.documentElement;
    if (isDark) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    localStorage.setItem(STORAGE_KEY, isDark ? 'dark' : 'light');
  }, [isDark]);

  const toggleTheme = () => setIsDark((prev) => !prev);

  return (
    <ThemeContext.Provider value={{ isDark, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
