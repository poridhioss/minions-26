// TitleBar — the top strip of the IDE.
//
// Hosts:
//  - the brand label on the left
//  - explorer / terminal mini-toggles on the right (VS Code-style)
//  - a small sandbox status pill (`sandbox <id>` or `no sandbox`)
//
// The mini-toggles here mirror the activity bar's explorer button and
// the keyboard shortcut; they're intentionally redundant so muscle
// memory from VS Code works the same way.

import './TitleBar.css';

export default function TitleBar({
  containerId,
  sidebarVisible,
  terminalVisible,
  onToggleSidebar,
  onToggleTerminal,
}) {
  return (
    <header className="titlebar">
      <div className="brand">⌬ Replit-mini</div>
      <div className="titlebar-spacer" />
      <div className="titlebar-mini">
        <button
          className={'mini-btn' + (sidebarVisible ? ' active' : '')}
          title="Toggle Explorer (Ctrl+B)"
          aria-label="Toggle Explorer"
          onClick={onToggleSidebar}
        >
          <span className="tb-icon">🗂</span>
        </button>
        <button
          className={'mini-btn' + (terminalVisible ? ' active' : '')}
          title="Toggle Terminal (Ctrl+`)"
          aria-label="Toggle Terminal"
          onClick={onToggleTerminal}
        >
          <span className="tb-icon">▭</span>
        </button>
      </div>
      <span className="muted titlebar-status">
        {containerId ? `sandbox ${containerId.slice(0, 12)}` : 'no sandbox'}
      </span>
    </header>
  );
}
