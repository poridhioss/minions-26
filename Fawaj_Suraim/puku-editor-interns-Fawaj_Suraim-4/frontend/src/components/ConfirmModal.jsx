import { AlertTriangle, X } from 'lucide-react';

/**
 * Lightweight modal confirmation. Rendered inline (no portal) so it stays
 * simple to drop into any panel.
 *
 * Props:
 *   - open:      whether to show the modal
 *   - title:     header text (default 'Confirm')
 *   - message:   body text
 *   - confirmLabel: button label (default 'Delete')
 *   - cancelLabel:  button label (default 'Cancel')
 *   - danger:    if true, paints the confirm button in rose
 *   - onConfirm: called when the user confirms
 *   - onCancel:  called when the user cancels (or hits Esc / backdrop)
 */
export default function ConfirmModal({
  open,
  title = 'Confirm',
  message,
  confirmLabel = 'Delete',
  cancelLabel = 'Cancel',
  danger = true,
  onConfirm,
  onCancel,
}) {
  if (!open) return null;

  const onBackdrop = (e) => {
    if (e.target === e.currentTarget) onCancel?.();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      onClick={onBackdrop}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4 backdrop-blur-sm"
    >
      <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-2xl shadow-black/70 ring-1 ring-slate-700">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div
              className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full ring-1 ${
                danger
                  ? 'bg-rose-500/10 text-rose-300 ring-rose-500/30'
                  : 'bg-amber-500/10 text-amber-300 ring-amber-500/30'
              }`}
            >
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div>
              <h2 id="confirm-title" className="text-sm font-semibold text-slate-100">
                {title}
              </h2>
              {message && (
                <p className="mt-1 text-xs text-slate-400">{message}</p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 ring-1 ring-slate-700 hover:bg-slate-700"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold ring-1 transition ${
              danger
                ? 'bg-rose-500/15 text-rose-200 ring-rose-500/40 hover:bg-rose-500/30 hover:text-rose-100'
                : 'bg-emerald-500/15 text-emerald-200 ring-emerald-500/40 hover:bg-emerald-500/30 hover:text-emerald-100'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
