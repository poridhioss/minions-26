# minions-26

Lab repository for the **Build Runner** project — a self-hosted, mini-CI pipeline
that takes a GitHub URL, clones it, builds a Docker image, pushes to
`ghcr.io`, and redeploys a running container on port 8080.

👉 **All project code, docs, and the React dashboard live in
[`build-runner-project/`](./build-runner-project/).**

## What's inside

```
build-runner-project/
├── main.py              FastAPI server (HTTP + WebSocket)
├── worker.py            Background build/push/deploy worker
├── docker_builder.py    Docker SDK wrapper with live log streaming
├── redis_helper.py      Redis client + key constants
├── Dockerfile           Container image for API + worker
├── docker-compose.yml   Local dev stack
├── requirements.txt     Python dependencies
├── frontend/            React + Vite dashboard
├── docs/                Screenshots and reference assets
├── BUILD_REQUIREMENTS.md  What your repo needs to build successfully
├── Assat/               Asset folder
└── README.md            Full project README (start here)
```

## Quick start

```bash
cd build-runner-project
cat README.md    # → full project documentation
```

## See the live UI

The React dashboard (after `cd frontend && npm run dev`) runs at
<http://localhost:5173> and lets you paste a GitHub URL, trigger a build,
and watch the log stream in real time.

---

Built during the **minions-26** lab sessions.
