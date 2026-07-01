import { useEffect, useRef, useState } from 'react';
import { subscribe, _resolve } from '../confirm.js';

// Single-instance confirmation host. Mounted once near the top of
// <App>; subscribes to the global askConfirm() bus and renders a
// styled modal whenever a request is in flight. Backdrop click and
// Escape both cancel; Enter confirms (matches the inline rename/tab
// UX users already have).
export default function ConfirmHost() {
  const [req, setReq] = useState(null);
  const confirmRef = useRef(null);

  useEffect(() => subscribe(setReq), []);

  // Bind Esc + Enter while the modal is open. Use window-level keys
  // so the modal works no matter which child has focus.
  useEffect(() => {
    if (!req) return;
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); _resolve(false); }
      if (e.key === 'Enter') {
        // Don't auto-confirm when the user is typing in a field (we
        // don't have one today, but a future "type the name to confirm"
        // pattern would break if Enter hijacked the keystroke). The
        // focus check keeps it intentional.
        const tag = (e.target?.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea') return;
        e.stopPropagation();
        _resolve(true);
      }
    };
    window.addEventListener('keydown', onKey);
    // Auto-focus the confirm button so Enter (via the keydown handler)
    // confirms, and so screen readers announce the primary action.
    confirmRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [req]);

  if (!req) return null;

  return (
    <div
      className="settings-backdrop confirm-backdrop"
      onClick={() => _resolve(false)}
    >
      <div
        className="settings-modal confirm-modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-msg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="settings-header confirm-header">
          <span id="confirm-title">{req.title}</span>
        </div>
        <div className="settings-body confirm-body">
          <div id="confirm-msg" className="confirm-message">{req.message}</div>
          <div className="confirm-actions">
            <button
              className="confirm-btn confirm-cancel"
              onClick={() => _resolve(false)}
            >{req.cancelLabel}</button>
            <button
              ref={confirmRef}
              className={'confirm-btn ' + (req.danger ? 'confirm-danger' : 'confirm-primary')}
              onClick={() => _resolve(true)}
            >{req.confirmLabel}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
