import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { api } from '../api.js';
import { askConfirm } from '../confirm.js';

// In-memory clipboard shared by the whole sidebar (cut/copy/paste).
// `mode` is 'copy' | 'cut' so the source can self-delete on paste.
let clipboard = null; // { mode: 'copy'|'cut', path: string }

// Minimal starter content for newly created files. Returns an empty
// string for unfamiliar extensions so the file is genuinely blank —
// no header comment is prepended (the previous behaviour dropped a
// "// new file\n" line into every new file, which the user found
// noisy). For well-known web-dev extensions we still seed a tiny
// skeleton so the file is immediately usable.
const boilerplateFor = (name) => {
  const ext = (name.split('.').pop() || '').toLowerCase();
  const baseRaw = name.replace(/\.[^.]+$/, '');
  // PascalCase component name derived from the filename (js/jsx/ts/tsx).
  const words = baseRaw.split(/[^a-zA-Z0-9]+/).filter(Boolean);
  const comp = (words.map((w) => w[0].toUpperCase() + w.slice(1)).join('')) || 'App';
  // snake_case identifier for python entry points.
  const pyName = (baseRaw.toLowerCase().replace(/[^a-z0-9_]/g, '_') || 'main');
  switch (ext) {
    case 'js':
    case 'jsx':
      return `export default function ${comp}() {\n  return null;\n}\n`;
    case 'ts':
    case 'tsx':
      return `export default function ${comp}(): JSX.Element | null {\n  return null;\n}\n`;
    case 'html':
      return `<!doctype html>\n<html lang="en">\n  <head>\n    <meta charset="utf-8">\n    <title>${baseRaw}</title>\n  </head>\n  <body>\n  </body>\n</html>\n`;
    case 'json':
      return `{\n  \n}\n`;
    case 'py':
      return `def ${pyName}():\n    pass\n\n\nif __name__ == "__main__":\n    ${pyName}()\n`;
    case 'md':
      return `# ${baseRaw}\n`;
    default:
      return '';
  }
};

