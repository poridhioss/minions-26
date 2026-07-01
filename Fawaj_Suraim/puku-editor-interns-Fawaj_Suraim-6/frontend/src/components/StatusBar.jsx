// VSCode-style status bar. Stateless: parent owns the data, this is pure layout.
export default function StatusBar({
  filePath,
  language,
  cursor,
  saved,
  dirty,
  containerId,
  terminalVisible,
  onToggleTerminal,
}) {
  return (
    <footer className="statusbar">
      <div className="sb-left">
        <button
          className="sb-item sb-toggle"
          title="Toggle terminal"
          onClick={onToggleTerminal}
        >
          {terminalVisible ? '⌄ Terminal' : '› Terminal'}
        </button>
        <span className="sb-item" title="Sandbox">
          <span className="dot" /> {containerId ? containerId.slice(0, 12) : 'no sandbox'}
        </span>
        {filePath && (
          <span className="sb-item" title="Active file">
            {filePath}
          </span>
        )}
        {dirty && <span className="sb-item warn">● unsaved</span>}
        {saved && !dirty && <span className="sb-item ok">✓ saved</span>}
      </div>

      <div className="sb-right">
        {cursor && (
          <span className="sb-item">Ln {cursor.line}, Col {cursor.column}</span>
        )}
        <span className="sb-item">Spaces: 2</span>
        <span className="sb-item">LF</span>
        <span className="sb-item">UTF-8</span>
        <span className="sb-item lang">{language}</span>
      </div>
    </footer>
  );
}
