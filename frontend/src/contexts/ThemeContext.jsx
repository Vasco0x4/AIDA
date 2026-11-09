/* eslint-disable react-refresh/only-export-components -- context hooks are the public API */
import { createContext, useContext, useState, useEffect } from 'react';
import apiClient from '../services/api';

const ThemeContext = createContext();

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
};

// Available color themes
const COLOR_THEMES = {
  cyan: {
    name: 'Cyan',
    colors: {
      50: '#ecfeff',
      100: '#cffafe',
      200: '#a5f3fc',
      300: '#67e8f9',
      400: '#22d3ee',
      500: '#06b6d4',
      600: '#0891b2',
      700: '#0e7490',
      800: '#155e75',
      900: '#164e63',
      950: '#083344',
    }
  },
  purple: {
    name: 'Purple',
    colors: {
      50: '#faf5ff',
      100: '#f3e8ff',
      200: '#e9d5ff',
      300: '#d8b4fe',
      400: '#c084fc',
      500: '#a855f7',
      600: '#9333ea',
      700: '#7e22ce',
      800: '#6b21a8',
      900: '#581c87',
      950: '#3b0764',
    }
  },
  indigo: {
    name: 'Indigo',
    colors: {
      50: '#eef2ff',
      100: '#e0e7ff',
      200: '#c7d2fe',
      300: '#a5b4fc',
      400: '#818cf8',
      500: '#6366f1',
      600: '#4f46e5',
      700: '#4338ca',
      800: '#3730a3',
      900: '#312e81',
      950: '#1e1b4b',
    }
  },
  emerald: {
    name: 'Emerald',
    colors: {
      50: '#ecfdf5',
      100: '#d1fae5',
      200: '#a7f3d0',
      300: '#6ee7b7',
      400: '#34d399',
      500: '#10b981',
      600: '#059669',
      700: '#047857',
      800: '#065f46',
      900: '#064e3b',
      950: '#022c22',
    }
  },
  amber: {
    name: 'Amber',
    colors: {
      50: '#fffbeb',
      100: '#fef3c7',
      200: '#fde68a',
      300: '#fcd34d',
      400: '#fbbf24',
      500: '#f59e0b',
      600: '#d97706',
      700: '#b45309',
      800: '#92400e',
      900: '#78350f',
      950: '#451a03',
    }
  },
  rose: {
    name: 'Rose',
    colors: {
      50: '#fff1f2',
      100: '#ffe4e6',
      200: '#fecdd3',
      300: '#fda4af',
      400: '#fb7185',
      500: '#f43f5e',
      600: '#e11d48',
      700: '#be123c',
      800: '#9f1239',
      900: '#881337',
      950: '#4c0519',
    }
  }
};

export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState('light');
  const [primaryColor, setPrimaryColor] = useState('cyan');
  const [loading, setLoading] = useState(true);

  // Load theme from backend once an auth token is present. We listen to a
  // custom event so we react both to login and to logout (auth-cleared)
  // without re-fetching protected endpoints while logged out.
  useEffect(() => {
    const tryLoad = () => {
      if (localStorage.getItem('aida_token')) {
        loadTheme();
        loadPrimaryColor();
      } else {
        // No token: stay on local defaults, don't hit protected endpoints.
        setLoading(false);
      }
    };
    tryLoad();
    window.addEventListener('aida:auth-loaded', tryLoad);
    window.addEventListener('aida:auth-cleared', tryLoad);
    return () => {
      window.removeEventListener('aida:auth-loaded', tryLoad);
      window.removeEventListener('aida:auth-cleared', tryLoad);
    };
  }, []);

  // Apply theme to document
  useEffect(() => {
    const root = window.document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [theme]);

  // Apply primary color CSS variables
  useEffect(() => {
    const root = window.document.documentElement;
    const colors = COLOR_THEMES[primaryColor]?.colors || COLOR_THEMES.cyan.colors;

    Object.entries(colors).forEach(([shade, value]) => {
      root.style.setProperty(`--color-primary-${shade}`, value);
    });
  }, [primaryColor]);

  const loadTheme = async () => {
    try {
      const { data } = await apiClient.get('/system/settings/theme');
      setTheme(data.value || 'light');
    } catch (error) {
      // If theme setting doesn't exist, use light as default
      console.log('Theme setting not found, using default light theme');
      setTheme('light');
    } finally {
      setLoading(false);
    }
  };

  const loadPrimaryColor = async () => {
    try {
      const { data } = await apiClient.get('/system/settings/primary_color');
      setPrimaryColor(data.value || 'cyan');
    } catch (error) {
      // If color setting doesn't exist, use cyan as default
      console.log('Primary color setting not found, using default cyan');
      setPrimaryColor('cyan');
    }
  };

  const saveTheme = async (newTheme) => {
    try {
      await apiClient.put('/system/settings/theme', {
        value: newTheme
      });
    } catch (error) {
      console.error('Failed to save theme:', error);
    }
  };

  const savePrimaryColor = async (colorKey) => {
    try {
      await apiClient.put('/system/settings/primary_color', {
        value: colorKey
      });
    } catch (error) {
      console.error('Failed to save primary color:', error);
    }
  };

  const toggleTheme = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    saveTheme(newTheme);
  };

  const setThemeMode = (mode) => {
    if (mode === 'dark' || mode === 'light') {
      setTheme(mode);
      saveTheme(mode);
    }
  };

  const setPrimaryColorTheme = (colorKey) => {
    if (COLOR_THEMES[colorKey]) {
      setPrimaryColor(colorKey);
      savePrimaryColor(colorKey);
    }
  };

  const value = {
    theme,
    toggleTheme,
    setTheme: setThemeMode,
    isDark: theme === 'dark',
    primaryColor,
    setPrimaryColor: setPrimaryColorTheme,
    colorThemes: COLOR_THEMES,
    loading
  };

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};
