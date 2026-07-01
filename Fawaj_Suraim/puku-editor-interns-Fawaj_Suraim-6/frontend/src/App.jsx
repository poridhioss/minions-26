// App — the IDE shell. Composes Sidebar / EditorPane / TerminalPane /
// StatusBar and the new chrome (TitleBar, ActivityBar, SettingsModal,
// EditorContextMenu). All editor options live in `usePersistedEditor`,
// all magic numbers and default option sets live in `constants/editor`.

import { useCallback, useEffect, useRef, useState } from 'react';
import './App.css';
import Sidebar from './components/Sidebar.jsx';
import EditorPane from './components/EditorPane.jsx';
import TerminalPane from './components/TerminalPane.jsx';
import StatusBar from './components/StatusBar.jsx';
import ConfirmHost from './components/ConfirmHost.jsx';
import TitleBar from './components/TitleBar.jsx';
import ActivityBar from './components/ActivityBar.jsx';
import SettingsModal from './components/SettingsModal.jsx';
import EditorContextMenu from './components/EditorContextMenu.jsx';
import { api } from './api.js';
import { SIDEBAR_MAX, SIDEBAR_MIN } from './constants/editor';
import { usePersistedEditor } from './hooks/usePersistedEditor';

export default function App() {
  const [containerId, setContainerId] = useState(null);
  const [tabs, setTabs] = useState([]); // [{ path, content, savedAt }]
  const [activePath, setActivePath] = useState(null);
  const [split, setSplit] = useState(0.65);          // editor height ratio
  const [sidebarWidth, setSidebarWidth] = useState(260);
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [terminalVisible, setTerminalVisible] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Right-click context menu in the editor surface. Null when closed.
  // { x, y } in viewport coordinates.
  const [editorMenu, setEditorMenu] = useState(null);
  // Fired the moment a delete succeeds in the explorer. We close the
  // matching tab (if any) so the editor immediately reflects that the
  // file is gone. If the deleted path is a *directory*, we also close
  // any tab whose path is a descendant — otherwise deleting a folder
  // leaves stale tabs in the editor pointing at files that no longer
  // exist on disk.
  //   p === '/workspace/src'         → close tab '/workspace/src/app.js'
  //   p === '/workspace/src/app.js'  → close tab '/workspace/src/app.js'
  // We also mark descendants "unsaved" by removing the entry rather
  // than keeping a zombie tab the user can no longer save to.
  const handleFileDeleted = useCallback((p) => {
    if (!p) return;
    const prefix = p.endsWith('/') ? p : p + '/';
    setTabs((cur) => {
      const next = cur.filter((t) => t.path !== p && !t.path.startsWith(prefix));
      if (next.length === cur.length) return cur;
      if (activePath === p || activePath?.startsWith(prefix)) {
        setActivePath(next[0]?.path || null);
      }
      return next;
    });
  }, [activePath]);
  // Imperative handle on the Sidebar so the editor's "+" tab can trigger
  // the sidebar's new-file input.
  const sidebarRef = useRef(null);
  // Remember the sidebar width so toggling visibility preserves the size.
  const savedSidebarWidth = useRef(260);

  // Editor settings (persisted in localStorage). Configurable via the
  // editor's right-click context menu (and the Settings modal).
  const [editorOpts, setEditorOpts] = usePersistedEditor();

  // Sync the selected theme to <body> so the surrounding chrome (sidebar,
  // activity bar, tabs, terminal) can re-skin via .theme-* CSS overrides.
  useEffect(() => {
    const t = editorOpts.theme || 'vs-dark';
    document.body.classList.remove('theme-vs-dark', 'theme-vs-light', 'theme-hc-black');
    document.body.classList.add('theme-' + t);
  }, [editorOpts.theme]);

  const wrapRef = useRef(null);
  const mainRef = useRef(null);
  const draggingSplit = useRef(false);
  const draggingSidebar = useRef(false);
  const draggingTerminal = useRef(false);
  const terminalApiRef = useRef(null); // { create(), kill(), write(data), focus() }
  const editorSaveRef = useRef(null);  // EditorPane.save() impl

  /* -------- file ops ----------------------------------------------------- */

  const openFile = useCallback(async (path) => {
    if (!containerId) return;
    const existing = tabs.find((t) => t.path === path);
    if (existing) { setActivePath(path); return; }
    try {
      const res = await api.readFile(containerId, path);
      setTabs((cur) => [...cur, { path, content: res.content, savedAt: Date.now() }]);
      setActivePath(path);
    } catch (e) {
      alert('Open failed: ' + e.message);
    }
  }, [containerId, tabs]);

  const closeTab = (path) => {
    setTabs((cur) => {
      const next = cur.filter((t) => t.path !== path);
      if (activePath === path) setActivePath(next[0]?.path || null);
      return next;
    });
  };

  const tabUpdated = (path, patch) => {
    setTabs((cur) => cur.map((t) => (t.path === path ? { ...t, ...patch } : t)));
  };

  const runActive = async () => {
    if (!containerId) return alert('Spin up a sandbox first.');
    const tab = tabs.find((t) => t.path === activePath);
    if (!tab) return alert('No file open to run.');

    // Flush dirty buffer to disk first, otherwise the sandbox runs stale text.
    if (editorSaveRef.current) {
      const ok = await editorSaveRef.current();
      if (ok === false) return; // save failed; alert already shown
    }

    const ext = (tab.path.split('.').pop() || '').toLowerCase();
    const map = {
      js: 'node', mjs: 'node', cjs: 'node',
      ts: 'npx --yes ts-node',
      py: 'python3',
      sh: 'bash', bash: 'bash',
    };
    const runner = map[ext];
    if (!runner) return alert(`No runner mapped for .${ext} — try Terminal.`);

    // Always run from the sandbox's /workspace, with an absolute file path.
    const absPath = tab.path.startsWith('/') ? tab.path : `/workspace/${tab.path}`;

    // Reuse a free terminal if one is already up (idle → program already
    // finished and the shell is back at its prompt). Only fall back to
    // opening a new "Run" tab when no live PTY exists at all.
    if (!terminalVisible) setTerminalVisible(true);
    try {
      const cmd = `cd /workspace && ${runner} ${shellQuote(absPath)}`;
      const tabId = terminalApiRef.current?.runInReusableTab?.(cmd);
      if (!tabId) {
        const fname = (tab.path.split('/').pop() || 'run');
        terminalApiRef.current?.create?.({ prefill: cmd, title: `run: ${fname}` });
      }
    } catch (e) {
      alert('Run failed: ' + e.message);
    }
  };

  // Single-quote a path for safe shell interpolation.
  const shellQuote = (s) => `'${String(s).replace(/'/g, `'\\''`)}'`;

  /* -------- resizers (editor/terminal + sidebar) ------------------------- */

  useEffect(() => {
    const onMove = (e) => {
      if (draggingSplit.current && wrapRef.current) {
        const rect = wrapRef.current.getBoundingClientRect();
        const ratio = Math.min(0.9, Math.max(0.15, (e.clientY - rect.top) / rect.height));
        setSplit(ratio);
      }
      if (draggingSidebar.current && mainRef.current) {
        const rect = mainRef.current.getBoundingClientRect();
        const w = e.clientX - rect.left;
        // Floor is the sidebar's minimum allowed width. Drag below it
        // → collapse, just like VS Code.
        if (w < SIDEBAR_MIN) {
          setSidebarVisible(false);
          draggingSidebar.current = false;
          document.body.style.cursor = '';
        } else {
          const clamped = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, w));
          setSidebarWidth(clamped);
          savedSidebarWidth.current = clamped;
        }
      }
      if (draggingTerminal.current && wrapRef.current) {
        // Terminal on the right: split is the editor's *width* fraction.
        const rect = wrapRef.current.getBoundingClientRect();
        const ratio = Math.min(0.85, Math.max(0.2, (e.clientX - rect.left) / rect.width));
        setSplit(ratio);
      }
    };
    const onUp = () => {
      draggingSplit.current = false;
      draggingSidebar.current = false;
      draggingTerminal.current = false;
      document.body.style.cursor = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  // Auto-collapse sidebar on small viewports (matches the media query in App.css).
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 720px)');
    const onChange = (e) => { if (e.matches) setSidebarVisible(false); };
    mq.addEventListener('change', onChange);
    if (mq.matches) setSidebarVisible(false);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  // Keyboard shortcuts: Ctrl/Cmd+B → sidebar, Ctrl/Cmd+` → terminal.
  useEffect(() => {
    const onKey = (e) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      if (e.key === 'b' || e.key === 'B') { e.preventDefault(); toggleSidebar(); }
      if (e.key === '`') { e.preventDefault(); setTerminalVisible((v) => !v); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  // Close the editor right-click menu on outside click / Escape.
  // We listen on `click` (not `mousedown`) and stop pointer events from
  // bubbling on the menu itself, so a click *inside* the menu doesn't
  // close it before the button's onClick handler runs.
  useEffect(() => {
    if (!editorMenu) return;
    const onClick = (e) => {
      // If the click originated inside the menu, ignore it.
      if (e.target.closest && e.target.closest('.ctx-menu')) return;
      setEditorMenu(null);
    };
    const onKey = (e) => { if (e.key === 'Escape') setEditorMenu(null); };
    window.addEventListener('mousedown', onClick);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onClick);
      window.removeEventListener('keydown', onKey);
    };
  }, [editorMenu]);

  const toggleSidebar = () => {
    if (!sidebarVisible) {
      // restore last width
      setSidebarWidth(savedSidebarWidth.current || 260);
    }
    setSidebarVisible((v) => !v);
  };

  const activeTab = tabs.find((t) => t.path === activePath) || null;

  return (
    <div className="ide">
      <TitleBar
        containerId={containerId}
        sidebarVisible={sidebarVisible}
        terminalVisible={terminalVisible}
        onToggleSidebar={toggleSidebar}
        onToggleTerminal={() => setTerminalVisible((v) => !v)}
      />

      <div className="body" ref={mainRef}>
        <ActivityBar
          sidebarVisible={sidebarVisible}
          settingsOpen={settingsOpen}
          onToggleSidebar={toggleSidebar}
          onToggleSettings={() => setSettingsOpen((v) => !v)}
        />

        {/* ---- Sidebar (resizable, auto-hides on narrow screens) ---- */}
        {sidebarVisible && (
          <>
            <aside className="sidebar" style={{ width: sidebarWidth, minWidth: SIDEBAR_MIN }}>
              <Sidebar
                ref={sidebarRef}
                containerId={containerId}
                onOpenFile={openFile}
                onContainerChange={(id) => {
                  setContainerId(id);
                  setTabs([]);
                  setActivePath(null);
                }}
                onFileDeleted={handleFileDeleted}
              />
            </aside>
            <div
              className="vdivider"
              onMouseDown={() => {
                draggingSidebar.current = true;
                document.body.style.cursor = 'col-resize';
              }}
            />
          </>
        )}

        {/* ---- Main editor + terminal ---- */}
        <main
          className={'main main-pos-' + editorOpts.terminalPosition}
          ref={wrapRef}
        >
          <section
            className="editor-wrap"
            style={
              editorOpts.terminalPosition === 'right' || !terminalVisible
                ? { flex: 1, minWidth: 0, minHeight: 0 }
                : { height: `${split * 100}%` }
            }
          >
            <EditorPane
              containerId={containerId}
              openTabs={tabs}
              activeTab={activeTab}
              onActive={setActivePath}
              onCloseTab={closeTab}
              onTabUpdated={tabUpdated}
              onRun={runActive}
              saveRef={editorSaveRef}
              editorOpts={editorOpts}
              onEditorContextMenu={(pos) => setEditorMenu(pos)}
              onRequestCreate={() => sidebarRef.current?.beginCreateFile?.()}
            />
          </section>

          {terminalVisible && (
            <>
              {editorOpts.terminalPosition === 'bottom' && (
                <div
                  className="hdivider"
                  onMouseDown={() => {
                    draggingSplit.current = true;
                    document.body.style.cursor = 'row-resize';
                  }}
                />
              )}
              {editorOpts.terminalPosition === 'right' && (
                <div
                  className="vdivider"
                  onMouseDown={() => {
                    draggingTerminal.current = true;
                    document.body.style.cursor = 'col-resize';
                  }}
                />
              )}
              <section
                className="terminal-pane"
                style={
                  editorOpts.terminalPosition === 'right'
                    ? { width: `${(1 - split) * 100}%`, height: '100%' }
                    : { height: `${(1 - split) * 100}%` }
                }
              >
                <TerminalPane containerId={containerId} ref={terminalApiRef} />
              </section>
            </>
          )}
        </main>
      </div>

      <StatusBar
        filePath={activeTab?.path}
        language={activeTab?.language}
        cursor={activeTab?.cursor}
        saved={activeTab?.savedAt}
        containerId={containerId}
        terminalVisible={terminalVisible}
        onToggleTerminal={() => setTerminalVisible((v) => !v)}
      />

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        terminalVisible={terminalVisible}
        sidebarVisible={sidebarVisible}
        onToggleTerminal={setTerminalVisible}
        onToggleSidebar={setSidebarVisible}
        editorOpts={editorOpts}
        onEditorOptsChange={setEditorOpts}
        split={split}
        onSplitChange={setSplit}
        sidebarWidth={sidebarWidth}
        onSidebarWidthChange={setSidebarWidth}
      />

      <EditorContextMenu
        pos={editorMenu}
        editorOpts={editorOpts}
        onEditorOptsChange={setEditorOpts}
        onClose={() => setEditorMenu(null)}
      />

      <ConfirmHost />
    </div>
  );
}
