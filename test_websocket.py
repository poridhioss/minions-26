import asyncio
import websockets
import json

async def watch_logs(job_id):
    uri = f"ws://localhost:8000/logs/{job_id}"
    async with websockets.connect(uri) as websocket:
        print(f"Watching logs for job: {job_id}\n")
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Status: {data['status']} | {data.get('message', '')}")
            if data["status"] in ["success", "failed"]:
                print("\nJob finished!")
                break

if __name__ == "__main__":
    job_id = input("Enter job_id: ")
    asyncio.run(watch_logs(job_id))