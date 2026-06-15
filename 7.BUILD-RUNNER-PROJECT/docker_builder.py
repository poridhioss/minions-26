"""Build a Docker image and stream every line of build output into a Redis list.

The worker calls build_image(job_id, clone_dir, redis_client). Each chunk that
the Docker SDK emits is appended to `logs:{job_id}` (a Redis LIST) with an LPUSH
and a cap of 5000 entries so we never blow up Redis on a huge build.

main.py's /logs WebSocket tails that list to give clients a live feed.
"""
from __future__ import annotations

import os
import time
from typing import Optional

import docker


LOG_KEY = "logs:{}"
LOG_MAX = 5000  # cap list length per job


def _push_log(redis_client, job_id: str, line: str) -> None:
    """Append a single log line for this job, keeping the list bounded."""
    if not line:
        return
    key = LOG_KEY.format(job_id)
    try:
        redis_client.lpush(key, line)
        redis_client.ltrim(key, 0, LOG_MAX - 1)
    except Exception as e:
        # Logging must never abort the build
        print(f"[docker_builder] redis log push failed: {e}", flush=True)


def build_image(job_id: str, clone_dir: str, redis_client) -> tuple[bool, str]:
    """Build a Docker image from a cloned repo and stream its logs into Redis.

    Returns (success, message). message is the image tag on success or the
    error string on failure.
    """
    try:
        client = docker.from_env()
    except Exception as e:
        return False, f"docker daemon unreachable: {e}"

    dockerfile_path = os.path.join(clone_dir, "Dockerfile")
    if not os.path.exists(dockerfile_path):
        return False, "Dockerfile not found in repo"

    image_tag = f"build-runner/{job_id}:latest"

    try:
        _push_log(redis_client, job_id, f"--- Building image {image_tag} ---")

        # images.build() returns (image, build_logs); build_logs is already a streaming
        # generator of log dicts — iterate it to push live lines to Redis.
        image, build_logs = client.images.build(
            path=clone_dir,
            tag=image_tag,
            rm=True,
            forcerm=True,
        )

        for entry in build_logs:
            if "stream" in entry and entry["stream"]:
                # entry["stream"] already includes a trailing \n for most steps
                line = entry["stream"].rstrip()
                if line:
                    print(line, flush=True)
                    _push_log(redis_client, job_id, line)
            elif "error" in entry:
                err = entry["error"].strip()
                _push_log(redis_client, job_id, f"ERROR: {err}")
                return False, err
            elif "status" in entry:
                # pull / extract events
                line = entry["status"].strip()
                if line:
                    print(line, flush=True)
                    _push_log(redis_client, job_id, line)

        _push_log(redis_client, job_id, f"--- Built {image_tag} ---")
        return True, image_tag

    except docker.errors.BuildError as e:
        msg = str(e).strip()
        _push_log(redis_client, job_id, f"BUILD ERROR: {msg}")
        return False, msg
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        _push_log(redis_client, job_id, f"ERROR: {msg}")
        return False, msg