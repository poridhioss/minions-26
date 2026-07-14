import { useCallback, useEffect, useState } from 'react';
import Header from './components/Header';
import JobForm from './components/JobForm';
import JobList from './components/JobList';
import JobDetail from './components/JobDetail';
import { listJobs, deleteJobs, submitJob } from './api';

/**
 * App layout:
 *
 *   ┌───────────────────────────────────────────────────────────┐
 *   │ Header                                                    │
 *   ├──────────────────┬─────────────────────────┬──────────────┤
 *   │ JobList          │ JobDetail               │ JobForm      │
 *   │ (sidebar)        │ (logs + status)         │ (new job)    │
 *   └──────────────────┴─────────────────────────┴──────────────┘
 */
export default function App() {
  const [jobs, setJobs] = useState([]);        // submitted in this tab
  const [selectedId, setSelectedId] = useState(null);
  const [authLocked, setAuthLocked] = useState(false);
  // Persistent server-down indicator. Distinct from `authLocked` because
  // the recovery steps are different (re-key vs. restart backend), and
  // they shouldn't fight for the same banner slot.
  const [serverDown, setServerDown] = useState(false);

  // Pull the persisted job list from the backend. The server now enriches
  // every row with its current state in one round-trip — no more N+1
  // /jobs/:id calls. Reused by mount-time hydration and by the manual
  // refresh button in the header. Always runs the network call so that
  // saving a corrected API key takes effect immediately; 401s flip
  // authLocked back on if the new key is also wrong. The 2s polling
  // effect below is what actually skips requests when locked — keeping
  // the console quiet between saves.
  const hydrate = useCallback(async () => {
    try {
      const list = await listJobs();
      // Server returned data — we're definitely not down.
      setServerDown(false);
      if (!list.length) {
        setJobs((prev) => prev); // no-op; keep any jobs already shown
        setAuthLocked(false);
        return;
      }
      // Map server rows → sidebar rows. Server now returns `state` directly,
      // and `queuedAt` already in ISO form, so we just normalize the field
      // names the sidebar reads.
      const seeded = list.map((j) => ({
        jobId: j.jobId,
        image: j.image,
        command: j.command,
        submittedAt: j.queuedAt ? Date.parse(j.queuedAt) : Date.now(),
        status: j.state || 'unknown',
        exitCode: j.exitCode,
        startedAt: j.startedAt,
        finishedAt: j.finishedAt,
        durationMs: j.durationMs,
      }));
      setJobs(seeded);
      setAuthLocked(false);
    } catch (err) {
      if (err?.code === 'unauthorized') {
        setAuthLocked(true);
        setServerDown(false);
      } else if (err?.code === 'server_down') {
        setServerDown(true);
      }
      /* backend down / other errors — leave jobs[] as-is so the user can
         still see the last-known state until the backend recovers */
    }
    // Empty deps are intentional — hydrate reads `authLocked` only via the
    // setter, so a stable reference is fine and lets `onApiKeySaved` call
    // it right after `setAuthLocked(false)` without a stale closure.
  }, []);

  // Hydrate the sidebar from the backend on mount so a refresh keeps history.
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect --
       hydrate's own setState calls are intentional */
    hydrate();
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [hydrate]);

  // Periodically refresh statuses of jobs in the sidebar. We rely on the
  // server's enriched `listJobs` endpoint — a single round-trip carries
  // each row's current state — instead of fanning out one /jobs/:id call
  // per row, which used to flood devtools with hundreds of requests on a
  // busy session. When a request fails we keep the previously-known state
  // so a finished job doesn't suddenly look "waiting" again. Suspended
  // while `authLocked` is true so a stale key doesn't spam 401s on every
  // tick.
  /* eslint-disable react-hooks/exhaustive-deps --
     we only want this to re-run when the *count* of jobs changes; tracking
     the array itself would restart polling on every status tick. */
  useEffect(() => {
    if (jobs.length === 0 || authLocked) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const list = await listJobs();
        if (cancelled) return;
        setServerDown(false);
        // Build the new sidebar rows from server data. Anything already
        // in `jobs` keeps its identity (so the user keeps their selection
        // and any local-only fields like the 'cancelling' transient); new
        // rows appear, vanished rows drop out (the BullMQ removeOnComplete
        // TTL can cause finished jobs to disappear, which is correct).
        const byId = new Map(jobs.map((j) => [j.jobId, j]));
        const visible = list.filter((j) => {
          const state = (j.state || 'unknown').toLowerCase();
          return state !== 'deleted' && state !== 'removed';
        });
        const merged = visible.map((j) => {
          const incoming = {
            jobId: j.jobId,
            image: j.image,
            command: j.command,
            submittedAt: j.queuedAt ? Date.parse(j.queuedAt) : Date.now(),
            status: j.state || 'unknown',
            exitCode: j.exitCode,
            startedAt: j.startedAt,
            finishedAt: j.finishedAt,
            durationMs: j.durationMs,
          };
          // Preserve any local-only fields (e.g. the brief 'cancelling'
          // transient that JobDetail sets) when the row's status matches
          // what's already on screen. Drop the override once the server
          // reports a terminal state so the user sees the final status
          // (completed / failed / cancelled) instead of being stuck on
          // 'cancelling' forever.
          const existing = byId.get(j.jobId);
          const terminalFromServer = ['completed', 'failed', 'cancelled'].includes(incoming.status);
          if (existing && existing.status === 'cancelling' && !terminalFromServer) {
            return { ...incoming, status: existing.status };
          }
          return incoming;
        });
        setJobs(merged);
      } catch (err) {
        if (err?.code === 'unauthorized') {
          setAuthLocked(true);
          setServerDown(false);
        } else if (err?.code === 'server_down') {
          setServerDown(true);
        }
      }
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => { cancelled = true; clearInterval(id); };
  }, [jobs.length, authLocked]);
  /* eslint-enable react-hooks/exhaustive-deps */

  const onSubmitted = (jobId, image, command) => {
    setJobs((prev) => [
      { jobId, image, command, submittedAt: Date.now(), status: 'waiting' },
      ...prev,
    ]);
    setSelectedId(jobId);
  };

  // Called by JobDetail after its 10-second cool-off so a cancelled job
  // gets re-queued with the same image+command. Errors are surfaced as
  // flash banners so the user knows the resubmit didn't go through.
  const onResubmit = async (image, command) => {
    try {
      const { jobId } = await submitJob({ image, command });
      onSubmitted(jobId, image, command);
    } catch (err) {
      if (err?.code === 'unauthorized') {
        setFlash({ kind: 'auth', text: 'Unauthorized — check the API key in the header.' });
      } else if (err?.code === 'server_down') {
        setFlash({ kind: 'err', text: 'Server is down — could not re-run.' });
      } else {
        setFlash({ kind: 'err', text: err?.message || 're-run failed' });
      }
    }
  };

  // Called by JobDetail when the user deletes the currently-open job.
  const onDeleted = (jobId) => {
    setJobs((prev) => prev.filter((j) => j.jobId !== jobId));
    if (selectedId === jobId) setSelectedId(null);
    setFlash({ kind: 'ok', text: 'Job deleted.' });
  };

  const onClearList = async (ids) => {
    // Always require a non-empty selection; the UI no longer offers a
    // "clear all" affordance.
    if (!ids || ids.length === 0) return;
    try {
      await deleteJobs(ids);
      setJobs((prev) => prev.filter((j) => !ids.includes(j.jobId)));
      if (ids.includes(selectedId)) setSelectedId(null);
      setFlash({ kind: 'ok', text: `Deleted ${ids.length} job${ids.length === 1 ? '' : 's'}.` });
      // A successful delete implies the server is reachable — drop any
      // stale server-down indicator that was hanging on screen.
      setServerDown(false);
    } catch (err) {
      if (err?.code === 'unauthorized') {
        setFlash({ kind: 'auth', text: 'Unauthorized — check the API key in the header.' });
        setServerDown(false);
      } else if (err?.code === 'server_down') {
        setServerDown(true);
        setFlash({ kind: 'err', text: 'Server is down — could not delete.' });
      } else {
        setFlash({ kind: 'err', text: err?.message || 'delete failed' });
      }
    }
  };

  // Flash banner (success/error toasts). Declared before `onRefresh` because
  // `onRefresh` clears it on every click.
  const [flash, setFlash] = useState(null);
  useEffect(() => {
    if (!flash) return;
    const id = setTimeout(() => setFlash(null), 4000);
    return () => clearTimeout(id);
  }, [flash]);

  // Refresh button state: spinner while a manual re-hydrate is in flight.
  const [refreshing, setRefreshing] = useState(false);
  // refreshKey is used as the React `key` on JobDetail so a manual refresh
  // remounts the panel and useJobStream re-fetches from scratch (otherwise
  // stale log buffers and the cached `status` from before the refresh stay
  // on screen). refreshBump also forces Header to re-poll /healthz right
  // away instead of waiting up to 10s for the next tick.
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshBump, setRefreshBump] = useState(0);
  const onRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    // Clear stale banners so the user gets a clean slate while we retry.
    // If the retry fails, hydrate() will re-set whichever flags apply
    // (authLocked on 401, serverDown on transport failure).
    setFlash(null);
    setAuthLocked(false);
    setServerDown(false);
    try {
      await hydrate();
    } finally {
      setRefreshing(false);
      // Bump the keys *after* hydrate resolves so the new mount happens
      // against fresh data.
      setRefreshKey((k) => k + 1);
      setRefreshBump((k) => k + 1);
    }
  };

  // Called by Header right after the user saves a new API key. Clears the
  // auth-lock so the saved value actually takes effect on the next request,
  // then immediately re-runs the sidebar hydration (and bumps the detail
  // key so useJobStream re-fetches the open job's logs/status too).
  const onApiKeySaved = async () => {
    setAuthLocked(false);
    try {
      await hydrate();
    } catch {
      /* hydrate already surfaces 401s internally */
    }
    setRefreshKey((k) => k + 1);
    setRefreshBump((k) => k + 1);
  };

  const selectedJob = jobs.find((j) => j.jobId === selectedId) || null;

  return (
    // min-h-screen + overflow-x-hidden so the page scrolls vertically
    // instead of forcing everything into the viewport height. The 3-col
    // grid below is `auto-rows`, so each panel grows to its natural height
    // and the LogView never gets squeezed below 400px on narrow widths.
    <div className="relative min-h-screen w-full overflow-x-hidden text-slate-100">
      {/* Dark scrim over the body-level hero image. Keeps panels readable
          without nuking the artwork entirely — a soft slate wash that
          sits between the background and the colored tint blobs. The
          radial gradient on top of this fades the corners back into the
          whale so the page doesn't feel like a flat gray slab. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 z-0 bg-slate-950/80"
      />
      {/* Layered radial gradients give the page some depth without
          competing with the panel chrome. Two soft blobs in indigo/cyan
          sit on top of the slate base. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(ellipse_at_top_left,rgba(99,102,241,0.10),transparent_60%),radial-gradient(ellipse_at_bottom_right,rgba(6,182,212,0.08),transparent_65%)]"
      />
      <div className="relative z-10 flex min-h-screen flex-col">
        <Header
          onRefresh={onRefresh}
          refreshing={refreshing}
          authLocked={authLocked}
          healthzBump={refreshBump}
          onApiKeySaved={onApiKeySaved}
        />
        {authLocked && (
          <div
            role="status"
            className="mx-3 mt-3 rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-300 ring-1 ring-amber-500/30"
          >
            API key rejected — check the header. Sidebar state may be stale until fixed.
          </div>
        )}
        {serverDown && (
          // Persistent (not auto-dismissed) indicator distinct from the
          // amber auth banner: gets its own slate/blue styling so the user
          // can tell "wrong key" from "backend isn't running". Cleared the
          // moment any request succeeds, or by a manual refresh click.
          <div
            role="status"
            className="mx-3 mt-3 rounded-md bg-sky-500/10 px-3 py-2 text-xs text-sky-300 ring-1 ring-sky-500/30"
          >
            Server is down — request can't be made. Sidebar shows the last-known state until the backend recovers.
          </div>
        )}
        {flash && (
          <div
            role="status"
            className={`mx-3 mt-3 rounded-md px-3 py-2 text-xs ring-1 ${
              flash.kind === 'ok'
                ? 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30'
                : flash.kind === 'auth'
                  ? 'bg-amber-500/10 text-amber-300 ring-amber-500/30'
                  : 'bg-rose-500/10 text-rose-300 ring-rose-500/30'
            }`}
          >
            {flash.text}
          </div>
        )}
        {/*
          Layout (custom breakpoints: xs=480px, narrow=890px):
            < xs       (  <480):  single column. List collapses into a drawer
                                   above; detail below; form at the bottom.
            xs-narrow  (480–890): two columns — list + detail, form below.
                                   Sidebar is a slim 200px rail.
            narrow-lg  (890–1024): two columns — list + detail, form below.
                                    Sidebar grows to 240px.
            lg+        (1024+):  three columns — list + detail + form side
                                 by side.
            xl+        (1280+):  wider three-column.
          `items-stretch` makes every cell in a row share the tallest
          sibling's height, which is what aligns the Jobs sidebar to the
          detail logs at width. The page still scrolls vertically if the
          viewport is shorter than the natural content height.
        */}
        <main className="grid items-stretch auto-rows-min grid-cols-1 gap-3 p-3 xs:gap-4 xs:p-4 xs:grid-cols-[200px_minmax(0,1fr)] narrow:grid-cols-[240px_minmax(0,1fr)] lg:grid-cols-[260px_minmax(0,1fr)_320px] xl:grid-cols-[300px_minmax(0,1fr)_360px]">
          <JobList
            jobs={jobs}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onClear={onClearList}
          />
          <JobDetail
            key={selectedJob ? `detail-${selectedJob.jobId}-${refreshKey}` : `detail-empty-${refreshKey}`}
            job={selectedJob}
            authLocked={authLocked}
            onCancelDone={() => { /* status will refresh via polling */ }}
            onResubmit={onResubmit}
            onDeleted={onDeleted}
          />
          <div className="xs:col-span-2 lg:col-span-1">
            <JobForm onSubmitted={onSubmitted} />
          </div>
        </main>
      </div>
    </div>
  );
}
