import { useEffect, useRef, useState } from 'react';
import { Trash2, ArrowDown } from 'lucide-react';

/**
 * Renders the live log stream for a single job.
 *
 * Props:
 *   - events:  Array<{ type, stream?, data?, ... }>   from useJobStream
 *   - onClear: optional callback (parent decides what to clear)
 */
export default function LogView({ events, onClear }) {
  const ref = useRef(null);
  const [stickToBottom, setStickToBottom] = useState(true);

  // Auto-scroll unless the user scrolled up.
  useEffect(() => {
    const el = ref.current;
    if (!el || !stickToBottom) return;
    el.scrollTop = el.scrollHeight;
  }, [events, stickToBottom]);

  const onScroll = (e) => {
    const el = e.currentTarget;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    setStickToBottom(atBottom);
  };

  return (
    // flex-1 + min-h-0 so this fills whatever height the parent grid cell
    // gives it. The outer JobDetail section uses h-full, so the log block
    // stretches to match the Jobs sidebar's row height. The internal scroll
    // container keeps long sessions from overflowing the panel.
    <div className="relative flex min-h-105 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-950 shadow-inner shadow-black/60">
      <div className="flex items-center justify-between border-b border-slate-700 bg-slate-800/70 px-4 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Live logs
          <span className="ml-2 font-mono text-[10px] text-slate-500">
            {events.length} event{events.length === 1 ? '' : 's'}
          </span>
        </span>
        <div className="flex items-center gap-2">
          {!stickToBottom && (
            <button
              onClick={() => { setStickToBottom(true); ref.current?.scrollTo({ top: ref.current.scrollHeight }); }}
              className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-300 ring-1 ring-emerald-500/30 hover:bg-emerald-500/25"
            >
              <ArrowDown className="h-3 w-3" /> jump to latest
            </button>
          )}
          {onClear && (
            <button
              onClick={onClear}
              className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-rose-300"
              title="Clear log"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      <pre
        ref={ref}
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-auto px-4 py-3 font-mono text-[12.5px] leading-relaxed text-slate-200"
      >
        {events.length === 0 ? (
          <span className="text-slate-600">waiting for events…</span>
        ) : (
          events.map((e, i) => <LogLine key={i} event={e} />)
        )}
      </pre>
    </div>
  );
}

function LogLine({ event }) {
  if (event.type === 'start') {
    return (
      <div className="text-slate-500">
        <span className="select-none text-slate-700">▶ </span>
        start <span className="text-emerald-300">{event.image}</span>
        <span className="text-slate-500"> · </span>
        <span className="text-slate-300">{event.command}</span>
      </div>
    );
  }
  if (event.type === 'exit') {
    const ok = event.statusCode === 0 && !event.timedOut;
    return (
      <div className={ok ? 'text-emerald-400' : 'text-rose-400'}>
        <span className="select-none text-slate-700">■ </span>
        exit code <span className="font-bold">{event.statusCode}</span>
        {event.timedOut ? ' (timed out)' : ''}
      </div>
    );
  }
  if (event.type === 'log') {
    const color =
      event.stream === 'stderr' ? 'text-rose-300'
        : event.stream === 'system' ? 'text-amber-300'
          : 'text-slate-200';
    return (
      <div className={color}>
        {event.data}
      </div>
    );
  }
  if (event.type === 'error') {
    return <div className="text-rose-400">✖ {event.data}</div>;
  }
  if (event.type === 'connected') {
    return <div className="text-sky-400">● stream connected</div>;
  }
  return <div className="text-slate-500">{JSON.stringify(event)}</div>;
}