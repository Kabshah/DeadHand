import React, { useState, useEffect } from 'react';
import { Mail, Clock, RefreshCw, XCircle, Info, ShieldAlert, CheckCircle2 } from 'lucide-react';

export default function SwitchCard({ switchItem, onCheckin, onCancel, onViewDetails }) {
  const [timeLeft, setTimeLeft] = useState({ days: 0, hours: 0, minutes: 0, seconds: 0, totalMs: 0 });

  useEffect(() => {
    const calculateTime = () => {
      if (switchItem.status !== 'active') {
        setTimeLeft({ days: 0, hours: 0, minutes: 0, seconds: 0, totalMs: 0 });
        return;
      }

      const deadline = new Date(switchItem.next_deadline).getTime();
      const now = new Date().getTime();
      const diff = deadline - now;

      if (diff <= 0) {
        setTimeLeft({ days: 0, hours: 0, minutes: 0, seconds: 0, totalMs: 0 });
        return;
      }

      const days = Math.floor(diff / (1000 * 60 * 60 * 24));
      const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((diff % (1000 * 60)) / 1000);

      setTimeLeft({ days, hours, minutes, seconds, totalMs: diff });
    };

    calculateTime();
    const interval = setInterval(calculateTime, 1000);
    return () => clearInterval(interval);
  }, [switchItem.next_deadline, switchItem.status]);

  const pad = (n) => String(n).padStart(2, '0');

  const isUrgent = switchItem.status === 'active' && timeLeft.totalMs > 0 && timeLeft.totalMs <= 3600 * 1000; // < 1 hour
  const isWarning = switchItem.status === 'active' && timeLeft.totalMs > 3600 * 1000 && timeLeft.totalMs <= 86400 * 1000; // < 24 hours

  // Calculate progress bar percentage
  const totalIntervalMs = (switchItem.interval_hours || 24) * 3600 * 1000;
  const progressPercent = switchItem.status === 'active'
    ? Math.max(0, Math.min(100, ((totalIntervalMs - timeLeft.totalMs) / totalIntervalMs) * 100))
    : (switchItem.status === 'triggered' ? 100 : 0);

  const getStatusClass = () => {
    switch (switchItem.status) {
      case 'active': return 'status-active';
      case 'triggering': return 'status-triggering';
      case 'triggered': return 'status-triggered';
      case 'cancelled': return 'status-cancelled';
      case 'failed_reveal': return 'status-failed';
      default: return '';
    }
  };

  const formatInterval = (hours) => {
    if (hours < 1) {
      return `${Math.round(hours * 60)} Minutes`;
    }
    if (hours >= 24 && hours % 24 === 0) {
      const days = hours / 24;
      return `${days} ${days === 1 ? 'Day' : 'Days'}`;
    }
    return `${hours} ${hours === 1 ? 'Hour' : 'Hours'}`;
  };

  return (
    <div
      className={`switch-card ${isUrgent ? 'critical-near' : ''} ${isWarning ? 'warning-near' : ''}`}
      id={`switch-card-${switchItem.id}`}
    >
      <div className="card-header-row">
        <div className="switch-id-tag">
          <span>#DH-{String(switchItem.id).padStart(4, '0')}</span>
          <span style={{ color: 'var(--border-base)' }}>•</span>
          <span title={`Interval: ${switchItem.interval_hours} hrs`}>
            {formatInterval(switchItem.interval_hours)}
          </span>
        </div>
        <span className={`status-badge ${getStatusClass()}`}>
          {switchItem.status}
        </span>
      </div>

      <div className="card-recipient-box">
        <Mail size={16} className="recipient-icon" />
        <div className="recipient-info">
          <span className="recipient-label">Recipient Target</span>
          <span className="recipient-email" title={switchItem.recipient_email}>
            {switchItem.recipient_email}
          </span>
        </div>
      </div>

      {/* Countdown Area */}
      <div
        className={`countdown-box ${isUrgent ? 'urgent' : ''} ${isWarning ? 'warning' : ''} ${switchItem.status !== 'active' ? 'inactive' : ''}`}
      >
        <div className="countdown-label">
          {switchItem.status === 'active' ? (
            isUrgent ? (
              <span style={{ color: 'var(--red)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <ShieldAlert size={12} /> CRITICAL: TRIGGER IMMINENT
              </span>
            ) : isWarning ? (
              <span style={{ color: 'var(--amber)' }}>Warning: Check-in required soon</span>
            ) : (
              'Time Remaining Until Reveal'
            )
          ) : switchItem.status === 'triggering' ? (
            'DECRYPTING & SENDING REVEAL...'
          ) : switchItem.status === 'triggered' ? (
            'SECRET DISCLOSED'
          ) : switchItem.status === 'cancelled' ? (
            'SWITCH DEACTIVATED'
          ) : (
            'DELIVERY FAILED'
          )}
        </div>

        <div className="countdown-digits">
          {switchItem.status === 'active' ? (
            timeLeft.totalMs > 0 ? (
              `${pad(timeLeft.days)}d : ${pad(timeLeft.hours)}h : ${pad(timeLeft.minutes)}m : ${pad(timeLeft.seconds)}s`
            ) : (
              '00d : 00h : 00m : 00s'
            )
          ) : switchItem.status === 'triggered' ? (
            switchItem.sent_at ? (
              `Sent: ${new Date(switchItem.sent_at).toLocaleDateString()}`
            ) : (
              'Completed'
            )
          ) : (
            '— — : — —'
          )}
        </div>
      </div>

      {/* Progress track */}
      {switchItem.status === 'active' && (
        <div className="card-progress-wrapper">
          <div className="progress-track">
            <div
              className={`progress-bar-fill ${isUrgent ? 'urgent' : isWarning ? 'warning' : ''}`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="progress-labels">
            <span>Progress</span>
            <span>{Math.round(progressPercent)}% elapsed</span>
          </div>
        </div>
      )}

      {/* Card Action Buttons */}
      <div className="card-actions-row">
        {switchItem.status === 'active' ? (
          <>
            <button
              className="btn btn-success btn-sm"
              onClick={() => onCheckin(switchItem)}
              title="Reset countdown by your interval"
            >
              <RefreshCw size={14} />
              <span>Check In</span>
            </button>

            <button
              className="btn btn-outline-danger btn-sm"
              onClick={() => onCancel(switchItem)}
              title="Permanently cancel this switch"
            >
              <XCircle size={14} />
              <span>Cancel</span>
            </button>
          </>
        ) : (
          <div style={{ flex: 1, fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            {switchItem.status === 'triggered'
              ? 'Secret revealed to recipient'
              : switchItem.status === 'cancelled'
              ? 'Manually revoked'
              : 'Standby'}
          </div>
        )}

        <button
          className="btn btn-ghost btn-sm btn-icon"
          onClick={() => onViewDetails(switchItem)}
          title="View Switch Details & Metadata"
        >
          <Info size={16} />
        </button>
      </div>
    </div>
  );
}
