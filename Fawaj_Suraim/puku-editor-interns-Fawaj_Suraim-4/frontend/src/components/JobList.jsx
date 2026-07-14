import { useEffect, useMemo, useState } from 'react';
import { Trash2, ChevronDown, ChevronUp } from 'lucide-react';
import StatusPill from './StatusPill';
import ConfirmModal from './ConfirmModal';

/**
 * Left sidebar list of submitted jobs.
 *
 * Props:
 *   - jobs:        Array<{ jobId, image, command, submittedAt, status }>
 *   - selectedId:  currently-open jobId
 *   - onSelect(id): user clicked a job
 *   - onClear(ids): parent decides what to do; pass ids array (empty = all)
 */
export default function JobList({ jobs, selectedId, onSelect, onClear }) {
  // Set of selected jobIds. Local to the list so checkbox state survives
  // selection changes / polling refreshes.
  const [picked, setPicked] = useState(() => new Set());

  // On viewports narrower than `narrow` (890px) the list becomes a
  // collapsible drawer so the detail panel stays visible by default.
  // narrow+ shows it inline.
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 55.625rem)'); // --breakpoint-narrow
    const onChange = () => { if (mq.matches) setExpanded(true); };
    onChange();
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const allSelected = jobs.length > 0 && picked.size === jobs.length;
  const someSelected = picked.size > 0 && picked.size < jobs.length;

  const toggle = (id) => {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (allSelected) setPicked(new Set());
    else setPicked(new Set(jobs.map((j) => j.jobId)));
  };

  const headerLabel = useMemo(() => {
    if (picked.size > 0) return `delete ${picked.size}`;
    return 'delete';
  }, [picked.size]);

  const [confirmClear, setConfirmClear] = useState(false);

  const askDelete = () => {
    if (picked.size === 0) return;
    setConfirmClear(true);
  };

  const performClear = () => {
    if (picked.size === 0) return;
    const ids = [...picked];
    setPicked(new Set());
    setConfirmClear(false);
    onClear?.(ids);
  };

  return (
    // `max-h` caps the sidebar so very long lists scroll internally instead
    // of pushing the page off-screen. The whole page is scrollable, so the
    // sidebar can be a constrained scroll region without locking the layout.
    <aside
      data-expanded={expanded ? 'true' : 'false'}
      className="flex h-full min-h-0 flex-col gap-2 rounded-xl border border-slate-700 bg-slate-900/95 p-2 shadow-xl shadow-black/40 xs:p-3"
    >
      <div className="flex items-center justify-between gap-1 px-1">
        <h2 className="min-w-0 truncate text-sm font-semibold uppercase tracking-wide text-slate-300">
          Jobs
          <span className="ml-2 rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-normal text-slate-400">
            {jobs.length}
          </span>
          {picked.size > 0 && (
            <span className="ml-2 inline-block rounded-full bg-emerald-500/15 px-2 py-0.5 align-middle text-[10px] font-normal text-emerald-300 ring-1 ring-emerald-500/30">
              {picked.size} sel
            </span>
          )}
        </h2>
        <div className="flex shrink-0 items-center gap-1">
          {picked.size > 0 && (
            <>
              <button
                type="button"
                onClick={() => setPicked(new Set())}
                className="hidden rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200 xs:inline-block"
                title="clear selection"
              >
                <span className="text-[10px] uppercase tracking-wide">clear</span>
              </button>
              <button
                onClick={askDelete}
                title={headerLabel}
                aria-label={headerLabel}
                className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-rose-300"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </>
          )}
          {/*
            Narrow-viewport collapse toggle. Hidden once the `narrow`
            breakpoint (890px) kicks in — on those viewports the body is
            always shown.
          */}
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200 narrow:hidden"
            title={expanded ? 'collapse jobs' : 'expand jobs'}
            aria-expanded={expanded}
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {jobs.length > 0 && picked.size > 0 && (
        <label className="hidden cursor-pointer items-center gap-2 px-1 text-[10px] uppercase tracking-wide text-slate-500 hover:text-slate-300 xs:flex">
          <input
            type="checkbox"
            checked={allSelected}
            ref={(el) => { if (el) el.indeterminate = someSelected; }}
            onChange={toggleAll}
            className="h-3 w-3 cursor-pointer rounded border-slate-700 bg-slate-800 text-emerald-500 focus:ring-emerald-500/50"
          />
          <span>{allSelected ? 'deselect all' : 'select all'}</span>
        </label>
      )}

      <div className={`-mx-1 min-h-0 flex-1 overflow-y-auto px-1 ${expanded ? 'block' : 'hidden'} narrow:block`}>
        {jobs.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-1 px-4 py-12 text-center text-xs text-slate-500">
            <span className="font-mono">No jobs yet</span>
            <span className="narrow:hidden">Tap “Jobs” above to see this list.</span>
            <span className="hidden narrow:inline">Submit one on the right to see it stream here.</span>
          </div>
        ) : (
          <ul className="flex flex-col gap-1">
            {jobs.map((j) => {
              const isActive = j.jobId === selectedId;
              const isPicked = picked.has(j.jobId);
              const isTerminal = j.status === 'completed' || j.status === 'failed' || j.status === 'unknown';
              const ts = j.submittedAt || j.queuedAt;
              return (
                <li key={j.jobId}>
                  <div
                    className={`group flex w-full items-stretch rounded-lg border text-left transition ${
                      isActive
                        ? 'border-emerald-500/40 bg-emerald-500/5'
                        : isTerminal
                          ? 'border-slate-800/60 bg-slate-800/40 opacity-70 hover:opacity-100'
                          : 'border-transparent hover:border-slate-700 hover:bg-slate-800/60'
                    }`}
                  >
                    {/*
                      Checkbox column — kept always visible below `xs`
                      (the rows aren't big enough to hide it on hover)
                      so a user can multi-select on a phone-width viewport
                      without a discoverability problem. Hidden until row
                      is hovered/focused on wider screens.
                    */}
                    <label
                      className={`flex shrink-0 cursor-pointer items-center pl-2 pr-1 transition ${
                        isPicked || isActive
                          ? 'opacity-100'
                          : 'opacity-100 xs:opacity-0 xs:group-hover:opacity-100 xs:focus-within:opacity-100'
                      }`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={isPicked}
                        onChange={() => toggle(j.jobId)}
                        onClick={(e) => e.stopPropagation()}
                        aria-label={`select ${j.image || 'job'} ${j.jobId.slice(0, 8)}`}
                        className="h-3 w-3 cursor-pointer rounded border-slate-700 bg-slate-800 text-emerald-500 focus:ring-emerald-500/50"
                      />
                    </label>
                    {/* Single clickable surface for selecting a job. Spans
                        the whole row width minus the checkbox column. */}
                    <button
                      type="button"
                      onClick={() => onSelect(j.jobId)}
                      className="min-w-0 flex-1 rounded-r-lg px-2 py-1.5 text-left focus:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500/50 xs:py-2"
                    >
                      <div className="flex items-center justify-between gap-1.5">
                        <span
                          className={`min-w-0 truncate font-mono text-xs ${
                            isTerminal ? 'text-slate-400 line-through decoration-slate-600' : 'text-slate-200'
                          }`}
                        >
                          {j.image || '?'}
                        </span>
                        {/* Always show the job state — full word on narrow+,
                            compact dot on xs where columns are tight. */}
                        <StatusPill state={j.status} compact="xs" className="w-auto xs:hidden" />
                        <StatusPill state={j.status} className="hidden xs:inline-flex" />
                      </div>
                      <div
                        className={`mt-0.5 hidden truncate font-mono text-[11px] xs:mt-1 xs:block ${
                          isTerminal ? 'text-slate-500' : 'text-slate-400'
                        }`}
                      >
                        {j.command}
                      </div>
                      <div className="mt-0.5 hidden truncate font-mono text-[10px] text-slate-600 narrow:block">
                        {j.jobId.slice(0, 8)} · {ts ? new Date(ts).toLocaleTimeString() : '—'}
                      </div>
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <ConfirmModal
        open={confirmClear}
        title={picked.size === 1 ? 'Delete this job?' : `Delete ${picked.size} jobs?`}
        message={`This will remove ${picked.size} job${picked.size === 1 ? '' : 's'} and their logs from the orchestrator. Running jobs will be stopped and removed.`}
        confirmLabel="Delete"
        onConfirm={performClear}
        onCancel={() => setConfirmClear(false)}
      />
    </aside>
  );
}