# Phase 1: Project Setup ✅

## Overview
This phase covers the initial setup of the Build Runner project, including creating the project structure, setting up a Python virtual environment, installing FastAPI, and running the first API server.

---

## Objectives
- ✅ Create project folder and directory structure
- ✅ Set up Python virtual environment
- ✅ Install FastAPI and required dependencies
- ✅ Create and run the first FastAPI server

---

## Step 1: Create Project Folder

Create a new project directory:

```bash
mkdir build-runner-project
cd build-runner-project
```

This will be the root directory for the entire project.

---

## Step 2: Set Up Python Virtual Environment

Create a Python virtual environment to isolate project dependencies:

```bash
python3 -m venv venv
```

Activate the virtual environment:

**On Linux/macOS:**
```bash
source venv/bin/activate
```

**On Windows:**
```bash
venv\Scripts\activate
```

You should see `(venv)` prefix in your terminal, indicating the virtual environment is active.

---

## Step 3: Install Dependencies

Update pip to the latest version:

```bash
pip install --upgrade pip
```

Install FastAPI and Uvicorn (ASGI server):

```bash
pip install fastapi uvicorn
```

**Dependency Explanation:**
- **FastAPI**: Modern Python web framework for building APIs with automatic documentation
- **Uvicorn**: Lightning-fast ASGI server to run FastAPI applications

Verify installation:
```bash
pip list
```

---

## Step 4: Create the First FastAPI Server

Create `main.py` in the project root:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Build Runner System is alive!"}
```

**Code Explanation:**
- `FastAPI()`: Creates the FastAPI application instance
- `@app.get("/")`: Decorator that defines a GET endpoint at the root path
- `home()`: Handler function that returns a JSON response

---

## Step 5: Run the Server

Start the development server:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Command Parameters:**
- `main:app`: Reference to the FastAPI app instance in main.py
- `--reload`: Auto-restart server when code changes (development only)
- `--host 0.0.0.0`: Listen on all network interfaces
- `--port 8000`: Run on port 8000

You should see output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

---

## Step 6: Test the Server

Open a browser or use curl to test:

```bash
curl http://localhost:8000/
```

Expected response:
```json
{"message": "Build Runner System is alive!"}
```

**Optional:** Visit `http://localhost:8000/docs` for interactive API documentation (Swagger UI).

---

## Project Structure After Phase 1

```
build-runner-project/
├── venv/                    # Virtual environment
├── main.py                  # FastAPI application
└── requirements.txt         # (Optional) List of dependencies
```

---

## Creating requirements.txt

To make the project reproducible, create a `requirements.txt` file:

```bash
pip freeze > requirements.txt
```

Contents should include:
```
fastapi==0.104.0
uvicorn==0.24.0
```

This allows others to install dependencies with:
```bash
pip install -r requirements.txt
```

---

## Summary

✅ Project folder created  
✅ Virtual environment set up  
✅ FastAPI installed  
✅ First server running  
✅ API endpoint responding  

**Next Phase:** Phase 2 - Redis + API (Install Redis, create `/build` and `/status` endpoints)

---

## Troubleshooting

**Issue:** `command not found: python3`
- **Solution:** Install Python 3.8+ from python.org or use package manager

**Issue:** `ModuleNotFoundError: No module named 'fastapi'`
- **Solution:** Ensure virtual environment is activated, then reinstall: `pip install fastapi`

**Issue:** Port 8000 already in use
- **Solution:** Use different port: `uvicorn main:app --reload --port 8001`
