// ActivityBar — the narrow vertical strip on the left edge.
//
// Holds the Explorer toggle at the top and a Settings cog at the
// bottom (separated by a flex spacer). This is the same layout VS
// Code uses, so users already know where to look.

import './ActivityBar.css';

export default function ActivityBar({
  sidebarVisible,
  settingsOpen,
  onToggleSidebar,
  onToggleSettings,
}) {
  return (
    <nav className="activity-bar" aria-label="Activity bar">
      <button
        className={'activity-btn' + (sidebarVisible ? ' active' : '')}
        title="Explorer (Ctrl+B)"
        aria-label="Explorer"
        onClick={onToggleSidebar}
      >
        <span className="ab-icon">🗂</span>
      </button>
      <span className="activity-spacer" />
      <button
        className={'activity-btn activity-settings' + (settingsOpen ? ' active' : '')}
        title="Settings"
        aria-label="Settings"
        onClick={onToggleSettings}
      >
        <span className="ab-icon">⚙</span>
      </button>
    </nav>
  );
}
