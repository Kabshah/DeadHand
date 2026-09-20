import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getMe, devLogin, logout, getGoogleLoginUrl } from '../api/auth';
import { useToast } from './ToastContext';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(() => localStorage.getItem('access_token'));
  const [refreshToken, setRefreshToken] = useState(() => localStorage.getItem('refresh_token'));
  const [isLoading, setIsLoading] = useState(true);
  const toast = useToast();

  const fetchProfile = useCallback(async () => {
    try {
      const profile = await getMe();
      setUser(profile);
    } catch (err) {
      console.warn('Failed to load user profile:', err);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (accessToken) {
      fetchProfile();
    } else {
      setIsLoading(false);
    }
  }, [accessToken, fetchProfile]);

  // Listen for automatic token invalidation from API client
  useEffect(() => {
    const handleSessionExpired = () => {
      setUser(null);
      setAccessToken(null);
      setRefreshToken(null);
      toast.error('Your session has expired. Please sign in again.');
    };

    window.addEventListener('auth:session_expired', handleSessionExpired);
    return () => window.removeEventListener('auth:session_expired', handleSessionExpired);
  }, [toast]);

  const setSession = useCallback((access, refresh) => {
    localStorage.setItem('access_token', access);
    localStorage.setItem('refresh_token', refresh);
    setAccessToken(access);
    setRefreshToken(refresh);
    setIsLoading(true);
    fetchProfile();
  }, [fetchProfile]);

  const loginWithDev = useCallback(async (email) => {
    try {
      const data = await devLogin(email);
      setSession(data.access_token, data.refresh_token);
      toast.success(`Logged in successfully as ${email}`);
      return true;
    } catch (err) {
      toast.error(err.message || 'Dev login failed');
      return false;
    }
  }, [setSession, toast]);

  const loginWithGoogle = useCallback(() => {
    window.location.href = getGoogleLoginUrl();
  }, []);

  const logoutUser = useCallback(async () => {
    const token = localStorage.getItem('refresh_token');
    try {
      if (token) {
        await logout(token);
      }
    } catch (err) {
      console.warn('Backend logout failed:', err);
    } finally {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      setAccessToken(null);
      setRefreshToken(null);
      setUser(null);
      toast.info('Signed out successfully');
    }
  }, [toast]);

  const value = {
    user,
    accessToken,
    refreshToken,
    isLoading,
    isAuthenticated: Boolean(accessToken && user),
    setSession,
    loginWithDev,
    loginWithGoogle,
    logout: logoutUser,
    logoutUser,
    refreshUser: fetchProfile,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
