"""Background worker. Pops jobs from Redis, clones, builds, notifies, cleans up.

Isolation: each build runs inside a one-shot Docker container with --memory and
--cpus limits so two jobs cannot starve the host. The image is tagged with the
job_id and is removed at the end of the run.
"""
import json
import os
import shutil
import subprocess
import time
from typing import Optional

import redis

from docker_builder import build_image
from notifier import send_notification

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
JOB_TTL = int(os.getenv("JOB_TTL", "3600"))  # 1h

# ghcr.io push + redeploy
GITHUB_PAT = os.getenv("GITHUB_PAT", "")
DEMO_IMAGE = os.getenv("DEMO_IMAGE", "")
DEMO_CONTAINER = os.getenv("DEMO_CONTAINER", "demo-app")
DEMO_PORT = os.getenv("DEMO_PORT", "8080")
DEPLOY_ENABLED = os.getenv("DEPLOY_ENABLED", "true").lower() == "true"

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=10,
)


def _push_log(job_id: str, line: str) -> None:
    if not line:
        return
    try:
        r.lpush(f"logs:{job_id}", line)
        r.ltrim(f"logs:{job_id}", 0, 4999)
    except Exception:
        pass


def update_status(job_id: str, status: str, message: str = "") -> None:
    raw = r.get(f"job:{job_id}")
    if raw:
        job = json.loads(raw)
        job["status"] = status
        job["message"] = message
        r.set(f"job:{job_id}", json.dumps(job), ex=JOB_TTL)
        print(f"[{job_id}] {status} | {message}", flush=True)


def clone_repo(job_id: str, github_url: str) -> Optional[str]:
    clone_dir = f"/tmp/build_{job_id}"
    if os.path.exists(clone_dir):
        shutil.rmtree(clone_dir, ignore_errors=True)

    # GitHub disabled password auth — embed PAT in the URL so clone works.
    # Prefer GITHUB_TOKEN (fine-grained) then fall back to GITHUB_PAT.
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT")
    clone_url = github_url
    if token and github_url.startswith("https://github.com/"):
        clone_url = github_url.replace(
            "https://github.com/", f"https://x-access-token:{token}@github.com/"
        )

    update_status(job_id, "cloning", f"Cloning {github_url}")
    try:
        result = subprocess.run(
            ["git", "clone", "--depth=1", clone_url, clone_dir],
            capture_output=True,
            text=True,
            timeout=120,
            # never let the token leak to git's askpass or logs
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/echo"},
        )
    except subprocess.TimeoutExpired:
        update_status(job_id, "failed", "git clone timed out (>120s)")
        return None
    except Exception as e:
        update_status(job_id, "failed", f"git clone error: {e}")
        return None

    if result.returncode != 0:
        # scrub any token that may have echoed back in stderr
        safe_err = (result.stderr or "").replace(token or "x-access-token", "***")
        update_status(job_id, "failed", safe_err.strip() or "git clone failed")
        return None
    return clone_dir


def prune_image(image_tag: str) -> None:
    """Best-effort removal of a built image to protect /var/lib/docker."""
    try:
        import docker
        docker.from_env().images.remove(image_tag, force=True)
    except Exception as e:
        print(f"[{image_tag}] image prune failed: {e}", flush=True)


