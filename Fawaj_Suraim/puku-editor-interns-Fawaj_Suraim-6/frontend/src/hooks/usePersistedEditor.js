// usePersistedEditor — editor options state backed by localStorage.
//
// Why a hook: every component that needs to read or mutate editor
// options (SettingsModal, EditorContextMenu, App's `<body>` theme
// sync) would otherwise need to thread props or contexts through.
// A hook gives us a single source of truth and persistence for free.
//
// Storage failures are swallowed — Safari private mode and quota
// errors shouldn't crash the app.

import { useEffect, useState } from 'react';
import { DEFAULTS, EDITOR_OPTS_KEY } from '../constants/editor';

function loadInitial() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(EDITOR_OPTS_KEY) || '{}') };
  } catch {
    return DEFAULTS;
  }
}

export function usePersistedEditor() {
  const [editorOpts, setEditorOpts] = useState(loadInitial);

  useEffect(() => {
    try {
      localStorage.setItem(EDITOR_OPTS_KEY, JSON.stringify(editorOpts));
    } catch {
      /* private mode / quota — ignore */
    }
  }, [editorOpts]);

  return [editorOpts, setEditorOpts];
}
