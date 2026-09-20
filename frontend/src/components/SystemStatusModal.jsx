import React, { useState, useEffect } from 'react';
import { X, Activity, Server, Database, Cpu, ShieldCheck, CheckCircle2, AlertOctagon, RefreshCw } from 'lucide-react';
import { getHealth } from '../api/switches';

export default function SystemStatusModal({ isOpen = true, onClose }) {
  const [healthData, setHealthData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchStatus = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getHealth();
      setHealthData(data);
    } catch (err) {
      setError(err.message || 'API is not responding');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchStatus();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-container large" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-wrap">
            <Activity size={20} style={{ color: 'var(--text-secondary)' }} />
            <h2>System Diagnostics & Background Architecture</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close modal">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body" style={{ gap: 20 }}>
          {/* Live Node Status */}
          <div style={{ background: 'var(--bg-input)', padding: 18, borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 12, height: 12, borderRadius: '50%', background: error ? '#ef4444' : '#10b981', boxShadow: error ? '0 0 10px #ef4444' : '0 0 10px #10b981' }} />
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>
                  {error ? 'API Connection Offline' : 'FastAPI Cluster Status: HEALTHY'}
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  Service: {healthData?.service || 'dead-hand'} | Port: 8000
                </div>
              </div>
            </div>

            <button className="btn btn-secondary btn-sm" onClick={fetchStatus} disabled={isLoading}>
              <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
              <span>Ping</span>
            </button>
          </div>

          {/* Architecture Pipeline Explanation */}
          <div>
            <h3 style={{ fontSize: '1rem', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Server size={16} style={{ color: 'var(--text-muted)' }} /> Background Worker Pipeline (§8)
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div style={{ background: 'var(--bg-app)', border: '1px solid var(--border-subtle)', padding: 14, borderRadius: 'var(--radius-md)' }}>
                <div style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: '0.84rem', marginBottom: 4 }}>
                  1. Redis Sorted Set Tracking
                </div>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  All active Dead Hands are indexed in <code className="mono">switches:deadlines</code> with Unix timestamp scores.
                </p>
              </div>

              <div style={{ background: 'var(--bg-app)', border: '1px solid var(--border-subtle)', padding: 14, borderRadius: 'var(--radius-md)' }}>
                <div style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: '0.84rem', marginBottom: 4 }}>
                  2. Celery Beat Scanner (30 sec)
                </div>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  Periodically queries overdue keys via <code className="mono">ZRANGEBYSCORE -inf &lt;now&gt;</code> and dispatches worker tasks.
                </p>
              </div>

              <div style={{ background: 'var(--bg-app)', border: '1px solid var(--border-subtle)', padding: 14, borderRadius: 'var(--radius-md)' }}>
                <div style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: '0.84rem', marginBottom: 4 }}>
                  3. Distributed Locking & Transition
                </div>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  Acquires <code className="mono">lock:switch:id</code> and atomically shifts state <code className="mono">active → triggering</code>.
                </p>
              </div>

              <div style={{ background: 'var(--bg-app)', border: '1px solid var(--border-subtle)', padding: 14, borderRadius: 'var(--radius-md)' }}>
                <div style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: '0.84rem', marginBottom: 4 }}>
                  4. In-Memory Decrypt & Reveal
                </div>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  Fernet decrypts ciphertext only in worker memory and sends the disclosure email via authenticated SMTP.
                </p>
              </div>
            </div>
          </div>

          {/* Concurrency Guarantees */}
          <div style={{ background: 'var(--bg-app)', border: '1px solid var(--border-subtle)', padding: 14, borderRadius: 'var(--radius-md)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '0.85rem', color: 'var(--text-primary)', marginBottom: 4 }}>
              <ShieldCheck size={16} style={{ color: 'var(--green)' }} /> Concurrency & Anti-Race Protections
            </div>
            <ul style={{ paddingLeft: 18, fontSize: '0.8rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: 4 }}>
              <li><strong>Atomic GETDEL:</strong> Prevents two concurrent OTP calls from both passing.</li>
              <li><strong>HMAC Constant-Time Compare:</strong> Guards against timing attack vulnerabilities.</li>
              <li><strong>Check-in vs Trigger Race:</strong> Governed by atomic DB update <code className="mono">WHERE status='active'</code>.</li>
            </ul>
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