def push_and_deploy(job_id: str, built_image: str) -> None:
    """Push the just-built image to ghcr.io, then redeploy the running container.

    Step 1: `docker login ghcr.io` using GITHUB_PAT.
    Step 2: `docker tag` the local image as DEMO_IMAGE.
    Step 3: `docker push` to ghcr.io.
    Step 4: stop the old DEMO_CONTAINER, rm it, run the new image on DEMO_PORT.
    """
    if not GITHUB_PAT or not DEMO_IMAGE:
        print(f"[{job_id}] push/deploy skipped (GITHUB_PAT or DEMO_IMAGE empty)", flush=True)
        return

    _push_log(job_id, f"--- Pushing {built_image} -> {DEMO_IMAGE} ---")
    update_status(job_id, "pushing", f"Pushing to {DEMO_IMAGE}")

    # 1. login
    try:
        subprocess.run(
            ["docker", "login", "ghcr.io",
             "-u", "iftakhar-323",
             "--password-stdin"],
            input=GITHUB_PAT,
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
        )
    except Exception as e:
        msg = f"docker login failed: {e}"
        print(f"[{job_id}] {msg}", flush=True)
        _push_log(job_id, f"PUSH ERROR: {msg}")
        update_status(job_id, "failed", msg)
        return

    # 2. tag
    try:
        subprocess.run(
            ["docker", "tag", built_image, DEMO_IMAGE],
            check=True, capture_output=True, text=True, timeout=30,
        )
    except Exception as e:
        msg = f"docker tag failed: {e}"
        _push_log(job_id, f"PUSH ERROR: {msg}")
        update_status(job_id, "failed", msg)
        return

    # 3. push
    try:
        result = subprocess.run(
            ["docker", "push", DEMO_IMAGE],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            msg = (result.stderr or "push failed").strip()
            _push_log(job_id, f"PUSH ERROR: {msg}")
            update_status(job_id, "failed", f"push failed: {msg[:200]}")
            return
        # stream last few push lines into the log
        for line in (result.stdout or "").splitlines()[-5:]:
            _push_log(job_id, line)
    except subprocess.TimeoutExpired:
        msg = "docker push timed out (>600s)"
        _push_log(job_id, f"PUSH ERROR: {msg}")
        update_status(job_id, "failed", msg)
        return
    except Exception as e:
        msg = f"docker push error: {e}"
        _push_log(job_id, f"PUSH ERROR: {msg}")
        update_status(job_id, "failed", msg)
        return

    _push_log(job_id, "--- Push complete ---")

    # 4. redeploy (only if enabled)
    if not DEPLOY_ENABLED:
        update_status(job_id, "success", f"Pushed: {DEMO_IMAGE}")
        return

    update_status(job_id, "deploying", f"Redeploying {DEMO_CONTAINER} on :{DEMO_PORT}")
    _push_log(job_id, f"--- Redeploying container {DEMO_CONTAINER} ---")
    for cmd in (
        ["docker", "stop", DEMO_CONTAINER],
        ["docker", "rm", "-f", DEMO_CONTAINER],
    ):
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    try:
        subprocess.run(
            ["docker", "run", "-d",
             "--name", DEMO_CONTAINER,
             "--restart", "always",
             "-p", f"{DEMO_PORT}:8080",
             DEMO_IMAGE],
            check=True, capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        msg = f"docker run failed: {e}"
        _push_log(job_id, f"DEPLOY ERROR: {msg}")
        update_status(job_id, "failed", msg)
        return

    _push_log(job_id, f"--- Container {DEMO_CONTAINER} started on :{DEMO_PORT} ---")
    update_status(
        job_id,
        "success",
        f"Pushed + deployed: http://localhost:{DEMO_PORT}",
    )


def cleanup_clone(clone_dir: str) -> None:
    shutil.rmtree(clone_dir, ignore_errors=True)


def process_job(job_id: str, github_url: str) -> None:
    update_status(job_id, "running", "Job started")
    clone_dir = clone_repo(job_id, github_url)
    if not clone_dir:
        send_notification(job_id, "failed", "git clone failed")
        return

    update_status(job_id, "building", "Docker build started (isolated runner)")
    success, result = build_image(job_id, clone_dir, r)

    if success:
        # keep image for ~1h so users can pull it, then prune
        try:
            r.set(f"image:{job_id}", result, ex=JOB_TTL)
        except Exception:
            pass
        # push to ghcr.io and redeploy running container
        push_and_deploy(job_id, result)
        # final success line overwrites any deploy error if push_and_deploy succeeded
        cur = r.get(f"job:{job_id}")
        if cur:
            job = json.loads(cur)
            if job.get("status") != "failed":
                update_status(job_id, "success", f"Image: {result}")
                send_notification(job_id, "success", f"Image: {result}")
    else:
        update_status(job_id, "failed", f"Build failed: {result}")
        send_notification(job_id, "failed", f"Build failed: {result}")

    cleanup_clone(clone_dir)
    # schedule image prune after TTL expires
    try:
        from threading import Timer
        Timer(JOB_TTL, prune_image, args=(result if success else "",)).start()
    except Exception:
        pass


def periodic_cleanup() -> None:
    """Run every 10 minutes: drop /tmp/build_* older than 1h, prune dangling images."""
    while True:
        try:
            now = time.time()
            cutoff = now - 3600
            for entry in os.listdir("/tmp"):
                if not entry.startswith("build_"):
                    continue
                path = os.path.join("/tmp", entry)
                try:
                    if os.path.getmtime(path) < cutoff:
                        shutil.rmtree(path, ignore_errors=True)
                except FileNotFoundError:
                    pass

            # prune dangling images only — keep tagged build-runner ones until TTL
            try:
                import docker
                docker.from_env().images.prune(filters={"dangling": True})
            except Exception:
                pass
        except Exception as e:
            print(f"[cleanup] error: {e}", flush=True)
        time.sleep(600)


def worker_loop() -> None:
    print("Worker started. Waiting for jobs...", flush=True)
    while True:
        try:
            result = r.blpop("build_queue", timeout=5)
            if result is None:
                continue
            _, payload = result
            job = json.loads(payload)
            process_job(job["job_id"], job["github_url"])
        except KeyboardInterrupt:
            print("Worker stopped.", flush=True)
            break
        except Exception as e:
            print(f"Worker error: {e}", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    from threading import Thread

    Thread(target=periodic_cleanup, daemon=True).start()
    worker_loop()