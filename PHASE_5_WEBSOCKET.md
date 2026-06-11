# Phase 5: Real-Time WebSocket Logs ✅

## Overview
This phase implements WebSocket communication for real-time status streaming. Instead of repeatedly polling the `/status` endpoint, clients can connect to a WebSocket endpoint and receive live updates as they happen, automatically closing when the build completes.

---

## Objectives
- ✅ Implement WebSocket endpoint
- ✅ Stream status updates in real-time
- ✅ Auto-close connection when build completes
- ✅ Handle client connections gracefully
- ✅ Create WebSocket client for testing

---

## Step 1: Understanding WebSocket vs HTTP Polling

### Traditional HTTP Polling (Before):
```
Client                          Server
  │                               │
  ├─ GET /status/{job_id} ───────>│
  │<─ {"status": "running"} ──────┤
  │ (wait 1 second)               │
  ├─ GET /status/{job_id} ───────>│
  │<─ {"status": "cloning"} ──────┤
  │ (wait 1 second)               │
  ├─ GET /status/{job_id} ───────>│
  │<─ {"status": "building"} ─────┤
  │                               │
  (many requests, lots of overhead)
```

### WebSocket Streaming (Now):
```
Client                          Server
  │                               │
  ├─ UPGRADE to WebSocket ───────>│
  │<─ Connection established ─────┤
  │<─ {"status": "running"} ──────┤ (push)
  │<─ {"status": "cloning"} ──────┤ (push)
  │<─ {"status": "building"} ─────┤ (push)
  │<─ {"status": "success"} ──────┤ (push + close)
  │
  (one connection, server-initiated updates)
```

### Benefits:
- **Lower latency**: Instant updates vs polling intervals
- **Reduced bandwidth**: One connection, push-based vs many requests
- **Lower CPU**: No busy polling
- **Better UX**: Real-time progress display

---

## Step 2: Update main.py with WebSocket Endpoint

Add WebSocket support to `main.py`:

**Add this import at the top:**
```python
import asyncio
```

**Add this endpoint after the `/status` endpoint:**
```python
@app.websocket("/logs/{job_id}")
async def websocket_logs(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for real-time build status streaming.
    Sends status updates as they occur, closes when build completes.
    """
    # Accept the WebSocket connection
    await websocket.accept()
    
    # Stream status updates until job completes
    while True:
        # Get current job data from Redis
        job_data = r.get(f"job:{job_id}")
        
        if job_data:
            # Parse and send job data to client
            job = json.loads(job_data)
            await websocket.send_text(json.dumps(job))
            
            # Stop streaming if job has completed
            if job["status"] in ["success", "failed"]:
                break
        
        # Check for new updates every 1 second
        await asyncio.sleep(1)
    
    # Close the WebSocket connection
    await websocket.close()
```

**Updated complete main.py:**
```python
from fastapi import FastAPI, WebSocket
import redis
import json
import uuid
import asyncio

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

@app.websocket("/logs/{job_id}")
async def websocket_logs(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for real-time build status streaming.
    Sends status updates as they occur, closes when build completes.
    """
    await websocket.accept()
    
    while True:
        job_data = r.get(f"job:{job_id}")
        if job_data:
            job = json.loads(job_data)
            await websocket.send_text(json.dumps(job))
            # Stop streaming if job finished
            if job["status"] in ["success", "failed"]:
                break
        await asyncio.sleep(1)
    
    await websocket.close()
```

---

## Step 3: Create WebSocket Test Client

Create `test_websocket.py` for testing:

```python
import asyncio
import websockets
import json

async def watch_logs(job_id):
    """
    Connect to WebSocket endpoint and stream logs.
    Automatically closes when build completes.
    """
    uri = f"ws://localhost:8000/logs/{job_id}"
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Watching logs for job: {job_id}\n")
            
            while True:
                # Receive status update from server
                message = await websocket.recv()
                data = json.loads(message)
                
                # Display the update
                status = data['status']
                message_text = data.get('message', '')
                print(f"Status: {status} | {message_text}")
                
                # Exit loop if build finished
                if data["status"] in ["success", "failed"]:
                    print("\nJob finished!")
                    break
                    
    except websockets.exceptions.ConnectionClosed:
        print("Connection closed.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    job_id = input("Enter job_id: ")
    asyncio.run(watch_logs(job_id))
```

---

## Step 4: Install WebSocket Client Library

Install websockets package for testing:

```bash
pip install websockets
```

---

## Step 5: Understanding WebSocket Flow

### Connection Lifecycle:

```python
# 1. Client initiates WebSocket connection
await websocket.accept()  # Server accepts

# 2. Server sends updates in a loop
while True:
    data = get_status()
    await websocket.send_text(json.dumps(data))  # Push to client
    
    # 3. Check if job is complete
    if data["status"] in ["success", "failed"]:
        break  # Exit loop
    
    await asyncio.sleep(1)  # Wait before next update

# 4. Close connection
await websocket.close()
```

### Data Flow:

```json
// Message 1 (immediate)
{"job_id": "...", "status": "queued", "message": ""}

// Message 2 (after 1-2 seconds)
{"job_id": "...", "status": "running", "message": "Job started"}

// Message 3 (after git clone)
{"job_id": "...", "status": "cloning", "message": "Cloning https://..."}

// Message 4 (after clone completes)
{"job_id": "...", "status": "cloned", "message": "Repository cloned successfully"}

// Message 5 (during docker build)
{"job_id": "...", "status": "building", "message": "Docker build started"}

// Message 6 (final - connection closes after)
{"job_id": "...", "status": "success", "message": "Image built: build-runner/..."}
```

