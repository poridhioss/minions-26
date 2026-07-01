// SettingsModal — the overlay that opens when the activity bar's
// settings cog is clicked.
//
// Pure presentational: every value is read from props, every change
// is forwarded as a new options object via `onEditorOptsChange`.
// Mounted conditionally by App — when `open` is false, App doesn't
// render this component at all (and the backdrop click handler isn't
// attached).

import './SettingsModal.css';

export default function SettingsModal({
  open,
  onClose,
  terminalVisible,
  sidebarVisible,
  onToggleTerminal,
  onToggleSidebar,
  editorOpts,
  onEditorOptsChange,
  split,
  onSplitChange,
  sidebarWidth,
  onSidebarWidthChange,
}) {
  if (!open) return null;

  const setOpt = (patch) => onEditorOptsChange({ ...editorOpts, ...patch });

  return (
    <div className="settings-backdrop" onClick={onClose}>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <span>⚙ Settings</span>
          <button onClick={onClose}>✕</button>
        </div>
        <div className="settings-body">
          <label className="setting-row">
            <span>Show terminal</span>
            <input
              type="checkbox"
              checked={terminalVisible}
              onChange={(e) => onToggleTerminal(e.target.checked)}
            />
          </label>
          <label className="setting-row">
            <span>Show sidebar</span>
            <input
              type="checkbox"
              checked={sidebarVisible}
              onChange={(e) => onToggleSidebar(e.target.checked)}
            />
          </label>
          <label className="setting-row">
            <span>Minimap</span>
            <input
              type="checkbox"
              checked={editorOpts.minimap}
              onChange={(e) => setOpt({ minimap: e.target.checked })}
            />
          </label>
          <label className="setting-row">
            <span>Word wrap</span>
            <input
              type="checkbox"
              checked={editorOpts.wordWrap === 'on'}
              onChange={(e) => setOpt({ wordWrap: e.target.checked ? 'on' : 'off' })}
            />
          </label>
          <div className="setting-row">
            <span>Font size</span>
            <input
              type="range" min="10" max="24"
              value={editorOpts.fontSize}
              onChange={(e) => setOpt({ fontSize: Number(e.target.value) })}
            />
            <span className="muted">{editorOpts.fontSize}px</span>
          </div>
          <div className="setting-row">
            <span>Tab size</span>
            <input
              type="range" min="1" max="8"
              value={editorOpts.tabSize}
              onChange={(e) => setOpt({ tabSize: Number(e.target.value) })}
            />
            <span className="muted">{editorOpts.tabSize}</span>
          </div>
          <div className="setting-row">
            <span>Terminal position</span>
            <select
              value={editorOpts.terminalPosition}
              onChange={(e) => setOpt({ terminalPosition: e.target.value })}
            >
              <option value="bottom">Bottom</option>
              <option value="right">Right</option>
            </select>
          </div>
          <div className="setting-row">
            <span>Theme</span>
            <select
              value={editorOpts.theme}
              onChange={(e) => setOpt({ theme: e.target.value })}
            >
              <option value="vs-dark">Dark (default)</option>
              <option value="vs-light">Light</option>
              <option value="hc-black">High contrast</option>
            </select>
          </div>
          <div className="setting-row">
            <span>Editor split</span>
            <input
              type="range" min="15" max="90"
              value={Math.round(split * 100)}
              onChange={(e) => onSplitChange(Number(e.target.value) / 100)}
            />
            <span className="muted">{Math.round(split * 100)}%</span>
          </div>
          <div className="setting-row">
            <span>Sidebar width</span>
            <input
              type="range" min="200" max="480"
              value={sidebarWidth}
              onChange={(e) => onSidebarWidthChange(Number(e.target.value))}
            />
            <span className="muted">{sidebarWidth}px</span>
          </div>
          <div className="setting-info muted">
            Tip: the tab strip's <b>Run</b> button auto-picks
            <code> node</code>, <code>python3</code>, <code>bash</code>, or
            <code> ts-node</code> based on the file's extension. The activity bar
            on the left toggles the Explorer; the header icons toggle Explorer
            and Terminal (<code>Ctrl+B</code> / <code>Ctrl+`</code>).
            Right-click inside the editor for quick toggles.
          </div>
        </div>
      </div>
    </div>
  );
}
