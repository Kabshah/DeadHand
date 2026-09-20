import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Shield, Lock, KeyRound, Clock, Mail, CheckCircle2, ArrowRight, AlertTriangle } from 'lucide-react';

export default function LoginPage() {
  const { loginWithGoogle } = useAuth();
  const [isRedirecting, setIsRedirecting] = useState(false);

  // Read rate limit cooldown from URL if redirected by backend
  const [cooldown, setCooldown] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('error') === 'rate_limit') {
      const wait = parseInt(params.get('retry_after') || '60', 10);
      return isNaN(wait) || wait <= 0 ? 60 : wait;
    }
    return 0;
  });

  // Ticking countdown timer
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => {
      setCooldown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          window.history.replaceState({}, document.title, window.location.pathname);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  const handleGoogleClick = () => {
    if (cooldown > 0) return;
    setIsRedirecting(true);
    loginWithGoogle();
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      padding: '40px 20px',
      background: 'var(--bg-app)',
    }}>
      {/* Top wordmark */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 44 }}>
        <div style={{
          width: 38, height: 38, borderRadius: 'var(--radius-md)',
          background: 'var(--green-bg)', border: '1px solid var(--green-border)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--green)',
        }}>
          <Shield size={22} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
          <span style={{ fontWeight: 800, fontSize: '1.15rem', letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
            Dead Hand
          </span>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 500 }}>
            Enterprise Safe
          </span>
        </div>
      </div>

      <div style={{ maxWidth: 880, width: '100%', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 48, alignItems: 'center' }}>

        {/* Left: Hero Information */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '4px 10px', borderRadius: 'var(--radius-full)',
              background: 'var(--green-bg)', border: '1px solid var(--green-border)',
              color: 'var(--green)', fontSize: '0.75rem', fontWeight: 600,
              marginBottom: 14,
            }}>
              <CheckCircle2 size={13} />
              <span>Automated Fail-Safe Protocol</span>
            </div>
            <h1 style={{ fontSize: '2rem', fontWeight: 800, lineHeight: 1.2, letterSpacing: '-0.03em', marginBottom: 12 }}>
              Secure automated<br />
              emergency disclosures.
            </h1>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.92rem', lineHeight: 1.65, maxWidth: 380 }}>
              Safeguard confidential credentials, messages, and instructions. If you miss a scheduled check-in, they're automatically decrypted and delivered.
            </p>
          </div>

          {/* Feature list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 4 }}>
            {[
              { icon: <Lock size={15} />, label: 'Fernet AES-256 encryption at rest' },
              { icon: <KeyRound size={15} />, label: 'Purpose-bound OTP verification on sensitive actions' },
              { icon: <Clock size={15} />, label: 'Automated periodic deadline monitoring' },
              { icon: <Mail size={15} />, label: 'Automated emergency secret dispatch via SMTP' },
            ].map(({ icon, label }) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--green)', flexShrink: 0 }}>{icon}</span>
                <span>{label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Focused Google Auth Card */}
        <div style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-xl)',
          padding: '36px 30px',
          boxShadow: 'var(--shadow-md)',
          display: 'flex',
          flexDirection: 'column',
          gap: 20,
        }}>
          <div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: 6, letterSpacing: '-0.02em' }}>
              Sign In
            </h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
              Authenticate with your Google account to access your encrypted switch vault.
            </p>
          </div>

          {/* Live Rate Limit Alert Banner */}
          {cooldown > 0 && (
            <div style={{
              background: 'var(--amber-bg)',
              border: '1px solid var(--amber-border)',
              borderRadius: 'var(--radius-md)',
              padding: '12px 14px',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 10,
              fontSize: '0.82rem',
              color: 'var(--amber)',
              lineHeight: 1.5,
              animation: 'slide-up 200ms ease-out',
            }}>
              <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 2 }} />
              <div>
                <div style={{ fontWeight: 700, marginBottom: 2 }}>
                  Rate Limit Active (1 Login per IP)
                </div>
                <div>
                  Too many login attempts from your IP address. For your security, you can retry in{' '}
                  <strong style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
                    {cooldown}s
                  </strong>.
                </div>
              </div>
            </div>
          )}

          {/* Google OAuth Button */}
          <button
            type="button"
            onClick={handleGoogleClick}
            disabled={isRedirecting || cooldown > 0}
            style={{
              width: '100%',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12,
              padding: '12px 18px',
              background: cooldown > 0 ? 'var(--bg-elevated)' : '#ffffff',
              color: cooldown > 0 ? 'var(--text-muted)' : '#1f2937',
              fontWeight: 600,
              fontSize: '0.92rem',
              border: '1px solid #cbd5e1',
              borderRadius: 'var(--radius-md)',
              cursor: isRedirecting || cooldown > 0 ? 'not-allowed' : 'pointer',
              boxShadow: cooldown > 0 ? 'none' : 'var(--shadow-xs)',
              transition: 'all var(--ease-fast)',
              opacity: cooldown > 0 ? 0.75 : 1,
            }}
            onMouseEnter={e => {
              if (!isRedirecting && cooldown <= 0) {
                e.currentTarget.style.background = '#f8fafc';
                e.currentTarget.style.borderColor = '#94a3b8';
                e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
              }
            }}
            onMouseLeave={e => {
              if (cooldown <= 0) {
                e.currentTarget.style.background = '#ffffff';
                e.currentTarget.style.borderColor = '#cbd5e1';
                e.currentTarget.style.boxShadow = 'var(--shadow-xs)';
              }
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
            </svg>
            <span>
              {isRedirecting
                ? 'Connecting to Google...'
                : cooldown > 0
                ? `Retry available in ${cooldown}s`
                : 'Continue with Google'}
            </span>
            {!isRedirecting && cooldown <= 0 && (
              <ArrowRight size={16} style={{ color: 'var(--text-muted)' }} />
            )}
          </button>

          {/* Security footnote */}
          <div style={{
            paddingTop: 16,
            borderTop: '1px solid var(--border-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              <Lock size={12} style={{ color: 'var(--green)' }} />
              <span>OAuth 2.0 PKCE Verified Authentication</span>
            </div>
            <p style={{ fontSize: '0.73rem', color: 'var(--text-faint)', lineHeight: 1.5 }}>
              By continuing, you agree to access your account via verified Google identity. Access is restricted to authorized credentials.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
