import { useEffect, useRef, useState } from 'react';
import { getJob, fetchLogs } from '../api';

/**
 * useJobStream(jobId, authLocked)
 *
 * Single source of truth = GET /jobs/:id/logs (returns the full event buffer
 * from Redis). We poll it every second while the job is non-terminal, so the
 * UI shows the latest output without missing anything a WebSocket race could
 * lose. Once the job reaches a terminal state we stop polling; the last fetch
 * is the final state.
 *
 * When `authLocked` is true, polling is fully suspended so a rejected API
 * key doesn't flood the console with 401s on every tick.
 *
 * Returns { status, events, error, connected, refresh }.
 */
export function useJobStream(jobId, authLocked = false) {
  const [status, setStatus] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);
  const [connected, setConnected] = useState(true);
  // `cancelledRef` flips on unmount/jobId change so in-flight fetches from
  // the previous job don't bleed into the next.
  const cancelledRef = useRef(false);

  // Re-arm the poller whenever the jobId changes, or whenever auth locks
  // / unlocks. The dep on `authLocked` cleanly tears down + re-creates the
  // interval so we don't need a mutable ref.
  useEffect(() => {
    cancelledRef.current = false;
    /* eslint-disable react-hooks/set-state-in-effect --
       resetting on mount is intentional — switching jobIds should show
       the new job's state, not the previous one. The "unauthorized"
       branch also intentionally surfaces a hint synchronously when the
       lock flips on. */
    if (!jobId || authLocked) {
      if (authLocked) {
        setError('unauthorized');
        setConnected(false);
      } else {
        setStatus(null);
        setEvents([]);
        setError(null);
        setConnected(false);
      }
      return undefined;
    }

    setEvents([]);
    setStatus(null);
    setError(null);
    setConnected(true);
    /* eslint-enable react-hooks/set-state-in-effect */

    const tick = async () => {
      if (cancelledRef.current) return;
      try {
        const [s, lines] = await Promise.all([
          getJob(jobId),
          fetchLogs(jobId).catch(() => []),
        ]);
        if (cancelledRef.current) return;
        setStatus(s);
        if (lines && lines.length) setEvents(lines);
        const terminal = s?.state === 'completed' || s?.state === 'failed' || s?.state === 'cancelled' || s?.state === 'unknown';
        if (terminal) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          setConnected(false);
        }
      } catch (e) {
        // 404 means the job was deleted (or aged out and the row was
        // scrubbed). Stop polling immediately so we don't keep hammering
        // the API with a missing-resource request. Surface the deleted
        // sentinel — components like JobDetail already render an empty
        // state when `status` is null, so the JobDetail's parent will
        // drop the row on its next `listJobs` poll.
        if (e?.status === 404) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          setStatus({ state: 'deleted', jobId });
          setConnected(false);
          return;
        }
        if (!cancelledRef.current) setError(e.message || 'fetch failed');
      }
    };

    const pollRef = { current: null };
    tick();
    pollRef.current = setInterval(tick, 1000);

    return () => {
      cancelledRef.current = true;
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [jobId, authLocked]);

  const refresh = async () => {
    if (!jobId || authLocked) return;
    try {
      const [s, lines] = await Promise.all([
        getJob(jobId),
        fetchLogs(jobId).catch(() => []),
      ]);
      setStatus(s);
      if (lines && lines.length) setEvents(lines);
    } catch {
    /* swallow — refresh is best-effort */
  }
  };

  return { status, events, error, connected, refresh };
}