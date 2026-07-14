const STYLES = {
  waiting:   'bg-slate-700/40 text-slate-300 ring-slate-600/40',
  active:    'bg-amber-500/15 text-amber-300 ring-amber-500/30 animate-pulse',
  completed: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30',
  cancelled: 'bg-violet-500/15 text-violet-300 ring-violet-500/30',
  failed:    'bg-rose-500/15 text-rose-300 ring-rose-500/30',
  delayed:   'bg-sky-500/15 text-sky-300 ring-sky-500/30',
  unknown:   'bg-slate-700/40 text-slate-400 ring-slate-600/30',
};

export default function StatusPill({ state, compact, className = '' }) {
  const cls = STYLES[state] || STYLES.unknown;
  // `compact` keeps the colored dot only and drops the uppercase word,
  // used in narrow sidebars where every column counts.
  if (compact) {
    return (
      <span
        className={`inline-flex h-2 w-2 shrink-0 rounded-full bg-current ring-1 ring-current/30 ${cls} ${className}`}
        title={state || 'unknown'}
        aria-label={`status: ${state || 'unknown'}`}
      />
    );
  }
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ring-1 ${cls} ${className}`}>
      <span className={`h-1.5 w-1.5 rounded-full bg-current ${state === 'active' ? 'animate-ping' : ''}`} />
      {state || 'unknown'}
    </span>
  );
}