function TreeNode({
  entry, level = 0, onOpen, onContextMenu, containerId,
  refresh, setStatus, draggingPath, setDraggingPath,
  renaming, setRenaming, submitRename, treeVersion,
  currentDir, onSelectDir, forceOpen = false,
}) {
  // A newly-created directory should auto-expand so the user can see
  // (and immediately act on) its empty contents. `forceOpen` flips the
  // default once when this node first mounts.
  const [open, setOpen] = useState(level < 1 || forceOpen);
  const [children, setChildren] = useState(null);
  const isDir = entry.type === 'dir';
  const name = entry.path.split('/').pop() || '/';

  const loadChildren = async () => {
    try {
      const res = await api.tree(containerId, entry.path);
      setChildren(res.entries.filter((e) => e.path));
    } catch (e) {
      setStatus(e.message);
    }
  };

  const toggle = async (e) => {
    // Clicks on a nested row bubble up to every ancestor's <div>, each
    // of which has its own onClick={toggle}. Without stopping the
    // propagation, clicking a single row would also collapse every
    // ancestor — making it look like the clicked directory "didn't
    // expand" while in reality the whole tree collapsed above it.
    e.stopPropagation();
    if (!isDir) return onOpen(entry.path);
    // Any click on a directory row makes it the target for the top `+`
    // popover's "new file / new folder" actions, so the user can build
    // a hierarchy without per-row buttons. We also auto-expand and lazy-
    // load children on first open.
    if (onSelectDir) onSelectDir(entry.path);
    const next = !open;
    setOpen(next);
    if (next && !children) await loadChildren();
  };

  // When the parent detects external file changes (e.g. terminal `touch`),
  // refetch this directory's children if it's open so newly added files
  // show up without collapsing/expanding the node.
  useEffect(() => {
    if (!isDir || !open || !treeVersion) return;
    loadChildren();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [treeVersion]);

  // Drag-and-drop to move files.
  const onDragStart = (e) => {
    e.stopPropagation();
    e.dataTransfer.setData('text/plain', entry.path);
    e.dataTransfer.effectAllowed = 'move';
    setDraggingPath(entry.path);
  };
  const onDragOver = (e) => {
    if (!isDir) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
  };
  const onDrop = async (e) => {
    if (!isDir) return;
    e.preventDefault();
    e.stopPropagation();
    const src = e.dataTransfer.getData('text/plain');
    setDraggingPath(null);
    if (!src || src === entry.path) return;
    const dest = entry.path + '/' + src.split('/').pop();
    try {
      // Move via shell `mv` since we don't have a dedicated rename endpoint.
      await api.exec(containerId, `mv '${src}' '${dest}'`);
      await refresh();
    } catch (err) { setStatus(err.message); }
  };

  // Small text glyphs (no emoji) — Replit-mini-style minimalism.
  const toggleGlyph = isDir ? (open ? '▾' : '▸') : '';
  const iconGlyph = isDir ? '▢' : '·';

  return (
    <div
      className={
        'tree-row'
        + (draggingPath === entry.path ? ' dragging' : '')
        + (isDir && currentDir === entry.path ? ' active' : '')
      }
      data-kind={isDir ? 'dir' : 'file'}
      style={{ paddingLeft: 4 + level * 14 }}
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onClick={toggle}
    >
      {/* The label row (toggle · icon · name) is its own flex line so the
         `tree-children` block can break to a new line *under* it. Previously
         the row was a single flex container with `flex-direction: row`, so
         the children div (even with flex-basis:100%) still tried to fit on
         the same line as the name — pushing the name to 0 width and making
         the directory's own name disappear the moment the user expanded it. */}
      <div className="tree-label" onClick={toggle}>
        <span className="tree-toggle">{toggleGlyph}</span>
        <span className="tree-icon">{iconGlyph}</span>
        {renaming?.path === entry.path ? (
          <span className="rename-row" onClick={(e) => e.stopPropagation()}>
            <input
              className="tree-name rename-input"
              autoFocus
              value={renaming.value}
              onChange={(e) => setRenaming({ ...renaming, value: e.target.value })}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitRename();
                if (e.key === 'Escape') setRenaming(null);
              }}
              onClick={(e) => e.stopPropagation()}
              // No onBlur — the tick button is the confirm path now.
            />
            <button
              className="rename-tick"
              onMouseDown={(e) => e.preventDefault() /* keep input focused until click */}
              onClick={(e) => { e.stopPropagation(); submitRename(); }}
              title="Confirm (Enter)"
              aria-label="Confirm rename"
            >✓</button>
            <button
              className="rename-x"
              onClick={(e) => { e.stopPropagation(); setRenaming(null); }}
              title="Cancel (Esc)"
              aria-label="Cancel rename"
            >×</button>
          </span>
        ) : (
          <span
            className="tree-name"
            onContextMenu={(e) => onContextMenu(e, entry.path, isDir)}
            title={entry.path}
          >
            {name}
          </span>
        )}
      </div>

      {open && isDir && (
        <div className="tree-children">
          {children?.map((c) => (
            <TreeNode
              key={c.path}
              entry={c}
              level={level + 1}
              onOpen={onOpen}
              onContextMenu={onContextMenu}
              containerId={containerId}
              refresh={refresh}
              setStatus={setStatus}
              draggingPath={draggingPath}
              setDraggingPath={setDraggingPath}
              renaming={renaming}
              setRenaming={setRenaming}
              submitRename={submitRename}
              treeVersion={treeVersion}
              currentDir={currentDir}
              onSelectDir={onSelectDir}
              forceOpen={c.path === forceOpen}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default forwardRef(function Sidebar(
  { containerId, onOpenFile, onContainerChange, onFileDeleted },
  ref,
) {
  const cid = containerId;
  const [entries, setEntries] = useState([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [creating, setCreating] = useState(false);     // inline input visible
  const [creatingKind, setCreatingKind] = useState('file'); // 'file' | 'dir'
  const [newName, setNewName] = useState('');   // input value (empty by default)
  // The directory the inline "new file / new dir" input will create *into*.
  // Defaults to /workspace, and gets updated when the user clicks any
  // directory row. The top `+` popover routes new file/folder actions
  // here, so the user just picks a directory and then hits the global
  // `+` to create inside it — no per-row buttons needed.
  const [createInPath, setCreateInPath] = useState('/workspace');
  // Tracks which directory row is currently selected (highlighted).
  // Mirrors `createInPath` for the sidebar UI. Kept as separate state
  // so the row highlight can be cleared independently of where the
  // next create will land (e.g. after a create completes).
  const [currentDir, setCurrentDir] = useState('/workspace');
  // When set, the matching TreeNode should auto-expand on next render.
  // Set after a successful dir creation so the user immediately sees
  // (and can add to) the new empty directory. Cleared on next refresh.
  const [justCreatedPath, setJustCreatedPath] = useState(null);
  const [menu, setMenu] = useState(null);               // {x, y, path, isDir}
  const [renaming, setRenaming] = useState(null);       // {path, value}
  const [draggingPath, setDraggingPath] = useState(null);
  const [newPopoverOpen, setNewPopoverOpen] = useState(false);
  const newPopoverRef = useRef(null);
  const inputRef = useRef(null);
  const sigRef = useRef(''); // last tree fingerprint, used by auto-refresh
  const [treeVersion, setTreeVersion] = useState(0); // bumps on external change

  // Helper to open the inline input scoped to a given parent directory.
  // Used by the header popover's "New file" / "New folder" items and the
  // editor's `+` tab button. The parent defaults to the currently
  // selected directory, falling back to /workspace.
  const beginCreate = (kind, parent) => {
    setCreatingKind(kind);
    setCreateInPath(parent || currentDir || '/workspace');
    // Start with an empty input — the previous default ("hello.js" /
    // "newdir" / "newfile.js") was acting as a suggested name that the
    // user had to clear before typing. The placeholder still hints at
    // the kind of entity being created.
    setNewName('');
    setCreating(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  // Expose a small imperative API so the editor header's "+" button can
  // open this sidebar's new-file input and focus it. Defaults to /workspace
  // but accepts an optional parent path so callers can target a directory.
  useImperativeHandle(ref, () => ({
    beginCreateFile: (parent) => beginCreate('file', parent),
    beginCreateDir: (parent) => beginCreate('dir', parent),
  }));

  // Selecting a directory row from the tree — the click handler in
  // TreeNode.toggle calls this so the row highlights and the top `+`
  // popover's "new file / new folder" actions target that directory.
  const selectDir = (path) => {
    setCurrentDir(path);
    setCreateInPath(path);
  };

  const refresh = async () => {
    if (!cid) return;
    try {
      const res = await api.tree(cid, '/workspace');
      const next = res.entries.filter((e) => e.path && e.path !== '.');
      setEntries(next);
      // Bump the version so any open subdirectory TreeNode refetches
      // its children — otherwise a new file inside `/workspace/src`
      // would only land in `entries` (top level) and would not appear
      // in `src`'s rendered children until the 4s auto-refresh tick
      // fires. The bump lets the per-node useEffect on `[treeVersion]`
      // pick the change up and call `loadChildren()` immediately.
      setTreeVersion((v) => v + 1);
    } catch (e) {
      setStatus(e.message);
    }
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [cid]);

  // Remember the last set of file paths we saw on disk so we can detect
  // deletions that happened outside the explorer (e.g. `rm` in the
  // terminal). The auto-refresh effect below updates this; the diff
  // gets reported to the parent via `onFileDeleted` so open tabs can
  // close. We only start tracking once we've seen at least one tree,
  // so the very first tick doesn't trigger spurious "deletions" for
  // every file.
  const knownFilesRef = useRef(null); // Set<string> | null

  // Auto-refresh the tree every 4s so files added via the terminal
  // (or any other out-of-band write) show up without a manual reload.
  // We compare a JSON fingerprint to avoid useless re-renders.
  useEffect(() => {
    if (!cid) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await api.tree(cid, '/workspace');
        const next = res.entries.filter((e) => e.path && e.path !== '.');
        const sig = JSON.stringify(next.map((e) => [e.path, e.type, e.size, e.mtimeMs]));
        if (sig !== sigRef.current) {
          sigRef.current = sig;
          if (!cancelled) {
            // Detect out-of-band deletions: any path (file *or* dir)
            // present in the last snapshot that is missing from the
            // new one. We track directories here too so that
            // `rm -rf /workspace/src` in the terminal still fires
            // `onFileDeleted('/workspace/src')` and the editor can
            // close every descendant tab. Skip the first observation
            // (knownFilesRef is null) so the initial mount doesn't
            // fire phantom deletions.
            if (knownFilesRef.current && onFileDeleted) {
              const nextPaths = new Set(next.map((e) => e.path));
              for (const prev of knownFilesRef.current) {
                if (!nextPaths.has(prev)) onFileDeleted(prev);
              }
              knownFilesRef.current = nextPaths;
            } else {
              knownFilesRef.current = new Set(next.map((e) => e.path));
            }
            setEntries(next);
            setTreeVersion((v) => v + 1); // tell open nodes to refetch
          }
        }
      } catch { /* ignore transient errors */ }
    };
    const id = setInterval(tick, 4000);
    return () => { cancelled = true; clearInterval(id); };
  }, [cid, onFileDeleted]);

  // When the container id changes, drop the cached file set so the
  // first tick on the new sandbox isn't treated as a mass deletion.
  useEffect(() => {
    knownFilesRef.current = null;
  }, [cid]);

  // Close context menu on outside click / Esc.
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    const onKey = (e) => { if (e.key === 'Escape') setMenu(null); };
    window.addEventListener('click', close);
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('click', close); window.removeEventListener('keydown', onKey); };
  }, [menu]);

  // Close the "new file / new folder" popover on outside click / Esc.
  useEffect(() => {
    if (!newPopoverOpen) return;
    const close = (e) => {
      if (newPopoverRef.current && !newPopoverRef.current.contains(e.target)) {
        setNewPopoverOpen(false);
      }
    };
    const onKey = (e) => { if (e.key === 'Escape') setNewPopoverOpen(false); };
    window.addEventListener('mousedown', close);
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('mousedown', close); window.removeEventListener('keydown', onKey); };
  }, [newPopoverOpen]);

  // Click anywhere outside the file explorer panel clears the
  // highlighted directory selection. We scope the "inside" check to
  // the whole `.sidebar-files` section (not just `.tree`) so the
  // explorer's own controls — the `+` button, the refresh button,
  // the popover, the inline new-file/folder input — all keep the
  // user's selection alive. Tree rows themselves stop propagation
  // on click, so even if we used `.tree` here, those would also
  // be safe; the broader scope just covers the title-bar controls.
  useEffect(() => {
    const onDown = (e) => {
      const explorerEl = e.target?.closest?.('.sidebar-files');
      if (explorerEl) return;
      if (currentDir !== '/workspace') setCurrentDir('/workspace');
    };
    window.addEventListener('mousedown', onDown);
    return () => window.removeEventListener('mousedown', onDown);
  }, [currentDir]);

  const createContainer = async () => {
    setBusy(true);
    try {
      const c = await api.createContainer();
      onContainerChange(c.id);
      setStatus(`created ${c.id.slice(0, 12)}`);
    } catch (e) {
      setStatus(e.message);
    } finally {
      setBusy(false);
    }
  };

  const destroyContainer = async () => {
    if (!cid) return;
    const ok = await askConfirm({
      title: 'Stop sandbox?',
      message: 'This will stop and remove the current sandbox. Any unsaved work in the editor will be lost.',
      confirmLabel: 'Stop',
      cancelLabel: 'Keep running',
      danger: true,
    });
    if (!ok) return;
    await api.destroyContainer(cid);
    onContainerChange(null);
  };

  const submitNewFile = async () => {
    const name = newName.trim();
    if (!name) { setCreating(false); return; }
    // Resolve to an absolute path inside `createInPath` so the user can
    // target a subdirectory (instead of always landing at /workspace).
    const parent = createInPath || '/workspace';
    const absPath = parent === '/' ? `/${name}` : `${parent}/${name}`;
    try {
      if (creatingKind === 'dir') {
        await api.exec(cid, `mkdir -p '${absPath.replace(/'/g, "'\\''")}'`);
        setCreating(false);
        setNewName('');
        setCreatingKind('file');
        // Keep `createInPath` aligned with the user's last-selected
        // directory so the next popover open targets the same place.
        // Resetting to '/workspace' here would force every subsequent
        // create back to the root regardless of what the user picked.
        // Mark this path so the just-rendered TreeNode auto-expands,
        // revealing the empty directory the user can now populate.
        setJustCreatedPath(absPath);
        await refresh();
        // Clear the marker after a tick so a future re-render of the
        // same node (e.g. on tree refresh) doesn't keep it open.
        setTimeout(() => setJustCreatedPath(null), 1500);
      } else {
        await api.writeFile(cid, absPath, boilerplateFor(name));
        setCreating(false);
        setNewName('');
        setCreatingKind('file');
        // Same as above — preserve the user's directory selection.
        setJustCreatedPath(null);
        await refresh();
        // Don't auto-open: creating a file just materializes it in the
        // explorer. The user opens it explicitly by clicking the row.
      }
    } catch (e) { setStatus(e.message); }
  };

  const onContextMenu = (e, path, isDir) => {
    e.preventDefault();
    e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY, path, isDir });
  };

  const doCopy = () => { clipboard = { mode: 'copy', path: menu.path }; setMenu(null); };
  const doCut  = () => { clipboard = { mode: 'cut',  path: menu.path }; setMenu(null); };

  const doPaste = async (destDir) => {
    if (!clipboard) { setMenu(null); return; }
    const src = clipboard.path;
    const base = src.split('/').pop();
    const dest = (destDir || '/workspace') + '/' + base;
    if (dest === src) { setMenu(null); return; }
    try {
      if (clipboard.mode === 'cut') {
        await api.exec(cid, `mv '${src}' '${dest}'`);
        clipboard = null;
      } else {
        await api.exec(cid, `cp -r '${src}' '${dest}'`);
      }
      await refresh();
    } catch (e) { setStatus(e.message); }
    setMenu(null);
  };

  const doRename = () => {
    const base = menu.path.split('/').pop();
    setRenaming({ path: menu.path, value: base });
    setMenu(null);
  };

  const submitRename = async () => {
    if (!renaming) return;
    const next = renaming.value.trim();
    const dir = renaming.path.includes('/')
      ? renaming.path.slice(0, renaming.path.lastIndexOf('/'))
      : '/workspace';
    const dest = (dir === '' ? '/workspace' : dir) + '/' + next;
    if (!next || dest === renaming.path) { setRenaming(null); return; }
    try {
      await api.exec(cid, `mv '${renaming.path}' '${dest}'`);
      await refresh();
    } catch (e) { setStatus(e.message); }
    setRenaming(null);
  };

  const doDelete = async () => {
    const deletedPath = menu.path;
    const name = deletedPath.split('/').pop() || deletedPath;
    const isDir = menu.isDir;
    const ok = await askConfirm({
      title: isDir ? `Delete folder "${name}"?` : `Delete "${name}"?`,
      message: isDir
        ? `The folder ${deletedPath} and everything inside it will be permanently removed. This cannot be undone.`
        : `The file ${deletedPath} will be permanently removed. This cannot be undone.`,
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      danger: true,
    });
    if (!ok) { setMenu(null); return; }
    try { await api.deleteFile(cid, deletedPath); await refresh(); }
    catch (e) { setStatus(e.message); }
    setMenu(null);
    if (onFileDeleted) onFileDeleted(deletedPath);
  };

  return (
    <aside
      className="sidebar"
      onContextMenu={(e) => onContextMenu(e, '/workspace', true)}
    >
      <div className="sidebar-section">
        <div className="sidebar-title">Sandbox</div>
        {cid ? (
          <div className="row">
            <code className="cid" title={cid}>{cid.slice(0, 12)}…</code>
            <button onClick={destroyContainer}>Stop</button>
          </div>
        ) : (
          <button disabled={busy} onClick={createContainer}>
            {busy ? 'Spinning up…' : '+ New sandbox'}
          </button>
        )}
        {status && <div className="status">{status}</div>}
      </div>

      <div className="sidebar-section sidebar-files">
        <div className="sidebar-title">
          <span>Files</span>
          <span className="row-actions">
            <button
              className="icon-btn"
              disabled={!cid}
              onClick={refresh}
              title="Refresh (Ctrl+R)"
              aria-label="Refresh"
            >↻</button>
            <span className="new-popover-anchor" ref={newPopoverRef}>
              <button
                className="icon-btn"
                disabled={!cid}
                onClick={() => setNewPopoverOpen((v) => !v)}
                title={`New file or folder in ${currentDir}`}
                aria-label="New"
              >+</button>
              {newPopoverOpen && (
                <div className="tree-new-popover" role="menu" style={{ top: 'calc(100% + 4px)', right: 0 }}>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => { setNewPopoverOpen(false); beginCreate('file'); }}
                  ><span className="pop-icon" aria-hidden="true"><svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"><path d="M2 6 L10 6 M6 2 L6 10" /></svg></span><span className="pop-label">New file</span></button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => { setNewPopoverOpen(false); beginCreate('dir'); }}
                  ><span className="pop-icon" aria-hidden="true"><svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"><path d="M1.5 3.25 A0.75 0.75 0 0 1 2.25 2.5 L4.5 2.5 L5.5 3.75 L9.75 3.75 A0.75 0.75 0 0 1 10.5 4.5 L10.5 8.75 A0.75 0.75 0 0 1 9.75 9.5 L2.25 9.5 A0.75 0.75 0 0 1 1.5 8.75 Z" /></svg></span><span className="pop-label">New folder</span></button>
                </div>
              )}
            </span>
          </span>
        </div>

        {creating && (
          <div className="new-file-row">
            <span className="new-file-icon">{creatingKind === 'dir' ? '▢' : '·'}</span>
            <input
              ref={inputRef}
              className="new-file-input"
              value={newName}
              placeholder={
                createInPath === '/workspace'
                  ? 'name (in /workspace)'
                  : `name (in ${createInPath})`
              }
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitNewFile();
                if (e.key === 'Escape') {
                  setCreating(false);
                  setNewName('');
                  setCreatingKind('file');
                  setCreateInPath('/workspace');
                }
              }}
              // Don't auto-submit on blur — the user may want to click the
              // tick to confirm. Use the tick button to submit.
            />
            <button
              className="new-file-tick"
              onMouseDown={(e) => e.preventDefault() /* keep input focused until click */}
              onClick={submitNewFile}
              title="Create (Enter)"
              aria-label="Create"
            >✓</button>
            <button
              className="new-file-x"
              onClick={() => {
                setCreating(false);
                setNewName('');
                setCreatingKind('file');
                setCreateInPath('/workspace');
              }}
              title="Cancel (Esc)"
              aria-label="Cancel"
            >×</button>
          </div>
        )}

        <div className="tree" onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY, path: '/workspace', isDir: true }); }}>
          {/* Synthetic root node — a non-collapsible "workspace" label at
              the top of the explorer. Clicking it selects /workspace so
              the user has a clear anchor for the top `+` popover (and
              can always reset the selection back to the root). */}
          {cid && (
            <div
              className={'tree-row tree-root' + (currentDir === '/workspace' ? ' active' : '')}
              data-kind="dir"
              onClick={(e) => { e.stopPropagation(); selectDir('/workspace'); }}
            >
              <div className="tree-label" onClick={(e) => { e.stopPropagation(); selectDir('/workspace'); }}>
                <span className="tree-toggle"></span>
                <span className="tree-icon" aria-hidden="true">
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" aria-hidden="true">
                    <path d="M1.5 3.25 A0.75 0.75 0 0 1 2.25 2.5 L4.5 2.5 L5.5 3.75 L9.75 3.75 A0.75 0.75 0 0 1 10.5 4.5 L10.5 8.75 A0.75 0.75 0 0 1 9.75 9.5 L2.25 9.5 A0.75 0.75 0 0 1 1.5 8.75 Z" />
                  </svg>
                </span>
                <span className="tree-name" title="/workspace">workspace</span>
              </div>
            </div>
          )}
          {entries.map((e) => (
            <TreeNode
              key={e.path}
              entry={e}
              level={0}
              onOpen={onOpenFile}
              onContextMenu={onContextMenu}
              containerId={cid}
              refresh={refresh}
              setStatus={setStatus}
              draggingPath={draggingPath}
              setDraggingPath={setDraggingPath}
              renaming={renaming}
              setRenaming={setRenaming}
              submitRename={submitRename}
              treeVersion={treeVersion}
              currentDir={currentDir}
              onSelectDir={selectDir}
              forceOpen={justCreatedPath}
            />
          ))}
          {!entries.length && cid && <div className="muted tree-empty">/workspace is empty</div>}
        </div>
      </div>

      {menu && (
        <div
          className="ctx-menu"
          style={{ top: menu.y, left: menu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          {!menu.isDir && <div className="ctx-item" onClick={doCopy}>Copy</div>}
          <div className="ctx-item" onClick={doCut}>Cut</div>
          {menu.isDir && <div className="ctx-item" onClick={() => doPaste(menu.path)}>Paste into {menu.path.split('/').pop() || 'workspace'}</div>}
          {menu.path !== '/workspace' && <div className="ctx-item" onClick={doRename}>Rename</div>}
          {menu.path !== '/workspace' && <div className="ctx-item ctx-danger" onClick={doDelete}>Delete</div>}
        </div>
      )}
    </aside>
  );
})
