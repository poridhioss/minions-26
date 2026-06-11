# Phase 2: Redis + API Endpoints ✅

## Overview
This phase adds Redis as a message queue and job storage system, and creates two API endpoints:
- `POST /build`: Accept GitHub URLs and queue build jobs
- `GET /status/{job_id}`: Retrieve the status of a specific job

---

## Objectives
- ✅ Install and configure Redis
- ✅ Implement job storage system
- ✅ Create `/build` endpoint to queue jobs
- ✅ Create `/status` endpoint to check job progress

---

## Step 1: Install Redis

### On Linux (Ubuntu/Debian):
```bash
sudo apt-get update
sudo apt-get install redis-server
```

### On macOS (Homebrew):
```bash
brew install redis
```

### On Windows:
Download from [Redis Windows](https://github.com/microsoftarchive/redis/releases) or use WSL

---

## Step 2: Start Redis Server

Start Redis in the background:

```bash
redis-server
```

**Output should show:**
```
# Redis server started on port 6379
```

To verify Redis is running:
```bash
redis-cli ping
```

Should return: `PONG`

---

## Step 3: Install Python Redis Client

With virtual environment activated:

```bash
pip install redis
```

---

## Step 4: Update main.py with Redis Integration

Replace the contents of `main.py`:

```python
from fastapi import FastAPI
import redis
import json
import uuid

app = FastAPI()

# Connect to Redis
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

@app.get("/")
def home():
    return {"message": "Build Runner System is alive!"}

@app.post("/build")
def start_build(github_url: str):
    """
    Start a new build job for the given GitHub URL.
    Returns a unique job_id for tracking progress.
    """
    job_id = str(uuid.uuid4())
    job_data = {
        "job_id": job_id,
        "github_url": github_url,
        "status": "queued"
    }
    
    # Store job data in Redis with key "job:{job_id}"
    r.set(f"job:{job_id}", json.dumps(job_data))
    
    # Push job to queue for worker to process
    r.lpush("build_queue", json.dumps({
        "job_id": job_id,
        "github_url": github_url
    }))
    
    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Build job queued successfully"
    }

@app.get("/status/{job_id}")
def get_status(job_id: str):
    """
    Get the current status of a build job.
    Returns job details including status, URL, and progress.
    """
    job_data = r.get(f"job:{job_id}")
    
    if not job_data:
        return {"error": "Job not found", "job_id": job_id}
    
    return json.loads(job_data)
```

---

## Step 5: Understanding the Data Flow

### Job Creation Flow:
1. Client sends `POST /build?github_url=<url>`
2. API generates unique `job_id` (UUID)
3. Job data stored in Redis with key `job:{job_id}`
4. Job pushed to `build_queue` for worker to pick up
5. Client receives `job_id` to track progress

### Data Structure:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "github_url": "https://github.com/docker/welcome-to-docker",
  "status": "queued",
  "message": ""
}
```

### Redis Keys:
- `job:{job_id}`: Stores complete job data (JSON string)
- `build_queue`: List of pending jobs (queue)

---

## Step 6: Testing Phase 2

### Start the Server:
```bash
uvicorn main:app --reload
```

### Test 1: Create a Build Job

```bash
curl -X POST "http://localhost:8000/build?github_url=https://github.com/docker/welcome-to-docker"
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "message": "Build job queued successfully"
}
```

Save the `job_id` for the next test.

### Test 2: Check Job Status

```bash
curl "http://localhost:8000/status/550e8400-e29b-41d4-a716-446655440000"
```

**Response (while queued):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "github_url": "https://github.com/docker/welcome-to-docker",
  "status": "queued"
}
```

**Response (if job not found):**
```json
{
  "error": "Job not found",
  "job_id": "invalid-id"
}
```

---

## Step 7: Redis CLI Inspection (Optional)

Monitor Redis data in real-time:

```bash
redis-cli
```

Inside Redis CLI:
```
# List all keys
KEYS *

# View a specific job
GET job:{job_id}

# View build queue
LRANGE build_queue 0 -1

# Monitor commands in real-time
MONITOR

# Exit
EXIT
```

---

## Architecture Overview

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /build
       │ GET /status
       ▼
┌─────────────────┐      ┌──────────────┐
│  FastAPI Server │◄────►│  Redis Store │
│   (main.py)     │      │  (Port 6379) │
└─────────────────┘      └──────────────┘
       │
       │ Queue jobs
       ▼
   (Phase 3: Worker)
```

---

## Summary of Changes

| File | Changes |
|------|---------|
| `main.py` | Added Redis connection, `/build` endpoint, `/status` endpoint |
| `requirements.txt` | Added `redis==4.5.0+` |

---

## Key Concepts

### UUID (Universally Unique Identifier)
```python
import uuid
job_id = str(uuid.uuid4())  # Generates: 550e8400-e29b-41d4-a716-446655440000
```
- Guarantees unique job IDs without database
- Safe for distributed systems

### JSON Serialization
```python
# Store (object → JSON string)
r.set(f"job:{job_id}", json.dumps(job_data))

# Retrieve (JSON string → object)
job = json.loads(r.get(f"job:{job_id}"))
```

### Redis List (Queue)
```python
# Push job to front of queue
r.lpush("build_queue", job_json)

# Pop job from end of queue (FIFO)
r.rpop("build_queue")

# Block until job available (worker uses this)
r.blpop("build_queue", timeout=5)
```

---

## Summary

✅ Redis installed and running  
✅ `/build` endpoint creates and queues jobs  
✅ `/status` endpoint tracks job progress  
✅ Jobs stored in Redis with unique IDs  
✅ API tested and working  

**Next Phase:** Phase 3 - Worker (Background job processing)

---

## Troubleshooting

**Issue:** `ConnectionError: Error 111 connecting to localhost:6379`
- **Solution:** Ensure Redis is running: `redis-server`

**Issue:** `ModuleNotFoundError: No module named 'redis'`
- **Solution:** Install with `pip install redis`

**Issue:** Job status not updating
- **Solution:** Verify Redis connection with `redis-cli ping`
