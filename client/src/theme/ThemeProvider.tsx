import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type Theme = 'light' | 'dark';
export type ThemeMode = 'light' | 'dark' | 'system';

interface ThemeContextType {
  theme: Theme;
  themeMode: ThemeMode;
  toggleTheme: () => void;
  setTheme: (mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const THEME_STORAGE_KEY = 'finetune-theme';

function getSystemTheme(): Theme {
  // 强制默认使用深色主题，除非系统极度明确要求浅色
  if (typeof window === 'undefined') return 'dark';
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function getStoredThemeMode(): ThemeMode | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === 'light' || stored === 'dark' || stored === 'system') {
      return stored as ThemeMode;
    }
  } catch {
    return null;
  }
  return null;
}

function setStoredThemeMode(mode: ThemeMode): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    // Ignore storage failures, e.g. private mode or disabled localStorage.
  }
}

interface ThemeProviderProps {
  children: React.ReactNode;
  defaultTheme?: ThemeMode;
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children, defaultTheme }) => {
  const [themeMode, setThemeModeState] = useState<ThemeMode>(() => {
    const stored = getStoredThemeMode();
    if (stored) return stored;
    if (defaultTheme) return defaultTheme;
    return 'system';
  });

  const [theme, setThemeState] = useState<Theme>(() => {
    if (themeMode === 'system') return getSystemTheme();
    return themeMode;
  });

  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    const body = document.body;

    root.classList.remove('light-theme', 'dark-theme');
    body.classList.remove('light-theme', 'dark-theme');

    root.classList.add(`${theme}-theme`);
    body.classList.add(`${theme}-theme`);

    root.setAttribute('data-theme', theme);
    body.setAttribute('data-theme', theme);

    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (metaThemeColor) {
      metaThemeColor.setAttribute('content', theme === 'dark' ? '#1a1a1a' : '#faf9f7');
    }
  }, [theme]);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const handleChange = (e: MediaQueryListEvent) => {
      if (themeMode === 'system') {
        setThemeState(e.matches ? 'dark' : 'light');
      }
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [themeMode]);

  const setTheme = useCallback((newMode: ThemeMode) => {
    setThemeModeState(newMode);
    setStoredThemeMode(newMode);
    if (newMode === 'system') {
      setThemeState(getSystemTheme());
    } else {
      setThemeState(newMode);
    }
  }, []);

  const toggleTheme = useCallback(() => {
    const nextMode = theme === 'light' ? 'dark' : 'light';
    setTheme(nextMode);
  }, [theme, setTheme]);

  const value = useMemo(
    () => ({
      theme,
      themeMode,
      toggleTheme,
      setTheme,
    }),
    [theme, themeMode, toggleTheme, setTheme],
  );

  if (!mounted) {
    return (
      <ThemeContext.Provider value={value}>
        <div style={{ visibility: 'hidden' }}>{children}</div>
      </ThemeContext.Provider>
    );
  }

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export function useTheme(): ThemeContextType {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}

export default ThemeProvider;
