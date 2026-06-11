import redis
import json
import time
import subprocess
import os
import shutil
from docker_builder import build_image
from notifier import send_notification

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=10
)

def update_status(job_id, status, message=""):
    job_data = r.get(f"job:{job_id}")
    if job_data:
        job = json.loads(job_data)
        job["status"] = status
        job["message"] = message
        r.set(f"job:{job_id}", json.dumps(job))
        print(f"[{job_id}] Status → {status} | {message}", flush=True)

def clone_repo(job_id, github_url):
    clone_dir = f"/tmp/build_{job_id}"
    if os.path.exists(clone_dir):
        shutil.rmtree(clone_dir)

    update_status(job_id, "cloning", f"Cloning {github_url}")
    result = subprocess.run(
        ["git", "clone", github_url, clone_dir],
        capture_output=True, text=True, timeout=60
    )

    if result.returncode != 0:
        update_status(job_id, "failed", result.stderr.strip())
        return None

    return clone_dir

def process_job(job_id, github_url):
    update_status(job_id, "running", "Job started")

    clone_dir = clone_repo(job_id, github_url)
    if not clone_dir:
        return

    # build docker image from cloned repo
    update_status(job_id, "building", "Docker build started")
    success, result = build_image(job_id, clone_dir)

    if success:
        update_status(job_id, "success", f"Image built: {result}")
        send_notification(job_id, "success", f"Image built: {result}")
    else:
        update_status(job_id, "failed", f"Build failed: {result}")
        send_notification(job_id, "failed", f"Build failed: {result}")

def worker_loop():
    print("Worker started. Waiting for jobs...", flush=True)
    while True:
        try:
            result = r.blpop("build_queue", timeout=5)
            if result is None:
                continue
            _, job_data_str = result
            job_data = json.loads(job_data_str)
            process_job(job_data["job_id"], job_data["github_url"])
        except KeyboardInterrupt:
            print("Worker stopped.")
            break
        except Exception as e:
            print(f"Error: {e}", flush=True)
            time.sleep(2)

if __name__ == "__main__":
    worker_loop()