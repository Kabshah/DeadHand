import React, { useState, useRef, useEffect } from 'react';
import { X, Lock, KeyRound, Shield, AlertCircle, ArrowRight, ArrowLeft, RefreshCw, CheckCircle2, Clock } from 'lucide-react';
import { requestOtp } from '../api/otp';
import { createSwitch } from '../api/switches';
import { useToast } from '../context/ToastContext';

const INTERVAL_PRESETS = [
  { label: '20 Mins (Demo)', days: 0, hours: 0, minutes: 20 },
  { label: '1 Hour', days: 0, hours: 1, minutes: 0 },
  { label: '24 Hours', days: 1, hours: 0, minutes: 0 },
  { label: '3 Days', days: 3, hours: 0, minutes: 0 },
  { label: '7 Days', days: 7, hours: 0, minutes: 0 },
  { label: '30 Days', days: 30, hours: 0, minutes: 0 },
];

function formatHumanDuration(d, h, m) {
  const parts = [];
  const daysNum = parseInt(d) || 0;
  const hoursNum = parseInt(h) || 0;
  const minsNum = parseInt(m) || 0;
  if (daysNum > 0) parts.push(`${daysNum} day${daysNum > 1 ? 's' : ''}`);
  if (hoursNum > 0) parts.push(`${hoursNum} hr${hoursNum > 1 ? 's' : ''}`);
  if (minsNum > 0) parts.push(`${minsNum} min${minsNum > 1 ? 's' : ''}`);
  return parts.length > 0 ? parts.join(', ') : '0 minutes';
}

