import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Shield, Activity, LogOut, User } from 'lucide-react';
import { getHealth } from '../api/switches';

export default function Navbar({ onOpenSystemStatus }) {
  const { user, logoutUser, isAuthenticated } = useAuth();
  const [isBackendHealthy, setIsBackendHealthy] = useState(null);

  useEffect(() => {
    let isMounted = true;
    const checkHealth = async () => {
      try {
        const res = await getHealth();
        if (isMounted) setIsBackendHealthy(res?.status === 'ok');
      } catch {
        if (isMounted) setIsBackendHealthy(false);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="navbar">
      <div className="nav-brand">
        <div className="brand-icon-wrapper">
          <Shield size={16} />
        </div>
        <div className="brand-text">
          <span className="brand-title">Dead Hand</span>
          <span className="brand-subtitle">Automated Fail-Safe Protocol</span>
        </div>
      </div>

      <div className="nav-actions">
        <button
          className="nav-status-pill"
          onClick={onOpenSystemStatus}
          title="View system status and background workers"
        >
          <span
            className="status-dot"
            style={{
              backgroundColor: isBackendHealthy === false ? 'var(--red)' : 'var(--green)',
            }}
          />
          <span>{isBackendHealthy === false ? 'API Offline' : 'System Online'}</span>
          <Activity size={12} style={{ marginLeft: 2 }} />
        </button>

        {isAuthenticated && user && (
          <>
            <div className="user-badge">
              <User size={12} />
              <span className="user-email-text" title={user.email}>
                {user.email}
              </span>
            </div>

            <button
              className="btn btn-secondary btn-sm"
              onClick={logoutUser}
              title="Sign Out"
            >
              <LogOut size={13} />
              <span>Sign Out</span>
            </button>
          </>
        )}
      </div>
    </header>
  );
}
