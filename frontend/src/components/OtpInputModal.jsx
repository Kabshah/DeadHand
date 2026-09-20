import React, { useState, useRef, useEffect } from 'react';
import { KeyRound, RefreshCw, AlertCircle, ShieldCheck } from 'lucide-react';
import { requestOtp } from '../api/otp';
import { useToast } from '../context/ToastContext';

export default function OtpInputModal({
  isOpen,
  onClose,
  onSubmit,
  title = 'Verify Security Code',
  description = 'A 6-digit confirmation code has been dispatched to your email.',
  purpose,
  isSubmitting = false,
  submitLabel = 'Confirm Action',
}) {
  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [resendCooldown, setResendCooldown] = useState(30);
  const [isResending, setIsResending] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const inputRefs = useRef([]);
  const toast = useToast();

  useEffect(() => {
    if (isOpen) {
      setDigits(['', '', '', '', '', '']);
      setErrorMessage('');
      setResendCooldown(30);
      setTimeout(() => {
        inputRefs.current[0]?.focus();
      }, 150);
    }
  }, [isOpen]);

  useEffect(() => {
    let timer;
    if (resendCooldown > 0 && isOpen) {
      timer = setInterval(() => {
        setResendCooldown((prev) => prev - 1);
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [resendCooldown, isOpen]);

  if (!isOpen) return null;

  const handleDigitChange = (index, value) => {
    // Only accept numeric characters
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
    if (e.key === 'Enter') {
      const code = digits.join('');
      if (code.length === 6) {
        handleSubmit();
      }
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').trim();
    if (/^\d{6}$/.test(pasted)) {
      const chars = pasted.split('');
      setDigits(chars);
      inputRefs.current[5]?.focus();
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0 || isResending) return;
    setIsResending(true);
    setErrorMessage('');
    try {
      await requestOtp(purpose, true);
      toast.success('New OTP requested and sent to your email');
      setResendCooldown(45);
      setDigits(['', '', '', '', '', '']);
      inputRefs.current[0]?.focus();
    } catch (err) {
      if (err.status === 429) {
        setErrorMessage(`Rate limit exceeded. Please wait ${err.retryAfter || 60} seconds before requesting again.`);
      } else {
        setErrorMessage(err.message || 'Failed to resend OTP.');
      }
    } finally {
      setIsResending(false);
    }
  };

  const handleSubmit = () => {
    const code = digits.join('');
    if (code.length !== 6) {
      setErrorMessage('Please enter the full 6-digit code.');
      return;
    }
    onSubmit(code, setErrorMessage);
  };

  const fullCode = digits.join('');

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-container" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-wrap">
            <KeyRound size={18} style={{ color: 'var(--text-muted)' }} />
            <h2>{title}</h2>
          </div>
        </div>

        <div className="modal-body">
          <div className="otp-stage-box">
            <div className="otp-icon-shield">
              <ShieldCheck size={24} />
            </div>
            <p className="otp-instruction">{description}</p>

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
                disabled={resendCooldown > 0 || isResending}
                onClick={handleResend}
              >
                {isResending ? (
                  'Dispatching...'
                ) : resendCooldown > 0 ? (
                  `Resend in ${resendCooldown}s`
                ) : (
                  'Resend Code'
                )}
              </button>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={fullCode.length !== 6 || isSubmitting}
          >
            {isSubmitting ? (
              <>
                <RefreshCw size={15} className="animate-spin" />
                <span>Verifying...</span>
              </>
            ) : (
              submitLabel
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
