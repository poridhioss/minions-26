from fastapi import FastAPI, WebSocket
import redis
import json
import uuid
import asyncio

app = FastAPI()

import os
r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)
@app.get("/")
def home():
    return {"message": "Build Runner System is alive!"}

@app.post("/build")
def start_build(github_url: str):
    job_id = str(uuid.uuid4())
    job_data = {"job_id": job_id, "github_url": github_url, "status": "queued"}
    r.set(f"job:{job_id}", json.dumps(job_data))
    # push job to queue so worker can pick it up
    r.lpush("build_queue", json.dumps({"job_id": job_id, "github_url": github_url}))
    return {"job_id": job_id, "status": "queued"}

@app.get("/status/{job_id}")
def get_status(job_id: str):
    job_data = r.get(f"job:{job_id}")
    if not job_data:
        return {"error": "Job not found"}
    return json.loads(job_data)

@app.websocket("/logs/{job_id}")
async def websocket_logs(websocket: WebSocket, job_id: str):
    await websocket.accept()
    # keep sending status updates until job is done
    while True:
        job_data = r.get(f"job:{job_id}")
        if job_data:
            job = json.loads(job_data)
            await websocket.send_text(json.dumps(job))
            # stop streaming if job finished
            if job["status"] in ["success", "failed"]:
                break
        await asyncio.sleep(1)
    await websocket.close()