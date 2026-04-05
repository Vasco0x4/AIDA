import React, { useState, useEffect, useCallback } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Logo, LayoutDashboard, FileText, Terminal, Settings, ChevronLeft, ChevronRight } from '../icons';
import { LogOut } from 'lucide-react';
import commandSettingsService from '../../services/commandSettingsService';
import { useWebSocketContext } from '../../contexts/WebSocketContext';
import { useTheme } from '../../contexts/ThemeContext';
import { useAuth } from '../../contexts/AuthContext';

const Sidebar = ({ onToggle }) => {
  const { isDark } = useTheme();
  const { user, authRequired, logout } = useAuth();
  const location = useLocation();
  const [isExpanded, setIsExpanded] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);

  const navigation = [
    { name: 'Dashboard', href: '/', icon: LayoutDashboard },
    { name: 'Assessments', href: '/assessments', icon: FileText },
    { name: 'Commands', href: '/commands', icon: Terminal, showBadge: true },
    { name: 'Settings', href: '/settings', icon: Settings },
  ];

  const shouldShowExpanded = isExpanded || isHovered;

  // Check if we're on the assessments page to remove border
  const isAssessmentsPage = location.pathname.startsWith('/assessments');

  // WebSocket for real-time updates
  const { subscribe } = useWebSocketContext();

  // Load pending count
  const loadPendingCount = useCallback(async () => {
    try {
      const data = await commandSettingsService.getPendingCount();
      setPendingCount(data.pending_count || 0);
    } catch (error) {
      // Silently fail - badge just won't show
    }
  }, []);

  // Load on mount and subscribe to WebSocket events
  useEffect(() => {
    loadPendingCount();

    const unsubscribes = [
      subscribe('command_pending_approval', loadPendingCount),
      subscribe('command_approved', loadPendingCount),
      subscribe('command_rejected', loadPendingCount),
      subscribe('command_timeout', loadPendingCount),
    ];
    return () => unsubscribes.forEach(unsub => unsub && unsub());
  }, [subscribe, loadPendingCount]);

  // Notify parent of expansion state
  React.useEffect(() => {
    if (onToggle) {
      onToggle(shouldShowExpanded);
    }
  }, [shouldShowExpanded, onToggle]);

  return (
    <aside
      className={`h-screen bg-white dark:bg-neutral-800 ${isAssessmentsPage ? '' : 'border-r border-neutral-200 dark:border-neutral-700'} flex flex-col transition-all duration-300 ${shouldShowExpanded ? 'w-64' : 'w-16'
        }`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Toggle Button */}
      <div className="absolute -right-3 top-4 z-50">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-6 h-6 bg-white dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-600 rounded-full flex items-center justify-center shadow-sm hover:shadow-md transition-shadow"
        >
          {shouldShowExpanded ? (
            <ChevronLeft className="w-3 h-3 text-neutral-600 dark:text-neutral-300" />
          ) : (
            <ChevronRight className="w-3 h-3 text-neutral-600 dark:text-neutral-300" />
          )}
        </button>
      </div>

      {/* Logo */}
      <div className="h-14 flex items-center gap-2 px-4 border-b border-neutral-200 dark:border-neutral-700">
        <div className="w-10 h-10 flex items-center justify-center flex-shrink-0">
          <img
            src="/assets/aida-logo.png"
            alt="AIDA Logo"
            className="w-8 h-8 object-contain"
            style={{ filter: isDark ? 'invert(1)' : 'none' }}
          />
        </div>
        {shouldShowExpanded && (
          <div className="min-w-0">
            <h1 className="text-sm font-bold text-neutral-900 dark:text-neutral-100">AIDA</h1>
            <p className="text-xs text-neutral-500 dark:text-neutral-400">AI-Driven Security Assessment</p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-4 space-y-1">
        {navigation.map((item) => (
          <NavLink
            key={item.name}
            to={item.href}
            className={({ isActive }) =>
              `flex items-center gap-2 px-2 py-2 rounded-lg text-sm font-medium transition-all ${isActive
                ? 'bg-primary-100/50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-400 shadow-sm'
                : 'text-neutral-600 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700 hover:text-neutral-900 dark:hover:text-neutral-100'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <div className="relative flex-shrink-0">
                  <item.icon className={`w-5 h-5 ${isActive ? 'text-primary-500 dark:text-primary-400' : 'text-neutral-400'}`} />
                  {item.showBadge && pendingCount > 0 && (
                    <span className="absolute -top-1 -right-1 w-4 h-4 bg-amber-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center animate-pulse">
                      {pendingCount > 9 ? '9+' : pendingCount}
                    </span>
                  )}
                </div>
                {shouldShowExpanded && (
                  <span className="truncate flex-1">{item.name}</span>
                )}
                {shouldShowExpanded && item.showBadge && pendingCount > 0 && (
                  <span className="px-1.5 py-0.5 bg-amber-500 text-white text-xs font-medium rounded">
                    {pendingCount}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      {shouldShowExpanded && (
        <div className="p-3 border-t border-neutral-200 dark:border-neutral-700">
          <div className="flex items-center gap-2 px-2 py-1">
            <div className="w-7 h-7 flex items-center justify-center flex-shrink-0">
              <img
                src="/assets/aida-logo.png"
                alt="AIDA Logo"
                className="w-6 h-6 object-contain"
                style={{ filter: isDark ? 'invert(1)' : 'none' }}
              />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-neutral-900 dark:text-neutral-100 truncate">
                {authRequired && user ? user.username : 'AIDA'}
              </p>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">v1.0.0 Beta</p>
            </div>
            {authRequired && (
              <button
                onClick={logout}
                title="Sign out"
                className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      )}
      {!shouldShowExpanded && authRequired && (
        <div className="p-2 border-t border-neutral-200 dark:border-neutral-700">
          <button
            onClick={logout}
            title="Sign out"
            className="w-full flex items-center justify-center p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      )}
    </aside>
  );
};

export default Sidebar;
