import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './contexts/ThemeContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { WebSocketProvider } from './contexts/WebSocketContext';
import { PendingCommandsProvider } from './contexts/PendingCommandsContext';
import MainLayout from './components/layout/MainLayout';
import Login from './pages/Login';
import ChangePassword from './pages/ChangePassword';
import Setup from './pages/Setup';
import useCommandNotifications from './hooks/useCommandNotifications';
import CommandApprovalToast from './components/common/CommandApprovalBanner';

const GitIntegrations = lazy(() => import('./pages/GitIntegrations'));
const AppSec = lazy(() => import('./pages/AppSec'));
const GettingStarted = lazy(() => import('./pages/GettingStarted'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Assessments = lazy(() => import('./pages/Assessments'));
const AssessmentDetail = lazy(() => import('./pages/AssessmentDetail'));
const Schedules = lazy(() => import('./pages/Schedules'));
const Guide = lazy(() => import('./pages/Guide'));
const Board = lazy(() => import('./pages/Board'));
const RunDashboard = lazy(() => import('./pages/RunDashboard'));
const Takeover = lazy(() => import('./pages/Takeover'));
const Commands = lazy(() => import('./pages/Commands'));
const Settings = lazy(() => import('./pages/Settings'));
const Users = lazy(() => import('./pages/Users'));

// Notifications wrapper component
function NotificationHandler() {
  useCommandNotifications();
  return null;
}

function AuthGate({ children }) {
  const { isAuthenticated, loading, mustChangePassword, setupRequired } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-neutral-50 dark:bg-neutral-900">
        <div className="text-neutral-500 dark:text-neutral-400">Loading...</div>
      </div>
    );
  }

  if (setupRequired) {
    return <Setup />;
  }

  if (!isAuthenticated) {
    return <Login />;
  }

  if (mustChangePassword) {
    return <ChangePassword />;
  }

  return children;
}

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <AuthGate>
            <WebSocketProvider>
              <PendingCommandsProvider>
                <NotificationHandler />
                <CommandApprovalToast />
                <Suspense fallback={<div className="p-6 text-neutral-500 dark:text-neutral-400">Loading page…</div>}>
                  <Routes>
                  <Route path="/" element={<MainLayout />}>
                    <Route index element={<Dashboard />} />
                    <Route path="getting-started" element={<GettingStarted />} />
                    <Route path="assessments" element={<Assessments />} />
                    <Route path="assessments/:id" element={<AssessmentDetail />} />
                    <Route path="appsec/integrations" element={<GitIntegrations />} />
                    <Route path="appsec" element={<AppSec />} />
                    <Route path="board" element={<Board />} />
                    <Route path="schedules" element={<Schedules />} />
                    <Route path="guide" element={<Guide />} />
                    <Route path="runs/:id?" element={<RunDashboard />} />
                    <Route path="takeover" element={<Takeover />} />
                    <Route path="commands" element={<Commands />} />
                    <Route path="users" element={<Users />} />
                    <Route path="settings" element={<Settings />} />
                  </Route>
                  </Routes>
                </Suspense>
              </PendingCommandsProvider>
            </WebSocketProvider>
          </AuthGate>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
