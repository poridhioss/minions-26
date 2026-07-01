// Module-level constants for the IDE shell.
//
// Anything that's a magic number, default, or option-set used by more
// than one component lives here so we don't have to chase numbers
// through JSX.

/**
 * Default Monaco editor options. Overridden by:
 *  - the editor's right-click context menu (`EditorContextMenu`)
 *  - the Settings modal (`SettingsModal`)
 *  - localStorage under the key `replit.editor`
 */
export const DEFAULTS = {
  minimap: true,
  wordWrap: 'on',         // 'on' | 'off'
  fontSize: 14,
  tabSize: 2,
  fontFamily: 'Menlo, Consolas, "Courier New", monospace',
  renderWhitespace: 'selection', // 'none' | 'selection' | 'all' | 'boundary'
  lineNumbers: 'on',      // 'on' | 'off' | 'relative' | 'interval'
  cursorStyle: 'smooth',  // 'smooth' | 'block' | 'underline' | ...
  formatOnSave: false,
  terminalPosition: 'bottom', // 'bottom' | 'right'
  theme: 'vs-dark',       // 'vs-dark' | 'vs-light' | 'hc-black'
};

/** Maximum width the explorer sidebar can be dragged to. */
export const SIDEBAR_MAX = 480;

/**
 * Minimum width the sidebar can be resized to before it auto-hides.
 * Below this, dragging collapses the sidebar (VS Code behavior).
 */
export const SIDEBAR_MIN = 200;

/** localStorage key under which editor options are persisted. */
export const EDITOR_OPTS_KEY = 'replit.editor';
