import { useEffect, useState } from 'react';
import { Activity, Check, KeyRound, RefreshCw, Server, X } from 'lucide-react';
import { getApiKey, setApiKey } from '../api';

/**
 * Top bar. Shows:
 *   - product name + small status indicator (polls /healthz every 10s, or
 *     immediately when the parent bumps `healthzBump`)
 *   - manual refresh button (re-hydrates the sidebar from the backend)
 *   - auth-locked indicator when /jobs polling hits 401
 *   - API key input with explicit Save button. Save only appears when the
 *     input has content that differs from the currently-stored value, so
 *     typing into the field no longer writes through to localStorage on
 *     every keystroke.
 */
export default function Header({ onRefresh, refreshing, authLocked, healthzBump = 0, onApiKeySaved }) {
  // `savedKey` is the persisted value (what the backend will actually use);
  // `pendingKey` is what's currently in the input box.
  const [savedKey, setSavedKey] = useState(getApiKey());
  const [pendingKey, setPendingKey] = useState(getApiKey());
  const [savedFlash, setSavedFlash] = useState(false);
  const [health, setHealth] = useState('unknown');

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await fetch('/healthz');
        if (!cancelled) setHealth(r.ok ? 'ok' : 'down');
      } catch {
        if (!cancelled) setHealth('down');
      }
    };
    tick();
    const id = setInterval(tick, 10_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [healthzBump]);

  const onKeyChange = (e) => {
    setPendingKey(e.target.value);
    setSavedFlash(false);
  };

  const onSaveKey = () => {
    const trimmed = pendingKey.trim();
    setSavedKey(trimmed);
    setApiKey(trimmed);
    setSavedFlash(true);
    // Notify the parent so it can clear any auth-lock state and re-fetch
    // the sidebar — otherwise fixing a wrong key still looks broken until
    // the user reloads the page.
    onApiKeySaved?.();
  };

  const onClearKey = () => {
    setPendingKey('');
    setSavedKey('');
    setApiKey('');
    setSavedFlash(false);
  };

  // Save button only shows when the user has typed something new that
  // hasn't been persisted yet.
  const dirty = pendingKey.trim() !== savedKey;

  const healthColor = health === 'ok'
    ? 'bg-emerald-400'
    : health === 'down'
      ? 'bg-rose-400'
      : 'bg-slate-500';

  return (
    <header className="flex items-center gap-3 border-b border-slate-700 bg-slate-900/95 px-3 py-3 shadow-lg shadow-black/40 backdrop-blur narrow:gap-4 narrow:px-6">
      <div className="flex min-w-0 items-center gap-2 text-slate-100">
        <Server className="h-5 w-5 shrink-0 text-emerald-400" />
        <span className="truncate text-base font-semibold tracking-tight">
          <span className="xs:hidden">Orchestrator</span>
          <span className="hidden xs:inline">Job Orchestrator</span>
        </span>
      </div>

      <div className="ml-auto flex min-w-0 items-center gap-2 narrow:gap-3">
        {/*
          /healthz indicator. Three sizes:
            xs (<480px):   icon + colored dot only
            xs-narrow:     icon + dot + uppercase word ("OK")
            narrow+:       icon + "/healthz" + dot + uppercase word
        */}
        <div
          className="flex shrink-0 items-center gap-1.5 rounded-md bg-slate-800/70 px-1.5 py-1 text-xs text-slate-300 ring-1 ring-slate-700 xs:gap-2 xs:px-2 narrow:gap-2"
          title={`/healthz: ${health}`}
        >
          <Activity className="h-3.5 w-3.5" />
          <span className={`h-2 w-2 shrink-0 rounded-full ${healthColor}`} />
          <span className="hidden font-mono text-slate-400 xs:inline narrow:inline">/healthz</span>
          <span className="hidden uppercase tracking-wide text-[10px] text-slate-400 xs:inline">{health}</span>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={!onRefresh || refreshing}
          title={authLocked ? 'Refresh sidebar (API key rejected)' : 'Refresh sidebar'}
          aria-label="Refresh jobs"
          className={`flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs ring-1 transition disabled:cursor-not-allowed disabled:opacity-50 ${
            authLocked
              ? 'bg-amber-500/10 text-amber-300 ring-amber-500/40 hover:bg-amber-500/20'
              : 'bg-slate-800/70 text-slate-300 ring-slate-700 hover:bg-slate-700/70 hover:text-slate-100'
          }`}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          <span className="hidden xs:inline">{refreshing ? 'Refreshing…' : 'Refresh'}</span>
        </button>

        <div className="flex min-w-0 items-center gap-1 rounded-md bg-slate-800/70 px-2 py-1 ring-1 ring-slate-700 focus-within:ring-emerald-500/50">
          <KeyRound className="h-3.5 w-3.5 shrink-0 text-slate-400" />
          <input
            id="api-key"
            name="apiKey"
            type="password"
            value={pendingKey}
            onChange={onKeyChange}
            onKeyDown={(e) => {
              // Enter commits the pending key — feels natural when the
              // user pastes a key and hits return.
              if (e.key === 'Enter' && dirty) {
                e.preventDefault();
                onSaveKey();
              }
            }}
            placeholder="API key"
            autoComplete="off"
            className="w-20 min-w-0 bg-transparent text-xs text-slate-200 placeholder-slate-500 outline-none xs:w-28 narrow:w-44"
          />
          {dirty && pendingKey.trim() !== '' && (
            <button
              type="button"
              onClick={onSaveKey}
              title="Save API key"
              aria-label="Save API key"
              className="shrink-0 rounded p-0.5 text-emerald-400 hover:bg-emerald-500/15 hover:text-emerald-200"
            >
              <Check className="h-3.5 w-3.5" />
            </button>
          )}
          {savedKey && (
            <button
              type="button"
              onClick={onClearKey}
              title="Clear API key"
              aria-label="Clear API key"
              className="shrink-0 text-slate-500 hover:text-slate-200"
            >
              <X className="h-3 w-3" />
            </button>
          )}
          {savedFlash && !dirty && (
            <span className="hidden shrink-0 text-[10px] text-emerald-400 narrow:inline">saved</span>
          )}
        </div>
      </div>
    </header>
  );
}