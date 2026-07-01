import Editor, { loader } from '@monaco-editor/react';
import { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';

// Load Monaco from a pinned CDN; the loader resolves language workers on demand.
loader.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/vs' } });

const LANGS = {
  js: 'javascript', mjs: 'javascript', cjs: 'javascript',
  ts: 'typescript', tsx: 'typescript', jsx: 'javascript',
  json: 'json', html: 'html', htm: 'html', css: 'css', scss: 'scss', less: 'less',
  md: 'markdown', mdx: 'markdown',
  py: 'python', rb: 'ruby', go: 'go', rs: 'rust',
  java: 'java', kt: 'kotlin', swift: 'swift', c: 'c', h: 'c',
  cpp: 'cpp', hpp: 'cpp', cs: 'csharp',
  php: 'php', sql: 'sql',
  sh: 'shell', bash: 'shell', zsh: 'shell',
  yml: 'yaml', yaml: 'yaml', toml: 'ini', ini: 'ini', env: 'ini',
  xml: 'xml', svg: 'xml',
  txt: 'plaintext', '': 'plaintext',
};

export function detectLang(p) {
  const ext = p.split('.').pop()?.toLowerCase() || '';
  return LANGS[ext] || 'plaintext';
}

export default function EditorPane({
  containerId, openTabs, activeTab,
  onActive, onCloseTab, onTabUpdated, onRun,
  saveRef, editorOpts, onEditorContextMenu,
  onRequestCreate,
}) {
  const editorRef = useRef(null);
  const monacoRef = useRef(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => { setDirty(false); }, [activeTab?.path, containerId]);

  // Derive the active tab + language (hooks must be unconditional).
  const tab = activeTab || openTabs[0] || null;
  const language = tab ? detectLang(tab.path) : 'plaintext';

  // Apply user-tweakable options to the live editor (and keep them in sync
  // with the right-click menu in App.jsx). Default to safe values so the
  // prop is optional during dev.
  const opts = editorOpts || {
    minimap: true, wordWrap: 'on', fontSize: 14, tabSize: 2,
    fontFamily: 'Menlo, Consolas, monospace',
    renderWhitespace: 'selection', lineNumbers: 'on',
    cursorStyle: 'smooth', formatOnSave: false,
  };
  useEffect(() => {
    const ed = editorRef.current;
    if (!ed) return;
    ed.updateOptions({
      minimap: { enabled: !!opts.minimap },
      wordWrap: opts.wordWrap || 'off',
      fontSize: opts.fontSize || 14,
      // NB: tabSize is a *model* option in Monaco — view options silently
      // ignore it. We still pass it through (harmless) and also set it
      // on the model below so changes actually take effect.
      tabSize: opts.tabSize || 2,
      fontFamily: opts.fontFamily,
      renderWhitespace: opts.renderWhitespace,
      lineNumbers: opts.lineNumbers,
      cursorStyle: opts.cursorStyle,
    });
    const model = ed.getModel && ed.getModel();
    if (model) {
      model.updateOptions({
        tabSize: opts.tabSize || 2,
        indentSize: opts.tabSize || 2,
      });
    }
  }, [opts.minimap, opts.wordWrap, opts.fontSize, opts.tabSize,
      opts.fontFamily, opts.renderWhitespace, opts.lineNumbers, opts.cursorStyle]);

  // save() closes over the *current* tab — keep the impl stable so the
  // keybinding registered in onMount keeps working across re-renders.
  const save = async () => {
    if (!editorRef.current || !tab) return false;
    if (opts.formatOnSave) {
      try { await editorRef.current.getAction('editor.action.formatDocument')?.run(); } catch {}
    }
    const content = editorRef.current.getValue();
    try {
      await api.writeFile(containerId, tab.path, content);
      setDirty(false);
      onTabUpdated?.(tab.path, { content, savedAt: Date.now() });
      return true;
    } catch (e) {
      alert('Save failed: ' + e.message);
      return false;
    }
  };

  // Expose a parent-callable save so App.runActive() can flush dirty
  // buffers to disk before exec() — otherwise the sandbox runs stale text.
  useEffect(() => {
    if (saveRef) saveRef.current = save;
    return () => { if (saveRef) saveRef.current = null; };
  });

  // Tab-bar scroll behaviour: the strip has a hidden scrollbar by
  // default (see .tabs-scroll in App.css) so it doesn't compete with
  // the editor for visual attention. While the user is actively
  // scrolling (trackpad swipe, shift-wheel, click+drag), we toggle a
  // class that fades the scrollbar in; after ~600ms of stillness it
  // fades back out. The same effect also fires on hover / keyboard
  // focus via pure CSS, so the JS only needs to handle the "still
  // scrolling but not over the strip" case.
  // NOTE: this hook *must* live above the early returns below —
  // React's Rules of Hooks require the same number of hooks on every
  // render, and if a hook is only called on the "real editor" path the
  // next render that hits an early return would crash with
  // "Rendered more hooks than during the previous render".
  const tabsScrollRef = useRef(null);
  useEffect(() => {
    const el = tabsScrollRef.current;
    if (!el) return;
    let hideTimer = null;
    const onScroll = () => {
      el.classList.add('is-scrolling');
      if (hideTimer) clearTimeout(hideTimer);
      hideTimer = setTimeout(() => el.classList.remove('is-scrolling'), 600);
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      el.removeEventListener('scroll', onScroll);
      if (hideTimer) clearTimeout(hideTimer);
    };
  }, []);

  if (!containerId) {
    return <div className="editor empty">Spin up a sandbox to start editing.</div>;
  }
  if (!openTabs.length) {
    return (
      <div className="editor empty">
        <div>
          <div>No files open yet.</div>
          <div className="muted">Click <b>+ New file</b> in the sidebar, or pick a file from the tree.</div>
        </div>
      </div>
    );
  }

  const handleMount = (ed, monaco) => {
    editorRef.current = ed;
    monacoRef.current = monaco;

    // Suppress Monaco's built-in right-click menu so we can show our
    // own custom one (App.jsx renders the popup). Without this both
    // menus appear stacked.
    ed.updateOptions({ contextmenu: false });

    // Apply user-tweakable options once at mount (subsequent changes are
    // handled by the useEffect above).
    ed.updateOptions({
      minimap: { enabled: !!opts.minimap },
      wordWrap: opts.wordWrap || 'off',
      fontSize: opts.fontSize || 14,
      tabSize: opts.tabSize || 2,
      fontFamily: opts.fontFamily,
      renderWhitespace: opts.renderWhitespace,
      lineNumbers: opts.lineNumbers,
      cursorStyle: opts.cursorStyle,
    });
    // tabSize is a model option in Monaco, so set it on the model too.
    const m = ed.getModel && ed.getModel();
    if (m) m.updateOptions({ tabSize: opts.tabSize || 2, indentSize: opts.tabSize || 2 });

    // Report cursor + language up to the status bar.
    const report = () => {
      if (!onTabUpdated) return;
      onTabUpdated(tab.path, {
        language,
        cursor: { line: ed.getPosition().lineNumber, column: ed.getPosition().column },
      });
    };
    ed.onDidChangeCursorPosition(report);
    ed.onDidChangeModelContent(() => setDirty(true));
    report();

    // Forward the browser's contextmenu event (fired by right-click anywhere
    // over the editor surface) so App.jsx can render a config popup.
    const dom = ed.getDomNode();
    if (dom && onEditorContextMenu) {
      dom.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        onEditorContextMenu({ x: e.clientX, y: e.clientY });
      });
    }

    // Cmd/Ctrl + S to save.
    ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, save);
    // Cmd/Ctrl + Enter to run.
    ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => onRun && onRun());
  };

  return (
    <div className="editor">
      <div className="tabs">
        <div className="tabs-scroll" ref={tabsScrollRef}>
          {openTabs.map((t) => (
            <div
              key={t.path}
              className={
                'tab'
                + (t.path === tab.path ? ' active' : '')
              }
              onClick={() => onActive(t.path)}
              title={t.path}
            >
              <span className="tab-icon">📄</span>
              <span className="tab-name">{t.path.split('/').pop()}</span>
              <button
                className="tab-x"
                onClick={(e) => { e.stopPropagation(); onCloseTab(t.path); }}
                title="Close"
              >×</button>
            </div>
          ))}
          {onRequestCreate && (
            <button
              className="tab-new"
              onClick={onRequestCreate}
              title="New file"
            >+</button>
          )}
        </div>
        {onRun && (
          <button className="tab-run" onClick={onRun} title="Run active file (Ctrl+Enter)">
            ▶ Run
          </button>
        )}
        <button className="save-btn" onClick={save} disabled={!dirty}>
          {dirty ? '● Save  ⌘S' : '✓ Saved'}
        </button>
      </div>

      <Editor
        key={tab.path}
        height="100%"
        theme={opts.theme || 'vs-dark'}
        path={tab.path}
        defaultLanguage={language}
        defaultValue={tab.content ?? ''}
        onMount={handleMount}
        options={{
          fontSize: opts.fontSize,
          fontLigatures: true,
          minimap: { enabled: !!opts.minimap, scale: 1 },
          automaticLayout: true,
          tabSize: opts.tabSize,
          wordWrap: opts.wordWrap || 'off',
          // ---- Intellisense / suggestions ----
          quickSuggestions: { other: true, comments: false, strings: true },
          suggestOnTriggerCharacters: true,
          acceptSuggestionOnEnter: 'on',
          snippetSuggestions: 'inline',
          wordBasedSuggestions: 'allDocuments',
          parameterHints: { enabled: true },
          formatOnPaste: true,
          formatOnType: false,
          renderLineHighlight: 'all',
          cursorBlinking: 'smooth',
          smoothScrolling: true,
          scrollBeyondLastLine: false,
        }}
      />
    </div>
  );
}
