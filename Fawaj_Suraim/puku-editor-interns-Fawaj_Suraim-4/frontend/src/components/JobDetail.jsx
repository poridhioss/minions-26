import { useEffect, useState } from 'react';
import { useJobStream } from '../hooks/useJobStream';
import { cancelJob, deleteJob } from '../api';
import StatusPill from './StatusPill';
import LogView from './LogView';
import ConfirmModal from './ConfirmModal';
import { Ban, Trash2 } from 'lucide-react';

const RERUN_DELAY_MS = 10_000;

/**
 * The main panel for one job. Shows header (image, command, status, cancel,
 * delete) and the live log stream below.
 *
 * Props:
 *   - job:           { jobId, image, command, ... }
 *   - onCancelDone:  optional callback fired after a successful cancel
 *   - onResubmit:    optional (image, command) => void — called after a
 *                    10-second cool-off following a cancel, so the parent
 *                    can resubmit the same job.
 *   - onDeleted:     optional (jobId) => void — fired after a successful delete
 *                    so the parent can drop the row from the sidebar.
 */
export default function JobDetail({ job, onCancelDone, onResubmit, onDeleted, authLocked = false }) {
  const { status, events } = useJobStream(job?.jobId, authLocked);
  const live = status || { state: 'waiting' };
  const isTerminal = live.state === 'completed' || live.state === 'failed' || live.state === 'cancelled' || live.state === 'unknown';
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState(null);
  // When the user clicks "Cancel & Re-run" we capture the intent as state
  // (image+command) and start a 10-second countdown. When the countdown
  // hits zero we fire onResubmit exactly once. `pendingRerun` carries the
  // intent so the effect below doesn't resubmit on mount with no intent.
  const [pendingRerun, setPendingRerun] = useState(null);
  const [rerunCountdown, setRerunCountdown] = useState(0); // seconds remaining
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Reset the rerun intent if the user navigates to a different job.
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect --
       resetting on jobId change is intentional */
    setPendingRerun(null);
    setRerunCountdown(0);
    setCancelling(false);
    setCancelError(null);
    setDeleting(false);
    setDeleteError(null);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [job?.jobId]);

  // Once the worker actually reports a terminal state, drop the
  // "cancelling" spinner — the cancel completed successfully and the
  // worker tore the container down. We also drop the spinner on
  // `state === 'unknown'`, which is what `getStatus` returns once BullMQ
  // has TTL'd the job out via `removeOnComplete`/`removeOnFail` — without
  // this, a job that finished and aged out would leave the cancel button
  // stuck forever.
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect --
       reacting to a polled-state change to clear the spinner is the
       intent here — without it the button stays in the "cancelling…"
       state forever. */
    if (cancelling && (isTerminal || live.state === 'unknown')) setCancelling(false);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [cancelling, isTerminal, live.state]);

  // Tick the rerun countdown every second while > 0.
  useEffect(() => {
    if (rerunCountdown <= 0) return;
    const id = setInterval(() => {
      setRerunCountdown((s) => (s > 1 ? s - 1 : 0));
    }, 1000);
    return () => clearInterval(id);
  }, [rerunCountdown]);

  // Fire the resubmit exactly once when the countdown reaches 0.
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect --
       one-shot fire — clear the intent in the same tick so a re-render
       with the same state doesn't re-fire. */
    if (rerunCountdown !== 0 || !pendingRerun) return;
    const { image: img, command: cmd } = pendingRerun;
    setPendingRerun(null);
    onResubmit?.(img, cmd);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [rerunCountdown, pendingRerun, onResubmit]);

  const onCancel = async () => {
    // Allow re-entry while already cancelling: if the previous attempt
    // got stuck (e.g. the cancel request lost the BullMQ lock race and
    // the cancel-key has since expired, or the worker is wedged), the
    // user needs a way to fire another cancel. Only the rerun countdown
    // should block the button — that's a different concept (we're
    // committed to resubmitting on a timer).
    if (rerunCountdown > 0) return;
    setCancelling(true);
    setCancelError(null);
    try {
      await cancelJob(job.jobId);
      onCancelDone?.();
    } catch (err) {
      setCancelError(err?.code === 'unauthorized' ? 'Unauthorized — check API key.' : (err?.message || 'cancel failed'));
      setCancelling(false);
      return;
    }
    // Don't re-enable Cancel here — the worker still needs to tear down the
    // container (could be in the middle of a long `sleep N`). Stay in the
    // "cancelling" state until the actual job state transitions, or until the
    // 10s cool-off kicks in for Cancel & Re-run. The live `isTerminal` flag
    // from useJobStream controls the button from this point.
    if (pendingRerun && onResubmit) {
      setRerunCountdown(Math.ceil(RERUN_DELAY_MS / 1000));
    }
  };

  const requestDelete = () => {
    if (deleting) return;
    setDeleteError(null);
    setConfirmDelete(true);
  };

  const performDelete = async () => {
    if (deleting) return;
    setConfirmDelete(false);
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteJob(job.jobId);
      onDeleted?.(job.jobId);
    } catch (err) {
      setDeleteError(err?.code === 'unauthorized' ? 'Unauthorized — check API key.' : (err?.message || 'delete failed'));
      setDeleting(false);
    }
  };

  const onCancelAndRerun = async () => {
    // Mirrors onCancel: only the rerun countdown blocks — re-clicking
    // should restart the 10s cool-off, not be silently ignored.
    if (rerunCountdown > 0) return;
    // Record intent as state — don't mutate the `job` prop. The fire-once
    // effect above will call onResubmit when the countdown hits zero.
    setPendingRerun({ image: job.image, command: job.command });
    await onCancel();
  };

  if (!job) {
    return (
      <div className="flex h-full flex-col items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-900/70 p-6 text-center shadow-inner shadow-black/40 xs:p-12">
        <span className="text-sm text-slate-400">No job selected.</span>
        <span className="mt-1 text-xs text-slate-500">Submit one on the right, or pick one from the sidebar.</span>
      </div>
    );
  }

  return (
    <section className="flex h-full min-h-0 flex-col gap-3">
      {/*
        Detail header. Two-row layout below `xs` (480px):
          row 1: image, command (truncates), status pill, delete button
          row 2: cancel / cancel & re-run actions
        On wider viewports everything flows in one wrapping row.
      */}
      <header className="flex flex-col gap-2 rounded-xl border border-slate-700 bg-slate-900/95 px-3 py-3 shadow-xl shadow-black/40 xs:flex-row xs:flex-wrap xs:items-center xs:gap-3 xs:px-4">
        <div className="hidden flex-col xs:flex">
          <span className="text-[10px] uppercase tracking-wide text-slate-500">Job</span>
          <span className="font-mono text-xs text-slate-300">{job.jobId}</span>
        </div>
        <div className="mx-2 hidden h-8 w-px bg-slate-800 xs:block" />
        <div className="flex min-w-0 flex-col">
          <span className="text-[10px] uppercase tracking-wide text-slate-500">Image</span>
          <span className="truncate font-mono text-sm text-emerald-300">{job.image}</span>
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-[10px] uppercase tracking-wide text-slate-500">Command</span>
          <span className="truncate font-mono text-sm text-slate-200">{job.command}</span>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill state={live.state} />
          <button
            onClick={requestDelete}
            disabled={deleting}
            title="Delete this job"
            aria-label="Delete this job"
            className="inline-flex items-center gap-1 rounded-md bg-slate-800/60 px-2.5 py-1 text-xs font-medium text-slate-400 ring-1 ring-slate-700 transition hover:bg-rose-500/15 hover:text-rose-300 hover:ring-rose-500/40 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span className="hidden xs:inline">{deleting ? 'Deleting…' : 'Delete'}</span>
          </button>
        </div>
        {rerunCountdown > 0 ? (
          <button
            disabled
            className="inline-flex w-full items-center justify-center gap-1 rounded-md bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-200 ring-1 ring-amber-500/40 cursor-wait xs:w-auto xs:justify-start"
          >
            <Ban className="h-3.5 w-3.5" />
            Re-running in {rerunCountdown}s…
          </button>
        ) : !isTerminal ? (
          <div className="flex w-full flex-wrap items-center gap-2 xs:w-auto xs:flex-nowrap">
            <button
            onClick={onCancel}
            disabled={rerunCountdown > 0}
            aria-pressed={cancelling}
            title={cancelling ? 'Cancel requested — click again to force-cancel' : 'Cancel this job'}
            className={`inline-flex flex-1 items-center justify-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium ring-1 transition xs:flex-none ${
              cancelling
                ? 'bg-rose-500/30 text-rose-100 ring-rose-500/50 cursor-pointer hover:bg-rose-500/40 hover:ring-rose-400'
                : 'bg-rose-500/15 text-rose-300 ring-rose-500/40 hover:bg-rose-500/30 hover:text-rose-100 hover:ring-rose-400 hover:shadow-md hover:shadow-rose-500/40 active:bg-rose-500/50 active:shadow-rose-500/60'
            }`}
          >
            <Ban className="h-3.5 w-3.5" />
            {cancelling ? 'Cancel (click to force)' : 'Cancel'}
          </button>
            {onResubmit && (
              <button
                onClick={onCancelAndRerun}
                disabled={rerunCountdown > 0}
                title="Cancel now and re-submit after 10s"
                className="inline-flex flex-1 items-center justify-center gap-1 rounded-md bg-rose-500/10 px-2.5 py-1 text-xs font-medium text-rose-300 ring-1 ring-rose-500/30 hover:bg-rose-500/25 hover:text-rose-100 hover:ring-rose-400 hover:shadow-md hover:shadow-rose-500/40 active:bg-rose-500/40 disabled:cursor-not-allowed disabled:opacity-60 xs:flex-none"
              >
                <Ban className="h-3.5 w-3.5" />
                Cancel &amp; Re-run
              </button>
            )}
          </div>
        ) : null}
      </header>
      {(cancelError || deleteError) && (
        <div
          role="alert"
          className={`rounded-md px-3 py-2 text-xs ring-1 ${
            (cancelError || deleteError)?.toLowerCase().includes('unauthorized')
              ? 'bg-amber-500/10 text-amber-300 ring-amber-500/30'
              : 'bg-rose-500/10 text-rose-300 ring-rose-500/30'
          }`}
        >
          {cancelError || deleteError}
        </div>
      )}

      {(live.startedAt || live.finishedAt || live.durationMs != null) && (
        <div className="grid grid-cols-2 gap-2 rounded-xl border border-slate-700 bg-slate-800/70 px-3 py-2 text-[11px] text-slate-300 xs:px-4 sm:grid-cols-4">
          <Stat label="queued"   value={fmt(live.queuedAt)}   />
          <Stat label="started"  value={fmt(live.startedAt)}  />
          <Stat label="finished" value={fmt(live.finishedAt)} />
          <Stat label="duration" value={live.durationMs != null ? `${live.durationMs} ms` : '—'} />
        </div>
      )}

      <LogView events={events} />
      <ConfirmModal
        open={confirmDelete}
        title="Delete this job?"
        message={`This will remove job ${job.jobId.slice(0, 8)}… and its logs from the orchestrator. If it is still running, it will be stopped and removed from the queue.`}
        confirmLabel="Delete"
        onConfirm={performDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </section>
  );
}

function Stat({ label, value }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-slate-500">{label}</span>
      <span className="font-mono text-slate-200">{value || '—'}</span>
    </div>
  );
}

function fmt(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return d.toLocaleTimeString();
}