import { useState } from 'react';
import { Play } from 'lucide-react';
import { submitJob } from '../api';

const PRESETS = [
  { label: 'alpine · hello',  image: 'alpine', command: 'echo hello && sleep 1 && echo world' },
  { label: 'alpine · timing', image: 'alpine', command: 'echo start && sleep 2 && echo done' },
  { label: 'alpine · fail',   image: 'alpine', command: 'echo about to fail && exit 7' },
];

/**
 * Sticky form on the right side. Submits a job and calls `onSubmitted(jobId)`
 * so the parent can show it in the sidebar / open it in the detail pane.
 */
export default function JobForm({ onSubmitted }) {
  const [image, setImage]   = useState('alpine');
  const [command, setCommand] = useState('echo hello && sleep 1 && echo world');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]   = useState(null);
  const [unauthorized, setUnauthorized] = useState(false);
  const [serverDown, setServerDown] = useState(false);

  const submit = async (e) => {
    e?.preventDefault?.();
    setSubmitting(true);
    setError(null);
    try {
      const { jobId } = await submitJob({ image, command });
      onSubmitted?.(jobId, image, command);
      setError(null);
      setUnauthorized(false);
      setServerDown(false);
    } catch (err) {
      if (err?.code === 'unauthorized') {
        setUnauthorized(true);
        setServerDown(false);
        setError('Unauthorized — check the API key in the header.');
      } else if (err?.code === 'server_down') {
        setServerDown(true);
        setUnauthorized(false);
        setError('Server unreachable — is the backend running?');
      } else {
        setUnauthorized(false);
        setServerDown(false);
        setError(err.message || 'submit failed');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex h-full flex-col gap-3 rounded-xl border border-slate-700 bg-slate-900/95 p-3 shadow-xl shadow-black/40 xs:p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">New Job</h2>
        <button
          type="button"
          className="text-[11px] text-slate-400 hover:text-emerald-300"
          onClick={() => { setImage('alpine'); setCommand('echo hello && sleep 1 && echo world'); }}
        >
          reset
        </button>
      </div>

      <label className="flex flex-col gap-1">
        <span className="text-[10px] uppercase tracking-wide text-slate-400">Image</span>
        <input
          id="job-image"
          name="image"
          value={image}
          onChange={(e) => setImage(e.target.value)}
          placeholder="alpine"
          autoComplete="off"
          className="rounded-md bg-slate-800/70 px-3 py-1.5 font-mono text-sm text-slate-100 ring-1 ring-slate-700 outline-none focus:ring-emerald-500/50"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-[10px] uppercase tracking-wide text-slate-400">Command</span>
        <textarea
          id="job-command"
          name="command"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          rows={3}
          placeholder="sh -c command"
          autoComplete="off"
          className="resize-y rounded-md bg-slate-800/70 px-3 py-1.5 font-mono text-sm text-slate-100 ring-1 ring-slate-700 outline-none focus:ring-emerald-500/50"
        />
      </label>

      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => { setImage(p.image); setCommand(p.command); }}
            className="rounded-full bg-slate-800/70 px-3 py-1 text-[11px] text-slate-300 ring-1 ring-slate-700 hover:bg-slate-700/70 hover:text-slate-100"
          >
            {p.label}
          </button>
        ))}
      </div>

{error && (
        <div
          role="alert"
          className={`rounded-md px-3 py-2 text-xs ring-1 ${
            unauthorized
              ? 'bg-amber-500/10 text-amber-300 ring-amber-500/30'
              : serverDown
                ? 'bg-slate-500/10 text-slate-300 ring-slate-500/30'
                : 'bg-rose-500/10 text-rose-300 ring-rose-500/30'
          }`}
        >
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={submitting || !image || !command}
        className="inline-flex items-center justify-center gap-2 rounded-md bg-emerald-500 px-3 py-2 text-sm font-semibold text-emerald-950 shadow shadow-emerald-500/20 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
      >
        <Play className="h-4 w-4" />
        {submitting ? 'Submitting…' : 'Run Job'}
      </button>
    </form>
  );
}