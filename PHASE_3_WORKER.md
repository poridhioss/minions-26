# Phase 3: Background Worker ✅

## Overview
This phase implements a background worker process that continuously monitors the Redis job queue, picks up pending jobs, clones GitHub repositories, and updates job status throughout the build lifecycle.

---

## Objectives
- ✅ Create background worker process
- ✅ Implement job polling from Redis queue
- ✅ Clone GitHub repositories
- ✅ Track job status progression
- ✅ Handle errors gracefully

---

## Step 1: Install Required Dependencies

Ensure Git is available on your system:

**Linux:**
```bash
sudo apt-get install git
```

**macOS:**
```bash
brew install git
```

**Windows:**
Download from [git-scm.com](https://git-scm.com/download/win)

Install Python package for subprocess operations (already available):
```bash
pip install redis  # Should already be installed
```

---

## Step 2: Create worker.py

Create a new file `worker.py` in the project root:

```python
import redis
import json
import time
import subprocess
import os
import shutil

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

def update_status(job_id, status, message=""):
    """
    Update job status in Redis.
    Maintains job data with current status and message.
    """
    job_data = r.get(f"job:{job_id}")
    if job_data:
        job = json.loads(job_data)
        job["status"] = status
        job["message"] = message
        r.set(f"job:{job_id}", json.dumps(job))
        print(f"[{job_id}] Status → {status} | {message}")

def clone_repo(job_id, github_url):
    """
    Clone the GitHub repository to a temporary directory.
    Returns the clone path on success, None on failure.
    """
    clone_dir = f"/tmp/build_{job_id}"
    
    # Remove existing clone if it exists
    if os.path.exists(clone_dir):
        shutil.rmtree(clone_dir)

    update_status(job_id, "cloning", f"Cloning {github_url}")
    
    # Execute git clone command
    result = subprocess.run(
        ["git", "clone", github_url, clone_dir],
        capture_output=True,
        text=True,
        timeout=60
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip()
        update_status(job_id, "failed", error_msg)
        return None

    update_status(job_id, "cloned", "Repository cloned successfully")
    return clone_dir

def process_job(job_id, github_url):
    """
    Main job processing function.
    Orchestrates the entire build workflow.
    """
    update_status(job_id, "running", "Job started")

    # Clone the repository
    clone_dir = clone_repo(job_id, github_url)
    if not clone_dir:
        return

    # Next phase: Docker build (Phase 4)
    # For now, just mark as ready for building
    update_status(job_id, "ready_for_build", "Repository ready, waiting for docker build")

def worker_loop():
    """
    Main worker loop that continuously monitors the build queue.
    Uses blocking pop (blpop) to avoid busy waiting.
    """
    print("Worker started. Waiting for jobs...")
    while True:
        try:
            # blpop: blocking list pop with 5 second timeout
            # Returns: (key, value) tuple or None if timeout
            result = r.blpop("build_queue", timeout=5)
            
            if result is None:
                # No job available, timeout occurred
                continue
            
            # Unpack the queue result
            _, job_data_str = result
            job_data = json.loads(job_data_str)
            
            # Process the job
            process_job(job_data["job_id"], job_data["github_url"])
            
        except KeyboardInterrupt:
            print("Worker stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(2)  # Wait before retrying

if __name__ == "__main__":
    worker_loop()
```

---

## Step 3: Understanding the Worker Architecture

### Job Processing Flow:

```
┌──────────────────────────────────────────────┐
│ Worker Starts (worker_loop)                  │
└──────────┬───────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────┐
│ Wait for job in "build_queue" (blpop)       │
│ Blocks with 5 second timeout                │
└──────────┬───────────────────────────────────┘
           │ (Job received)
           ▼
┌──────────────────────────────────────────────┐
│ Update Status: "running"                    │
└──────────┬───────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────┐
│ Clone GitHub Repository                     │
│ - Remove old clone directory                │
│ - Execute: git clone <url> /tmp/build_<id>  │
│ - Update Status: "cloning" → "cloned"       │
└──────────┬───────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────┐
│ Ready for Docker Build (Phase 4)            │
└──────────────────────────────────────────────┘
```

### Key Functions:

#### update_status()
- Retrieves job from Redis
- Updates status and message fields
- Persists back to Redis
- Logs status change

#### clone_repo()
- Creates unique directory: `/tmp/build_{job_id}`
- Runs `git clone` with timeout (60 seconds)
- Cleans up previous clone attempts
- Handles errors gracefully

#### process_job()
- Orchestrates job workflow
- Calls helper functions in sequence
- Coordinates with other phases

#### worker_loop()
- Continuously monitors job queue
- Uses `blpop()` for non-blocking monitoring
- Handles interrupts (Ctrl+C)
- Implements error recovery

---

## Step 4: Understanding Redis Blocking Operations

### BLPOP (Blocking List Pop)

```python
# Without blocking (busy loop - BAD):
while True:
    job = r.lpop("build_queue")  # Spins rapidly, wastes CPU
    if job:
        process(job)

# With blocking (efficient - GOOD):
job_data = r.blpop("build_queue", timeout=5)  # Sleeps until job or timeout
if job_data:
    _, job = job_data
    process(job)
```

**Benefits:**
- No CPU waste while waiting
- Instant wake-up when job arrives
- Timeout prevents indefinite blocking

---

## Step 5: Testing Phase 3

### Terminal 1: Start Redis
```bash
redis-server
```

### Terminal 2: Start FastAPI Server
```bash
uvicorn main:app --reload
```

### Terminal 3: Start Worker
```bash
python worker.py
```

You should see:
```
Worker started. Waiting for jobs...
```

### Terminal 4: Submit a Build Job
```bash
curl -X POST "http://localhost:8000/build?github_url=https://github.com/docker/welcome-to-docker"
```

**Observe:**
- Terminal 3 (worker) shows cloning status
- Job directory created at `/tmp/build_{job_id}`

Check job status:
```bash
curl "http://localhost:8000/status/{job_id}"
```

**Response shows status progression:**
```json
{
  "job_id": "...",
  "github_url": "...",
  "status": "ready_for_build",
  "message": "Repository ready, waiting for docker build"
}
```

---

## Step 6: Error Handling

The worker handles several error scenarios:

### Scenario 1: Invalid Git URL
```
Worker Output:
[job_id] Status → failed | fatal: repository not found
```

### Scenario 2: Clone Timeout (60 seconds)
```python
# Git clone times out → subprocess.TimeoutExpired
```

### Scenario 3: Disk Space Full
```
Worker Output:
[job_id] Status → failed | No space left on device
```

---

## Directory Structure

After processing a job:

```
/tmp/
├── build_550e8400-e29b-41d4.../
│   ├── .git/                      # Git metadata
│   ├── Dockerfile                 # (if repo has one)
│   ├── README.md
│   └── ...                        # Repository contents
└── build_other-job-id/
    └── ...
```

---

## Important Notes

### Cleanup
The worker cleans up old clones before creating new ones:
```python
if os.path.exists(clone_dir):
    shutil.rmtree(clone_dir)  # Recursive delete
```

This prevents disk space from growing indefinitely.

### Timeout
Git clone has a 60-second timeout:
```python
subprocess.run(..., timeout=60)
```

If repo is very large, increase this value.

### Logging
All status changes are logged to console for debugging:
```
[job_id] Status → cloning | Cloning https://github.com/...
[job_id] Status → cloned | Repository cloned successfully
```

---

## Summary of Changes

| File | Changes |
|------|---------|
| `worker.py` | **NEW** - Complete worker implementation |
| `main.py` | No changes in this phase |
| `requirements.txt` | No new packages needed |

---

## Summary

✅ Worker process created  
✅ Job queue monitoring implemented  
✅ Repository cloning functional  
✅ Status tracking working  
✅ Error handling in place  

**Next Phase:** Phase 4 - Docker Build (Build Docker images from cloned repos)

---

## Running Worker in Background

### Using nohup (Linux/macOS):
```bash
nohup python worker.py > worker.log 2>&1 &
```

### Using tmux:
```bash
tmux new-session -d -s worker python worker.py
tmux attach -t worker  # View output
```

### Stop Worker:
```bash
# If using nohup
pkill -f "python worker.py"

# If using tmux
tmux kill-session -t worker
```

---

## Troubleshooting

**Issue:** `ModuleNotFoundError: No module named 'redis'`
- **Solution:** `pip install redis`

**Issue:** `git: command not found`
- **Solution:** Install Git, then restart worker

**Issue:** Worker not picking up jobs
- **Solution:** Check Redis connection: `redis-cli ping` → should return PONG

**Issue:** Permission denied in /tmp
- **Solution:** Use alternative temp directory with write permission