export default function CreateSwitchModal({ isOpen = true, onClose, onSuccess }) {
  const [step, setStep] = useState(1); // 1 = Details, 2 = OTP
  const [recipientEmail, setRecipientEmail] = useState('');
  const [days, setDays] = useState(1);
  const [hours, setHours] = useState(0);
  const [minutes, setMinutes] = useState(0);
  const [secretMessage, setSecretMessage] = useState('');
  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [isRequestingOtp, setIsRequestingOtp] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [resendCooldown, setResendCooldown] = useState(30);

  const otpInputRefs = useRef([]);
  const toast = useToast();

  useEffect(() => {
    if (isOpen) {
      setStep(1);
      setRecipientEmail('');
      setDays(1);
      setHours(0);
      setMinutes(0);
      setSecretMessage('');
      setDigits(['', '', '', '', '', '']);
      setErrorMessage('');
      setResendCooldown(30);
    }
  }, [isOpen]);

  useEffect(() => {
    let timer;
    if (resendCooldown > 0 && step === 2) {
      timer = setInterval(() => {
        setResendCooldown((prev) => prev - 1);
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [resendCooldown, step]);

  if (!isOpen) return null;

  const handleProceedToOtp = async (e) => {
    e.preventDefault();
    setErrorMessage('');

    if (!recipientEmail || !/^\S+@\S+\.\S+$/.test(recipientEmail)) {
      setErrorMessage('Please enter a valid recipient email address.');
      return;
    }

    const totalHours = (parseInt(days) || 0) * 24 + (parseInt(hours) || 0) + (parseInt(minutes) || 0) / 60;
    if (totalHours <= 0) {
      setErrorMessage('Please set a check-in interval greater than 0 minutes.');
      return;
    }
    if (totalHours > 8760) {
      setErrorMessage('Interval cannot exceed 365 days (8,760 hours).');
      return;
    }

    if (!secretMessage.trim()) {
      setErrorMessage('Please provide a secret message to be safeguarded.');
      return;
    }

    setIsRequestingOtp(true);
    try {
      await requestOtp('create_switch', false);
      toast.success('Security code sent to your registered email');
      setStep(2);
      setResendCooldown(30);
      setTimeout(() => {
        otpInputRefs.current[0]?.focus();
      }, 200);
    } catch (err) {
      if (err.status === 409) {
        // Already pending OTP
        toast.info('An OTP is already pending. You can enter it or request a resend.');
        setStep(2);
        setTimeout(() => {
          otpInputRefs.current[0]?.focus();
        }, 200);
      } else if (err.status === 429) {
        setErrorMessage(`Rate limit reached. Please wait ${err.retryAfter || 60} seconds before requesting an OTP.`);
      } else {
        setErrorMessage(err.message || 'Failed to dispatch OTP code.');
      }
    } finally {
      setIsRequestingOtp(false);
    }
  };

  const handleDigitChange = (index, value) => {
    const char = value.slice(-1);
    if (char && !/^\d$/.test(char)) return;

    const newDigits = [...digits];
    newDigits[index] = char;
    setDigits(newDigits);
    setErrorMessage('');

    if (char && index < 5) {
      otpInputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      otpInputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').trim();
    if (/^\d{6}$/.test(pasted)) {
      setDigits(pasted.split(''));
      otpInputRefs.current[5]?.focus();
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0 || isRequestingOtp) return;
    setIsRequestingOtp(true);
    setErrorMessage('');
    try {
      await requestOtp('create_switch', true);
      toast.success('Fresh security code sent to your email');
      setResendCooldown(45);
      setDigits(['', '', '', '', '', '']);
      otpInputRefs.current[0]?.focus();
    } catch (err) {
      if (err.status === 429) {
        setErrorMessage(`Rate limit reached. Wait ${err.retryAfter || 60} seconds.`);
      } else {
        setErrorMessage(err.message || 'Failed to resend code.');
      }
    } finally {
      setIsRequestingOtp(false);
    }
  };

  const handleCreateSwitch = async () => {
    const otpCode = digits.join('');
    if (otpCode.length !== 6) {
      setErrorMessage('Please enter the complete 6-digit confirmation code.');
      return;
    }

    const totalHours = (parseInt(days) || 0) * 24 + (parseInt(hours) || 0) + (parseInt(minutes) || 0) / 60;

    setIsSubmitting(true);
    setErrorMessage('');
    try {
      await createSwitch({
        recipient_email: recipientEmail,
        interval_hours: Number(totalHours.toFixed(4)),
        secret_message: secretMessage,
        otp_code: otpCode,
      });

      toast.success('Dead Hand armed successfully!');
      onSuccess();
      onClose();
    } catch (err) {
      if (err.status === 401) {
        setErrorMessage('Invalid or expired OTP code. Check your email or resend.');
      } else if (err.status === 422) {
        setErrorMessage(err.message || 'Invalid parameters supplied.');
      } else if (err.status === 429) {
        setErrorMessage(`Too many OTP attempts. Rate limit window active (${err.retryAfter || 60}s).`);
      } else {
        setErrorMessage(err.message || 'Failed to arm Dead Hand.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const fullCode = digits.join('');

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-container large" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-wrap">
            <Shield size={18} style={{ color: 'var(--text-muted)' }} />
            <h2>{step === 1 ? 'Arm New Dead Hand' : 'Authorize Dead Hand Activation'}</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close modal">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          {errorMessage && (
            <div className="error-banner">
              <AlertCircle size={16} />
              <span>{errorMessage}</span>
            </div>
          )}

          {step === 1 ? (
            <form id="create-switch-form" onSubmit={handleProceedToOtp} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div className="form-group">
                <label className="form-label" htmlFor="recipient-email">
                  <span>Recipient Email Address</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Target for secret disclosure</span>
                </label>
                <input
                  id="recipient-email"
                  type="email"
                  className="input-field"
                  placeholder="confidant@example.com"
                  value={recipientEmail}
                  onChange={(e) => setRecipientEmail(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  <span>Check-in Interval</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Frequency of required check-ins</span>
                </label>

                {/* Preset quick buttons */}
                <div className="interval-preset-grid">
                  {INTERVAL_PRESETS.map((preset) => {
                    const isActive =
                      Number(days) === preset.days &&
                      Number(hours) === preset.hours &&
                      Number(minutes) === preset.minutes;
                    return (
                      <button
                        key={preset.label}
                        type="button"
                        className={`interval-preset-btn ${isActive ? 'active' : ''}`}
                        onClick={() => {
                          setDays(preset.days);
                          setHours(preset.hours);
                          setMinutes(preset.minutes);
                        }}
                      >
                        {preset.label}
                      </button>
                    );
                  })}
                </div>

                {/* Alarm-style Days : Hours : Minutes Picker */}
                <div className="alarm-timer-picker">
                  <div className="alarm-unit">
                    <input
                      type="number"
                      min="0"
                      max="365"
                      className="alarm-input"
                      value={days}
                      onChange={(e) => {
                        const val = e.target.value === '' ? '' : Math.max(0, parseInt(e.target.value) || 0);
                        setDays(val);
                      }}
                      placeholder="0"
                    />
                    <span className="alarm-unit-label">Days</span>
                  </div>

                  <span className="alarm-colon">:</span>

                  <div className="alarm-unit">
                    <input
                      type="number"
                      min="0"
                      max="23"
                      className="alarm-input"
                      value={hours}
                      onChange={(e) => {
                        const val = e.target.value === '' ? '' : Math.max(0, Math.min(23, parseInt(e.target.value) || 0));
                        setHours(val);
                      }}
                      placeholder="0"
                    />
                    <span className="alarm-unit-label">Hours</span>
                  </div>

                  <span className="alarm-colon">:</span>

                  <div className="alarm-unit">
                    <input
                      type="number"
                      min="0"
                      max="59"
                      className="alarm-input"
                      value={minutes}
                      onChange={(e) => {
                        const val = e.target.value === '' ? '' : Math.max(0, Math.min(59, parseInt(e.target.value) || 0));
                        setMinutes(val);
                      }}
                      placeholder="0"
                    />
                    <span className="alarm-unit-label">Minutes</span>
                  </div>
                </div>

                {/* Alarm summary indicator */}
                <div className="alarm-summary-badge">
                  <Clock size={14} style={{ color: 'var(--text-muted)' }} />
                  <span>
                    Deadline triggers every: <strong>{formatHumanDuration(days, hours, minutes)}</strong>
                  </span>
                </div>
              </div>

              <div className="form-group">
                <div className="form-label">
                  <span>Confidential Secret Message</span>
                  <div className="encryption-badge">
                    <Lock size={12} />
                    <span>Fernet AES-256 Encrypted At Rest</span>
                  </div>
                </div>
                <textarea
                  id="secret-message"
                  className="input-field textarea-field"
                  placeholder="Master credentials, emergency instructions, key recovery phrases..."
                  value={secretMessage}
                  onChange={(e) => setSecretMessage(e.target.value)}
                  maxLength={10000}
                  required
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {secretMessage.length} / 10,000 characters
                </div>
              </div>
            </form>
          ) : (
            <div className="otp-stage-box">
              <div className="otp-icon-shield">
                <KeyRound size={24} />
              </div>
              <div>
                <h3 style={{ fontSize: '1.1rem', marginBottom: 4 }}>Enter Verification Code</h3>
                <p className="otp-instruction">
                  To prevent unauthorized switch creation, we sent a 6-digit confirmation code to your registered email.
                </p>
              </div>

              <div className="otp-inputs-row" onPaste={handlePaste}>
                {digits.map((digit, idx) => (
                  <input
                    key={idx}
                    ref={(el) => (otpInputRefs.current[idx] = el)}
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
          )}
        </div>

        <div className="modal-footer">
          {step === 1 ? (
            <>
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                Cancel
              </button>
              <button
                type="submit"
                form="create-switch-form"
                className="btn btn-primary"
                disabled={isRequestingOtp}
              >
                {isRequestingOtp ? (
                  <>
                    <RefreshCw size={15} className="animate-spin" />
                    <span>Requesting Code...</span>
                  </>
                ) : (
                  <>
                    <span>Proceed to Verification</span>
                    <ArrowRight size={15} />
                  </>
                )}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setStep(1)}
                disabled={isSubmitting}
              >
                <ArrowLeft size={15} />
                <span>Back</span>
              </button>
              <button
                type="button"
                className="btn btn-success"
                onClick={handleCreateSwitch}
                disabled={fullCode.length !== 6 || isSubmitting}
              >
                {isSubmitting ? (
                  <>
                    <RefreshCw size={15} className="animate-spin" />
                    <span>Creating Switch...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={16} />
                    <span>Create a switch</span>
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
