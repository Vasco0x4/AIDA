import { Outlet, Link } from 'react-router-dom';
import Sidebar from './Sidebar';
import GlobalSearch from '../common/GlobalSearch';
import { useState } from 'react';
import { Sun, Moon, Compass } from 'lucide-react';
import { useTheme } from '../../contexts/ThemeContext';

const MainLayout = () => {
  const { isDark, toggleTheme } = useTheme();
  const [sidebarExpanded, setSidebarExpanded] = useState(() => {
    try { return localStorage.getItem('aida.sidebar') !== 'collapsed' && window.innerWidth >= 1024; } catch { return false; }
  });

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900">
      <a href="#main-content" className="aida-skip-link">Skip to content</a>
      {/* Sidebar - Auto-collapse */}
      <div className="fixed left-0 top-0 bottom-0 z-50">
        <Sidebar onToggle={setSidebarExpanded} />
      </div>

      {/* Main content - Dynamic padding */}
      <div className={`transition-all duration-300 ${sidebarExpanded ? 'pl-16 lg:pl-64' : 'pl-16'}`}>
        {/* Top bar */}
        <header className="sticky top-0 z-40 h-14 bg-white/95 dark:bg-neutral-800/95 backdrop-blur-sm border-b border-neutral-200 dark:border-neutral-700 flex items-center justify-between px-3 sm:px-6">
          <div className="flex-1 min-w-0 max-w-2xl">
            <GlobalSearch />
          </div>

          <div className="flex items-center gap-2 ml-3">
            <Link to="/getting-started" className="hidden md:inline-flex btn btn-secondary"><Compass size={15} /> Getting started</Link>
            <button aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'} title={isDark ? 'Switch to light theme' : 'Switch to dark theme'} onClick={toggleTheme} className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700">{isDark ? <Sun size={18} /> : <Moon size={18} />}</button>
            {/* Quick actions */}
            <button onClick={() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }))} className="hidden lg:block text-xs text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 px-2 py-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors">
              Quick search
            </button>
          </div>
        </header>

        {/* Page content */}
        <main id="main-content" className="p-4 lg:p-7 min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default MainLayout;

