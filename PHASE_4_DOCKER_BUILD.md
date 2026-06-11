# Phase 4: Docker Build System ✅

## Overview
This phase implements Docker image building functionality. The system clones a GitHub repository containing a Dockerfile, builds a Docker image from it, captures build logs, and updates job status throughout the build process.

---

## Objectives
- ✅ Install Docker and Python Docker SDK
- ✅ Implement Docker image builder
- ✅ Validate Dockerfile presence
- ✅ Capture and log build output
- ✅ Handle build errors
- ✅ Integrate with worker process

---

## Step 1: Install Docker

### On Linux (Ubuntu):
```bash
sudo apt-get update
sudo apt-get install docker.io
sudo usermod -aG docker $USER
```

Log out and back in for group changes to take effect.

### On macOS:
```bash
brew install docker
# Or use Docker Desktop: https://www.docker.com/products/docker-desktop
```

### On Windows:
Install Docker Desktop from [docker.com](https://www.docker.com/products/docker-desktop)

### Verify Installation:
```bash
docker --version
docker run hello-world
```

---

## Step 2: Install Python Docker SDK

With virtual environment activated:

```bash
pip install docker
```

Verify installation:
```bash
python -c "import docker; print('Docker SDK installed')"
```

---

## Step 3: Create docker_builder.py

Create a new file `docker_builder.py`:

```python
import docker
import os

# Connect to local Docker daemon
client = docker.from_env()

def build_image(job_id, clone_dir):
    """
    Build a Docker image from a cloned repository.
    
    Args:
        job_id (str): Unique job identifier
        clone_dir (str): Path to cloned repository
        
    Returns:
        tuple: (success: bool, message: str)
               - (True, image_tag) on success
               - (False, error_message) on failure
    """
    
    # Step 1: Validate Dockerfile exists
    dockerfile_path = os.path.join(clone_dir, "Dockerfile")
    if not os.path.exists(dockerfile_path):
        return False, "Dockerfile not found in repo"

    # Step 2: Create unique image tag
    image_tag = f"build-runner/{job_id}:latest"

    try:
        # Step 3: Build Docker image
        print(f"Building image: {image_tag}")
        image, logs = client.images.build(
            path=clone_dir,           # Path to Dockerfile and context
            tag=image_tag,            # Tag for the image
            rm=True                   # Remove intermediate containers
        )

        # Step 4: Stream and print build logs
        for log in logs:
            if "stream" in log:
                print(log["stream"].strip())

        print(f"✓ Image built successfully: {image_tag}")
        return True, image_tag

    except docker.errors.BuildError as e:
        # Docker build failed
        error_msg = str(e)
        print(f"✗ Build error: {error_msg}")
        return False, error_msg
        
    except Exception as e:
        # Other errors (permissions, daemon not running, etc)
        error_msg = str(e)
        print(f"✗ Unexpected error: {error_msg}")
        return False, error_msg
```

---

## Step 4: Update worker.py to Use Docker Builder

Update `worker.py` to integrate docker_builder:

**Find this section in worker.py:**
```python
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
```

**Replace with this updated version:**
```python
from docker_builder import build_image  # Add this import at top

def process_job(job_id, github_url):
    """
    Main job processing function.
    Orchestrates the entire build workflow.
    """
    update_status(job_id, "running", "Job started")

    # Step 1: Clone the repository
    clone_dir = clone_repo(job_id, github_url)
    if not clone_dir:
        return

    # Step 2: Build Docker image from cloned repo
    update_status(job_id, "building", "Docker build started")
    success, result = build_image(job_id, clone_dir)

    # Step 3: Update final status based on build result
    if success:
        update_status(job_id, "success", f"Image built: {result}")
    else:
        update_status(job_id, "failed", f"Build failed: {result}")
```

---

## Step 5: Understanding Docker Build Process

### Docker Image Building Flow:

```
┌──────────────────────────────┐
│ Cloned Repository            │
│ /tmp/build_<job_id>/         │
│ ├── Dockerfile               │
│ ├── app.py                   │
│ ├── requirements.txt         │
│ └── ...                      │
└──────────┬──────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ Validate Dockerfile Exists   │
│ Check: /tmp/.../Dockerfile   │
└──────────┬──────────────────┘
           │
           ▼ (if exists)
┌──────────────────────────────┐
│ Execute: docker build        │
│ - Read Dockerfile            │
│ - Download base image        │
│ - Run build steps            │
│ - Create layers              │
│ - Tag image                  │
└──────────┬──────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ Capture Build Logs           │
│ Print each step output       │
└──────────┬──────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ Return Result                │
│ (success, image_tag)         │
└──────────────────────────────┘
```

### Example Dockerfile (to test with):

Create a test repo by adding `test_dockerfile/Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY . .

RUN pip install flask

EXPOSE 5000

CMD ["python", "app.py"]
```

---

## Step 6: Understanding Image Tagging

### Image Naming Convention:

```
build-runner/550e8400-e29b-41d4-a716:latest
│             │                           │
Registry      Job ID (unique)         Version Tag
```

**Benefits:**
- **Registry prefix** (`build-runner/`): Organizes all images
- **Job ID**: Identifies the build
- **Version tag** (`latest`): Easy to reference

### View Built Images:

```bash
docker images | grep build-runner
```

Output:
```
build-runner/550e8400...   latest    abc123def456   5 seconds ago   500MB
build-runner/other-job...  latest    def456ghi789   1 minute ago    480MB
```

---

## Step 7: Testing Phase 4

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

Worker output should show:
```
Worker started. Waiting for jobs...
```

### Terminal 4: Submit a Build Job

Create a simple GitHub repo or use one with a Dockerfile:

```bash
curl -X POST "http://localhost:8000/build?github_url=https://github.com/docker/welcome-to-docker"
```

Record the `job_id`.

### Terminal 5: Watch Build Progress

```bash
curl "http://localhost:8000/status/{job_id}"
```

Check multiple times to see status progression:

**Status 1 (Running):**
```json
{
  "job_id": "...",
  "status": "running",
  "message": "Job started"
}
```

**Status 2 (Cloning):**
```json
{
  "job_id": "...",
  "status": "cloning",
  "message": "Cloning https://github.com/docker/welcome-to-docker"
}
```

**Status 3 (Building):**
```json
{
  "job_id": "...",
  "status": "building",
  "message": "Docker build started"
}
```

**Status 4 (Success/Failed):**
```json
{
  "job_id": "...",
  "status": "success",
  "message": "Image built: build-runner/550e8400...:latest"
}
```

### Terminal 3: Worker Output

```
[550e8400...] Status → running | Job started
[550e8400...] Status → cloning | Cloning https://github.com/docker/welcome-to-docker
[550e8400...] Status → cloned | Repository cloned successfully
[550e8400...] Status → building | Docker build started
Step 1/5 : FROM python:3.9-slim
 ---> a1234567890abc
Step 2/5 : WORKDIR /app
 ---> Running in xyz123...
...
[550e8400...] Status → success | Image built: build-runner/550e8400...:latest
```

---

## Step 8: Docker CLI Commands

### View Built Images:
```bash
docker images | grep build-runner
```

### Run Built Image:
```bash
docker run build-runner/550e8400...:latest
```

### View Image Details:
```bash
docker inspect build-runner/550e8400...:latest
```

### Clean Up Images:
```bash
# Remove specific image
docker rmi build-runner/550e8400...:latest

# Remove all build-runner images
docker rmi $(docker images --filter=reference='build-runner/*' -q)
```

### View Build Logs (if saved):
```bash
docker logs <container_id>
```

---

## Error Handling Examples

### No Dockerfile
```python
# File: /tmp/build_<id>/Dockerfile → NOT FOUND
# Returns: (False, "Dockerfile not found in repo")
```

### Docker Daemon Not Running
```python
# Raises: docker.errors.DockerException
# Returns: (False, "Cannot connect to Docker daemon")
```

### Build Fails (Missing dependencies)
```python
# Docker returns error during RUN instruction
# Raises: docker.errors.BuildError
# Returns: (False, "Build failed: [error details]")
```

### Permission Denied
```bash
# Current user not in docker group
# Solution: sudo usermod -aG docker $USER
```

---

## Docker Build Options

The `client.images.build()` method supports many options:

```python
image, logs = client.images.build(
    path=clone_dir,           # Build context directory
    tag=image_tag,            # Image tag/name
    rm=True,                  # Remove intermediate containers
    forcerm=False,            # Force removal of intermediate containers
    quiet=False,              # Show build output
    nocache=False,            # Don't use Docker cache
    buildargs={},             # Build arguments
    network_mode='bridge',    # Network mode
)
```

---

## Summary of Changes

| File | Changes |
|------|---------|
| `docker_builder.py` | **NEW** - Docker image building |
| `worker.py` | Updated `process_job()` to call `build_image()` |
| `main.py` | No changes |
| `requirements.txt` | Add `docker==6.1.0+` |

---

## Summary

✅ Docker installed  
✅ Docker SDK installed  
✅ Image building implemented  
✅ Build logs captured  
✅ Dockerfile validation working  
✅ Error handling in place  

**Next Phase:** Phase 5 - WebSocket (Real-time log streaming)

---

## Troubleshooting

**Issue:** `docker.errors.DockerException: Cannot connect to Docker daemon`
- **Solution:** Start Docker: `sudo systemctl start docker`

**Issue:** `PermissionError: Permission denied while trying to connect to the Docker daemon`
- **Solution:** Add user to docker group:
  ```bash
  sudo usermod -aG docker $USER
  # Log out and back in
  ```

**Issue:** `Build failed with no useful error message`
- **Solution:** Check Docker logs:
  ```bash
  docker logs <container_id>
  journalctl -u docker
  ```

**Issue:** Build takes too long
- **Solution:** Docker might be downloading large base images. First build takes longer.
