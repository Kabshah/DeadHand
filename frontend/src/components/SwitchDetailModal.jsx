import React from 'react';
import { X, Shield, Clock, Calendar, Mail, AlertCircle } from 'lucide-react';

export default function SwitchDetailModal({ isOpen = true, onClose, switchItem }) {
  if (!isOpen || !switchItem) return null;

  const formatDate = (isoString) => {
    if (!isoString) return '—';
    const date = new Date(isoString);
    return `${date.toLocaleString()} (${Intl.DateTimeFormat().resolvedOptions().timeZone})`;
  };

  const formatUtc = (isoString) => {
    if (!isoString) return '—';
    return new Date(isoString).toUTCString();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-container" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-wrap">
            <Shield size={18} style={{ color: 'var(--text-muted)' }} />
            <h2>Dead Hand Inspection // #DH-{String(switchItem.id).padStart(4, '0')}</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close modal">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body" style={{ gap: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div style={{ background: 'var(--bg-app)', padding: 12, borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Current Status</div>
              <div style={{ fontSize: '1rem', fontWeight: 700, marginTop: 4, textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>
                {switchItem.status}
              </div>
            </div>

            <div style={{ background: 'var(--bg-app)', padding: 12, borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Optimistic Version</div>
              <div style={{ fontSize: '1rem', fontWeight: 700, marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                v{switchItem.version}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, background: 'var(--bg-input)', padding: 16, borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
            <div>
              <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Mail size={13} /> Recipient Target
              </span>
              <div style={{ fontSize: '0.95rem', fontWeight: 600, marginTop: 2 }}>{switchItem.recipient_email}</div>
            </div>

            <div>
              <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Clock size={13} /> Check-in Interval
              </span>
              <div style={{ fontSize: '0.95rem', fontWeight: 600, marginTop: 2 }}>
                {parseFloat(Number(switchItem.interval_hours).toFixed(2))} Hours ({Math.round(switchItem.interval_hours * 60)} Minutes)
              </div>
            </div>

            <div>
              <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Clock size={13} /> Next Impending Deadline
              </span>
              <div style={{ fontSize: '0.9rem', fontWeight: 600, marginTop: 2, color: 'var(--text-primary)' }}>
                {formatDate(switchItem.next_deadline)}
              </div>
              <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                UTC: {formatUtc(switchItem.next_deadline)}
              </div>
            </div>

            {switchItem.sent_at && (
              <div>
                <span style={{ fontSize: '0.76rem', color: 'var(--red)', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <AlertCircle size={13} /> Reveal Email Dispatched
                </span>
                <div style={{ fontSize: '0.9rem', fontWeight: 600, marginTop: 2 }}>
                  {formatDate(switchItem.sent_at)}
                </div>
              </div>
            )}

            <div>
              <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Calendar size={13} /> Switch Arm Date
              </span>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: 2 }}>
                {formatDate(switchItem.created_at)}
              </div>
            </div>
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
