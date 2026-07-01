// Lightweight app-wide confirmation modal. Lets any component (no
// matter how deep) request a yes/no from the user without prop-drilling
// a "modal state" through the tree. Works like `window.confirm` (returns
// a promise that resolves to `true` on confirm, `false` on cancel) but
// renders a styled in-app modal that matches the rest of the Replit-mini
// chrome (no browser-native popup, no theme clashing).
//
// Usage:
//   if (!await askConfirm({ title: 'Delete?', message: '...', danger: true })) return;
//
// The modal itself is mounted once at the top of <App>; this module
// keeps a single listener set and resolves the most recent request.

let currentResolve = null;
const listeners = new Set();

/**
 * Open a confirmation modal and wait for the user to confirm or cancel.
 * @param {object} opts
 * @param {string} opts.title         Heading text (e.g. "Delete file?").
 * @param {string} opts.message       Body text describing the action.
 * @param {string} [opts.confirmLabel] Custom label for the confirm button.
 * @param {string} [opts.cancelLabel]  Custom label for the cancel button.
 * @param {boolean} [opts.danger]     Style the confirm button as a destructive action.
 * @returns {Promise<boolean>}        True on confirm, false on cancel/backdrop/Esc.
 */
export function askConfirm({
  title,
  message,
  confirmLabel = 'OK',
  cancelLabel = 'Cancel',
  danger = false,
} = {}) {
  // If a prior askConfirm is still pending (unlikely in practice — the
  // modal blocks input via the backdrop), resolve it as cancelled so
  // we don't leak a hung promise.
  if (currentResolve) currentResolve(false);
  return new Promise((resolve) => {
    currentResolve = resolve;
    listeners.forEach((l) => l({ title, message, confirmLabel, cancelLabel, danger }));
  });
}

// Imperative handle for the mounted <ConfirmHost>. The host calls
// `subscribe` on mount and `unsubscribe` on unmount, and the helpers
// above push new requests through every subscribed listener.
export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

// Called by the host when the user picks a side.
export function _resolve(value) {
  if (!currentResolve) return;
  const r = currentResolve;
  currentResolve = null;
  r(value);
  // Tell the host to clear its state. The host is the only listener
  // we care about, but iterating is cheap and keeps the API symmetric.
  listeners.forEach((l) => l(null));
}
