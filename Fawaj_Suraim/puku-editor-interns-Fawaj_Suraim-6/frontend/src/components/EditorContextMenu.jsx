// EditorContextMenu — the right-click menu that appears over the
// editor surface. Mounted conditionally by App; App owns the
// open/close logic and outside-click dismissal.
//
// The menu is positioned at the click coordinates (passed via the
// `pos` prop as { x, y } in viewport space). We stop pointer events
// from bubbling on the menu itself, so a click *inside* the menu
// doesn't close it before the button's onClick handler runs.

import './EditorContextMenu.css';

export default function EditorContextMenu({
  pos,
  editorOpts,
  onEditorOptsChange,
  onClose,
}) {
  if (!pos) return null;

  const setOpt = (patch) => {
    onEditorOptsChange({ ...editorOpts, ...patch });
    onClose();
  };

  return (
    <div
      className="ctx-menu"
      style={{ top: pos.y, left: pos.x }}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        className="ctx-item ctx-check"
        onClick={() => setOpt({ minimap: !editorOpts.minimap })}
      >
        <span className="ctx-tick">{editorOpts.minimap ? '✓' : ' '}</span>
        Show minimap
      </button>
      <button
        className="ctx-item ctx-check"
        onClick={() =>
          setOpt({ wordWrap: editorOpts.wordWrap === 'on' ? 'off' : 'on' })
        }
      >
        <span className="ctx-tick">{editorOpts.wordWrap === 'on' ? '✓' : ' '}</span>
        Word wrap
      </button>
      <div className="ctx-sep" />
      <div className="ctx-row">
        <span className="ctx-tick" aria-hidden="true"> </span>
        <span className="ctx-label">Font size</span>
        <button
          className="ctx-btn"
          onClick={() =>
            onEditorOptsChange({
              ...editorOpts,
              fontSize: Math.max(10, editorOpts.fontSize - 1),
            })
          }
        >−</button>
        <span className="ctx-val">{editorOpts.fontSize}</span>
        <button
          className="ctx-btn"
          onClick={() =>
            onEditorOptsChange({
              ...editorOpts,
              fontSize: Math.min(24, editorOpts.fontSize + 1),
            })
          }
        >+</button>
      </div>
      <div className="ctx-row">
        <span className="ctx-tick" aria-hidden="true"> </span>
        <span className="ctx-label">Tab size</span>
        <button
          className="ctx-btn"
          onClick={() =>
            onEditorOptsChange({
              ...editorOpts,
              tabSize: Math.max(1, editorOpts.tabSize - 1),
            })
          }
        >−</button>
        <span className="ctx-val">{editorOpts.tabSize}</span>
        <button
          className="ctx-btn"
          onClick={() =>
            onEditorOptsChange({
              ...editorOpts,
              tabSize: Math.min(8, editorOpts.tabSize + 1),
            })
          }
        >+</button>
      </div>
      <div className="ctx-sep" />
      <div className="ctx-section">Terminal position</div>
      <button
        className="ctx-item ctx-radio"
        onClick={() => setOpt({ terminalPosition: 'bottom' })}
      >
        <span className="ctx-tick">{editorOpts.terminalPosition === 'bottom' ? '●' : '○'}</span>
        Bottom
      </button>
      <button
        className="ctx-item ctx-radio"
        onClick={() => setOpt({ terminalPosition: 'right' })}
      >
        <span className="ctx-tick">{editorOpts.terminalPosition === 'right' ? '●' : '○'}</span>
        Right
      </button>
    </div>
  );
}
