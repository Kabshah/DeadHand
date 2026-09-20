import React, { useState, useEffect } from 'react';
import { ToastProvider } from './context/ToastContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import ToastContainer from './components/ToastContainer';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import AuthCallbackPage from './pages/AuthCallbackPage';
import { Shield, RefreshCw } from 'lucide-react';

function AppContent() {
  const { isAuthenticated, isLoading } = useAuth();
  const [currentPath, setCurrentPath] = useState(window.location.pathname);

  useEffect(() => {
    const handlePopState = () => {
      setCurrentPath(window.location.pathname);
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Check if current route is the OAuth callback
  const isAuthCallback = currentPath === '/auth/callback' || window.location.hash.includes('access_token') || window.location.search.includes('access_token');

  if (isAuthCallback) {
    return (
      <AuthCallbackPage
        onComplete={() => {
          setCurrentPath('/');
          window.history.pushState({}, '', '/');
        }}
      />
    );
  }

  if (isLoading) {
    return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, background: 'var(--bg-app)' }}>
        <Shield size={36} color="var(--accent)" />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          <RefreshCw size={14} className="animate-spin" color="currentColor" />
          <span>Loading...</span>
        </div>
      </div>
    );
  }

  return isAuthenticated ? <DashboardPage /> : <LoginPage />;
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <AppContent />
        <ToastContainer />
      </AuthProvider>
    </ToastProvider>
  );
}
