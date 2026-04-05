import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './contexts/ThemeContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { WebSocketProvider } from './contexts/WebSocketContext';
import { PendingCommandsProvider } from './contexts/PendingCommandsContext';
import MainLayout from './components/layout/MainLayout';
import Dashboard from './pages/Dashboard';
import Assessments from './pages/Assessments';
import AssessmentDetail from './pages/AssessmentDetail';
import Commands from './pages/Commands';
import Settings from './pages/Settings';
import Login from './pages/Login';
import useCommandNotifications from './hooks/useCommandNotifications';
import CommandApprovalToast from './components/common/CommandApprovalBanner';

// Notifications wrapper component
function NotificationHandler() {
  useCommandNotifications();
  return null;
}

function AuthGate({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-neutral-50 dark:bg-neutral-900">
        <div className="text-neutral-500 dark:text-neutral-400">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login />;
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
                <Routes>
                  <Route path="/" element={<MainLayout />}>
                    <Route index element={<Dashboard />} />
                    <Route path="assessments" element={<Assessments />} />
                    <Route path="assessments/:id" element={<AssessmentDetail />} />
                    <Route path="commands" element={<Commands />} />
                    <Route path="settings" element={<Settings />} />
                  </Route>
                </Routes>
              </PendingCommandsProvider>
            </WebSocketProvider>
          </AuthGate>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
