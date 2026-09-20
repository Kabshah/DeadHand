import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { RefreshCw, CheckCircle2, AlertCircle } from 'lucide-react';

export default function AuthCallbackPage({ onComplete }) {
  const { setSession } = useAuth();
  const [status, setStatus] = useState('processing');
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    try {
      // 1. Check URL Hash fragment (#access_token=...&refresh_token=...)
      let accessToken = null;
      let refreshToken = null;

      if (window.location.hash) {
        const hashParams = new URLSearchParams(window.location.hash.substring(1));
        accessToken = hashParams.get('access_token');
        refreshToken = hashParams.get('refresh_token');
      }

      // 2. Check query params if not in hash
      if (!accessToken || !refreshToken) {
        const queryParams = new URLSearchParams(window.location.search);
        accessToken = queryParams.get('access_token');
        refreshToken = queryParams.get('refresh_token');
      }

      if (accessToken && refreshToken) {
        setSession(accessToken, refreshToken);
        setStatus('success');
        // Clean URL to avoid leaking tokens
        window.history.replaceState({}, document.title, window.location.pathname);
        setTimeout(() => {
          if (onComplete) onComplete();
        }, 600);
      } else {
        setStatus('error');
        setErrorMessage('Authentication tokens were missing from the OAuth callback response.');
      }
    } catch (err) {
      setStatus('error');
      setErrorMessage(err.message || 'Failed to process authentication tokens.');
    }
  }, [setSession, onComplete]);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div style={{ background: 'var(--bg-modal)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-xl)', padding: '40px 30px', textAlign: 'center', maxWidth: 440, width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
        {status === 'processing' && (
          <>
            <RefreshCw size={36} style={{ color: 'var(--accent)' }} className="animate-spin" />
            <h2 style={{ fontSize: '1.25rem' }}>Verifying Credentials...</h2>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)' }}>
              Establishing secure session.
            </p>
          </>
        )}

        {status === 'success' && (
          <>
            <CheckCircle2 size={36} color="var(--green)" />
            <h2 style={{ fontSize: '1.25rem' }}>Access Granted</h2>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)' }}>
              Redirecting to your dashboard...
            </p>
          </>
        )}

        {status === 'error' && (
          <>
            <AlertCircle size={36} color="var(--red)" />
            <h2 style={{ fontSize: '1.25rem' }}>Authentication Failed</h2>
            <p style={{ fontSize: '0.88rem', color: 'var(--red)' }}>{errorMessage}</p>
            <button
              className="btn btn-primary"
              style={{ marginTop: 12 }}
              onClick={() => { window.location.href = '/'; }}
            >
              Return to Login
            </button>
          </>
        )}
      </div>
    </div>
  );
}