---

## Step 6: Testing Phase 5

### Terminal 1: Start Redis
```bash
redis-server
```

### Terminal 2: Start FastAPI
```bash
uvicorn main:app --reload
```

### Terminal 3: Start Worker
```bash
python worker.py
```

### Terminal 4: Submit Build Job
```bash
curl -X POST "http://localhost:8000/build?github_url=https://github.com/docker/welcome-to-docker"
```

Note the `job_id` from response.

### Terminal 5: Connect WebSocket Client
```bash
python test_websocket.py
```

Enter the `job_id` when prompted.

**Output will show:**
```
Watching logs for job: 550e8400-e29b-41d4-a716-446655440000

Status: queued | 
Status: running | Job started
Status: cloning | Cloning https://github.com/docker/welcome-to-docker
Status: cloned | Repository cloned successfully
Status: building | Docker build started
Status: success | Image built: build-runner/550e8400...:latest

Job finished!
```

---

## Step 7: WebSocket vs REST API Comparison

### Use Cases:

| Scenario | Use WebSocket | Use REST API |
|----------|---------------|--------------|
| Real-time monitoring | ✅ Perfect | ❌ Polling overhead |
| Single status check | ❌ Overkill | ✅ Perfect |
| Mobile apps | ✅ Battery efficient | ❌ Battery drain |
| High-frequency updates | ✅ Efficient | ❌ Network congestion |
| Legacy clients | ❌ May not support | ✅ Universal |

---

## Step 8: Advanced WebSocket Features

### Example: Custom WebSocket Handler

```python
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/logs/{job_id}")
async def websocket_logs(websocket: WebSocket, job_id: str):
    try:
        await websocket.accept()
        
        while True:
            job_data = r.get(f"job:{job_id}")
            if job_data:
                job = json.loads(job_data)
                await websocket.send_text(json.dumps(job))
                
                if job["status"] in ["success", "failed"]:
                    break
            
            await asyncio.sleep(1)
    
    except WebSocketDisconnect:
        print(f"Client {job_id} disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()
```

### Example: Send Events as They Happen

Instead of polling Redis every second, update the job immediately:

```python
# In worker.py
def update_status(job_id, status, message=""):
    # ... update Redis ...
    
    # Optionally: notify connected clients
    # (requires implementing a notification system)
    pass
```

---

## Step 9: Browser WebSocket Client Example

Test from browser console:

```javascript
const jobId = "550e8400-e29b-41d4-a716-446655440000";
const ws = new WebSocket(`ws://localhost:8000/logs/${jobId}`);

ws.onopen = (event) => {
    console.log("Connected to WebSocket");
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(`Status: ${data.status} | ${data.message}`);
};

ws.onclose = (event) => {
    console.log("Connection closed");
};

ws.onerror = (event) => {
    console.error("WebSocket error:", event);
};
```

---

## Async Programming Concepts

### Async/Await Basics:

```python
# Regular function (blocks execution)
def sync_task():
    time.sleep(1)
    return "done"

# Async function (non-blocking)
async def async_task():
    await asyncio.sleep(1)  # Yields control, doesn't block
    return "done"

# Run async function
result = asyncio.run(async_task())
```

### Why Async for WebSocket?

```python
# Without async, server can only handle one client:
for websocket in clients:
    status = get_status()  # BLOCKS waiting for file I/O
    send_status(websocket)

# With async, server handles many clients:
async def handle_client(websocket):
    while True:
        status = await get_status()  # Yields control
        await websocket.send_text(...)  # Yields control
        await asyncio.sleep(1)          # Yields control

# Hundreds of clients, one thread (efficient)
```

---

## Summary of Changes

| File | Changes |
|------|---------|
| `main.py` | Added WebSocket `/logs/{job_id}` endpoint |
| `test_websocket.py` | **NEW** - WebSocket test client |
| `requirements.txt` | Add `websockets==11.0+` |

---

## Summary

✅ WebSocket endpoint implemented  
✅ Real-time status streaming working  
✅ Auto-close on job completion  
✅ WebSocket test client created  
✅ Browser-compatible  

**Next Phase:** Phase 6 - Email Notifications (Gmail integration)

---

## Troubleshooting

**Issue:** `websocket.exceptions.InvalidStatusCode: 500`
- **Solution:** Check FastAPI server logs for errors

**Issue:** Client receives data but connection doesn't close
- **Solution:** Ensure job status updates to "success" or "failed"

**Issue:** `ModuleNotFoundError: No module named 'websockets'`
- **Solution:** `pip install websockets`

**Issue:** Connection times out
- **Solution:** Check if job exists in Redis: `redis-cli GET "job:{job_id}"`

---

## Performance Tips

1. **Reduce polling interval** if you need faster updates:
   ```python
   await asyncio.sleep(0.5)  # Check every 500ms instead of 1s
   ```

2. **Implement connection pooling** for many concurrent clients

3. **Add heartbeat** to detect disconnected clients:
   ```python
   await websocket.send_text(json.dumps({"ping": True}))
   ```

4. **Use Redis pub/sub** instead of polling for better performance on large scale
