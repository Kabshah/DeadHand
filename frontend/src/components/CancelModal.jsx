import React, { useState, useRef, useEffect } from 'react';
import { X, AlertTriangle, KeyRound, AlertCircle, RefreshCw, XCircle } from 'lucide-react';
import { requestOtp } from '../api/otp';
import { cancelSwitch } from '../api/switches';
import { useToast } from '../context/ToastContext';

export default function CancelModal({ isOpen = true, onClose, switchItem, onSuccess }) {
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

      const triggerOtp = async () => {
        setIsRequestingOtp(true);
        try {
          await requestOtp(`cancel:${switchItem.id}`, false);
          toast.success(`Cancellation security code dispatched to your email`);
        } catch (err) {
          if (err.status === 409) {
            toast.info('An OTP is already active. Enter your code or request a resend.');
          } else if (err.status === 429) {
            setErrorMessage(`Rate limit hit. Wait ${err.retryAfter || 60} seconds.`);
          } else {
            setErrorMessage(err.message || 'Failed to dispatch cancellation code.');
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
      await requestOtp(`cancel:${switchItem.id}`, true);
      toast.success('Fresh cancellation code sent to your email');
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
      const updated = await cancelSwitch(switchItem.id, otpCode);
      toast.warning(`Switch #DMS-${String(switchItem.id).padStart(4, '0')} has been permanently deactivated`);
      onSuccess(updated);
      onClose();
    } catch (err) {
      if (err.status === 401) {
        setErrorMessage('Invalid or expired OTP code.');
      } else if (err.status === 410) {
        setErrorMessage('Switch is already triggered or cancelled.');
      } else if (err.status === 429) {
        setErrorMessage(`Too many attempts. Wait ${err.retryAfter || 60} seconds.`);
      } else {
        setErrorMessage(err.message || 'Cancellation failed.');
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
            <AlertTriangle size={20} color="#fb7185" />
            <h2>Deactivate Dead Hand</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close modal">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <div style={{ background: 'var(--red-bg)', border: '1px solid var(--red-border)', padding: 14, borderRadius: 'var(--radius-md)', color: 'var(--red)', fontSize: '0.88rem' }}>
            <strong>Warning:</strong> Deactivating Dead Hand <strong>#DH-{String(switchItem.id).padStart(4, '0')}</strong> is irreversible. The deadline timer will be stopped and the secret will never be sent to <strong>{switchItem.recipient_email}</strong>.
          </div>

          <div className="otp-stage-box">
            <div className="otp-icon-shield" style={{ background: 'var(--red-bg)', color: 'var(--red)' }}>
              <KeyRound size={22} />
            </div>

            <div>
              <p className="otp-instruction">
                Enter the 6-digit cancellation authorization code sent to your registered email address.
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
              <span>Didn't receive code?</span>
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
            Abort
          </button>
          <button
            type="button"
            className="btn btn-danger"
            onClick={handleSubmit}
            disabled={fullCode.length !== 6 || isSubmitting}
          >
            {isSubmitting ? (
              <>
                <RefreshCw size={15} className="animate-spin" />
                <span>Deactivating...</span>
              </>
            ) : (
              <>
                <XCircle size={16} />
                <span>Authorize Cancellation</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
