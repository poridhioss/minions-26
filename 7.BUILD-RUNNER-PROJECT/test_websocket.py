"""Stream live build logs over WebSocket and print them with a status header."""
import asyncio
import json
import sys

import websockets


async def watch_logs(job_id: str) -> None:
    uri = f"ws://localhost:8000/logs/{job_id}"
    async with websockets.connect(uri) as ws:
        print(f"=== Watching {job_id} ===\n")
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "status":
                print(f"[STATUS] {msg.get('status'):>10}  {msg.get('message','')}", flush=True)
            elif msg.get("type") == "log":
                print(f"  | {msg.get('line','')}", flush=True)
            else:
                print(json.dumps(msg), flush=True)
            if msg.get("status") in ("success", "failed"):
                print("\n=== Build finished ===")
                return


if __name__ == "__main__":
    job_id = sys.argv[1] if len(sys.argv) > 1 else input("Enter job_id: ")
    asyncio.run(watch_logs(job_id))