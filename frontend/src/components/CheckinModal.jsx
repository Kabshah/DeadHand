import React, { useState, useRef, useEffect } from 'react';
import { X, RefreshCw, KeyRound, Clock, AlertCircle, CheckCircle2 } from 'lucide-react';
import { requestOtp } from '../api/otp';
import { checkinSwitch } from '../api/switches';
import { useToast } from '../context/ToastContext';

export default function CheckinModal({ isOpen = true, onClose, switchItem, onSuccess }) {
  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [isRequestingOtp, setIsRequestingOtp] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [resendCooldown, setResendCooldown] = useState(30);

  const inputRefs = useRef([]);
  const toast = useToast();

  useEffect(() => {
    if (isOpen && switchItem) {
      setDigits(['', '', '', '', '', '']);
      setErrorMessage('');
      setResendCooldown(30);

      // Auto-trigger OTP request on opening
      const triggerOtp = async () => {
        setIsRequestingOtp(true);
        try {
          await requestOtp(`checkin:${switchItem.id}`, false);
          toast.success(`Check-in code sent to your email`);
        } catch (err) {
          if (err.status === 409) {
            toast.info('An OTP is already active. Enter your code or click resend.');
          } else if (err.status === 429) {
            setErrorMessage(`Rate limit hit. Wait ${err.retryAfter || 60} seconds.`);
          } else {
            setErrorMessage(err.message || 'Failed to dispatch check-in code.');
          }
        } finally {
          setIsRequestingOtp(false);
          setTimeout(() => {
            inputRefs.current[0]?.focus();
          }, 150);
        }
      };

      triggerOtp();
    }
  }, [isOpen, switchItem]);

  useEffect(() => {
    let timer;
    if (resendCooldown > 0 && isOpen) {
      timer = setInterval(() => {
        setResendCooldown((prev) => prev - 1);
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [resendCooldown, isOpen]);

  if (!isOpen || !switchItem) return null;

  const handleDigitChange = (index, value) => {
    const char = value.slice(-1);
    if (char && !/^\d$/.test(char)) return;

    const newDigits = [...digits];
    newDigits[index] = char;
    setDigits(newDigits);
    setErrorMessage('');

    if (char && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').trim();
    if (/^\d{6}$/.test(pasted)) {
      setDigits(pasted.split(''));
      inputRefs.current[5]?.focus();
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0 || isRequestingOtp) return;
    setIsRequestingOtp(true);
    setErrorMessage('');
    try {
      await requestOtp(`checkin:${switchItem.id}`, true);
      toast.success('Fresh check-in code sent to your email');
      setResendCooldown(45);
      setDigits(['', '', '', '', '', '']);
      inputRefs.current[0]?.focus();
    } catch (err) {
      if (err.status === 429) {
        setErrorMessage(`Rate limit hit. Wait ${err.retryAfter || 60} seconds.`);
      } else {
        setErrorMessage(err.message || 'Failed to resend code.');
      }
    } finally {
      setIsRequestingOtp(false);
    }
  };

  const handleSubmit = async () => {
    const otpCode = digits.join('');
    if (otpCode.length !== 6) {
      setErrorMessage('Please enter the 6-digit confirmation code.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage('');
    try {
      const updated = await checkinSwitch(switchItem.id, otpCode);
      toast.success(`Check-in verified! Deadline extended.`);
      onSuccess(updated);
      onClose();
    } catch (err) {
      if (err.status === 401) {
        setErrorMessage('Invalid or expired OTP code.');
      } else if (err.status === 410) {
        setErrorMessage('Switch is no longer active (may have triggered or been cancelled).');
      } else if (err.status === 429) {
        setErrorMessage(`Too many attempts. Wait ${err.retryAfter || 60} seconds.`);
      } else {
        setErrorMessage(err.message || 'Check-in failed.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const fullCode = digits.join('');

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-container" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-wrap">
            <RefreshCw size={20} color="#10b981" />
            <h2>Check In // Extend Deadline</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close modal">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <div style={{ background: 'var(--bg-app)', padding: 14, borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Target Switch:</span>
              <span className="mono" style={{ fontWeight: 600 }}>#DMS-{String(switchItem.id).padStart(4, '0')}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Extension Interval:</span>
              <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>+{switchItem.interval_hours} Hours</span>
            </div>
          </div>

          <div className="otp-stage-box">
            <div className="otp-icon-shield" style={{ background: 'var(--green-bg)', color: 'var(--green)' }}>
              <KeyRound size={22} />
            </div>

            <div>
              <p className="otp-instruction">
                Enter the 6-digit confirmation code dispatched to your registered email for switch #{switchItem.id}.
              </p>
            </div>

            <div className="otp-inputs-row" onPaste={handlePaste}>
              {digits.map((digit, idx) => (
                <input
                  key={idx}
                  ref={(el) => (inputRefs.current[idx] = el)}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleDigitChange(idx, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(idx, e)}
                  className="otp-digit-input"
                  autoComplete="off"
                />
              ))}
            </div>

            {errorMessage && (
              <div className="error-banner">
                <AlertCircle size={16} />
                <span>{errorMessage}</span>
              </div>
            )}

            <div className="otp-resend-row">
              <span>Code didn't arrive?</span>
              <button
                type="button"
                className="otp-resend-btn"
                disabled={resendCooldown > 0 || isRequestingOtp}
                onClick={handleResend}
              >
                {isRequestingOtp ? 'Sending...' : resendCooldown > 0 ? `Resend in ${resendCooldown}s` : 'Resend Code'}
              </button>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-success"
            onClick={handleSubmit}
            disabled={fullCode.length !== 6 || isSubmitting}
          >
            {isSubmitting ? (
              <>
                <RefreshCw size={15} className="animate-spin" />
                <span>Verifying Check-in...</span>
              </>
            ) : (
              <>
                <CheckCircle2 size={16} />
                <span>Confirm Check-In</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
