import React from 'react';
import { useToastState } from '../context/ToastContext';
import { CheckCircle2, AlertTriangle, AlertOctagon, Info, X } from 'lucide-react';

export default function ToastContainer() {
  const { toasts, removeToast } = useToastState();

  if (!toasts.length) return null;

  return (
    <div className="toast-container" aria-live="polite">
      {toasts.map((t) => {
        let Icon = Info;
        if (t.type === 'success') Icon = CheckCircle2;
        if (t.type === 'warning') Icon = AlertTriangle;
        if (t.type === 'error') Icon = AlertOctagon;

        return (
          <div key={t.id} className={`toast ${t.type}`}>
            <Icon size={18} className="toast-icon" />
            <span style={{ flex: 1 }}>{t.message}</span>
            <button
              className="toast-close-btn"
              onClick={() => removeToast(t.id)}
              aria-label="Dismiss toast"
            >
              <X size={15} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
