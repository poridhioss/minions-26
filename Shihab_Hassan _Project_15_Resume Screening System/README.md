# AI Resume Screening System

## Overview

The **AI Resume Screening System** is a full-stack application that helps recruiters automatically rank candidates against a job description. Recruiters paste a job description and upload multiple PDF resumes; the system extracts the resume text, computes semantic similarity between each resume and the job description, performs keyword-based skill matching, and returns candidates ordered by a composite relevance score.

The system solves the problem of manually reviewing large volumes of resumes by:

- Converting unstructured resume text into comparable numerical representations (embeddings).
- Performing fast nearest-neighbor similarity search with **FAISS**.
- Detecting required skills that are present or missing in each candidate's resume.
- Presenting the final ranking in an interactive web interface.

## Features

- Job description input via free-text paste.
- Batch upload of multiple PDF resumes.
- Automatic PDF text extraction with **PyMuPDF**.
- Sentence-level semantic embeddings using `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional vectors, normalized).
- Cosine-similarity-based candidate ranking using a **FAISS `IndexFlatIP`** index.
- Keyword-based skill matching against a JSON skills database with whole-word, case-insensitive matching.
- Composite final score: `0.7 × similarity + 0.3 × skill_match_ratio` (weights configurable in `backend/config.py`).
- Per-candidate breakdown of matched, missing, and extra skills.
- Streamlit UI with a summary table, per-candidate detail expanders, and live backend health-check.
- RESTful FastAPI backend with CORS enabled for browser-based clients.
- In-memory session state and on-disk persistence of uploaded PDFs in `uploads/resumes/`.
- Endpoint to reset the current session and start a new ranking batch.

## System Architecture

The application is composed of two independent processes that communicate over HTTP:

```
┌──────────────────┐         HTTP/JSON         ┌──────────────────┐
│   Streamlit UI   │ ────────────────────────▶ │   FastAPI API    │
│  (frontend)      │                           │   (backend)      │
│  Port 8501       │ ◀──────────────────────── │   Port 8000      │
└──────────────────┘                           └──────────────────┘
                                                          │
                                                          ▼
                                                ┌──────────────────────┐
                                                │  ML Pipeline         │
                                                │  ───────────────────  │
                                                │  pdf_parser          │
                                                │  embedder            │
                                                │  faiss_index         │
                                                │  skill_extractor     │
                                                │  ranker              │
                                                └──────────────────────┘
```

**Processing flow for a single `POST /rank` call:**

1. The API receives a request and validates that a job description and at least one resume are present in session state.
2. The job description and every resume are embedded with the `all-MiniLM-L6-v2` model into 384-dim normalized vectors.
3. Resume vectors are added to a fresh FAISS `IndexFlatIP` index.
4. The JD vector is used to query the index, returning similarity scores for every resume.
5. The skill extractor compares the JD against each resume, producing matched, missing, and extra skill lists and a `match_ratio`.
6. The ranker combines the two signals into a final score and sorts candidates in descending order.

## Project Structure

```
Resume Screening System/
├── backend/                    # FastAPI backend package
│   ├── __init__.py             # Package marker
│   ├── config.py               # Paths, model name, ranking weights, API host/port
│   ├── pdf_parser.py           # PyMuPDF-based PDF text extraction & candidate-name heuristic
│   ├── embedder.py             # Lazy-loaded sentence-transformer wrapper (384-dim vectors)
│   ├── faiss_index.py          # FaissIndex wrapper around IndexFlatIP with add/search/reset
│   ├── skill_extractor.py      # Loads skills.json and runs word-boundary skill matching
│   ├── ranker.py               # Combines similarity + skill ratio into a final score and sorts
│   └── main.py                 # FastAPI app, endpoints, in-memory session state
├── frontend/
│   └── app.py                  # Streamlit UI (JD input, PDF upload, ranking results)
├── data/
│   └── skills.json             # Skills database grouped by category
├── uploads/                    # Created automatically at startup
│   └── resumes/                # Persisted uploaded resume PDFs
├── requirements.txt            # Pinned Python dependencies
├── run_backend.bat             # Windows helper to launch the FastAPI server
├── run_frontend.bat            # Windows helper to launch the Streamlit UI
└── README.md
```

### File Responsibilities

| File | Responsibility |
|------|----------------|
| `backend/config.py` | Declares all paths, the embedding model name, the embedding dimension, and the similarity / skill ranking weights. |
| `backend/pdf_parser.py` | Opens a PDF with PyMuPDF, joins text from all pages, normalizes whitespace, and applies a heuristic to extract the candidate's name from the first lines. |
| `backend/embedder.py` | Lazily loads `sentence-transformers/all-MiniLM-L6-v2` and exposes `embed` and `embed_batch` producing normalized float32 vectors. |
| `backend/faiss_index.py` | Wraps `faiss.IndexFlatIP`; provides `add`, `search`, and `reset`, plus parallel metadata storage for each vector. |
| `backend/skill_extractor.py` | Loads `data/skills.json`, pre-compiles per-skill regex, and exposes `extract(text)` and `compare(jd, resume)`. |
| `backend/ranker.py` | Combines FAISS similarity with skill `match_ratio` using configured weights and returns candidates sorted descending by final score. |
| `backend/main.py` | FastAPI application with endpoints, CORS middleware, in-memory session state, and the orchestration of the full screening pipeline. |
| `frontend/app.py` | Streamlit UI that calls the FastAPI endpoints, displays a summary table, and renders per-candidate details. |
| `data/skills.json` | Curated list of skills organized by category (programming, web, data science, cloud/devops, databases, mlops, soft skills). |

## Technology Stack

- **Language:** Python 3
- **Backend framework:** FastAPI
- **ASGI server:** Uvicorn
- **Frontend framework:** Streamlit
- **HTTP client (frontend):** Requests
- **PDF parsing:** PyMuPDF (`fitz`)
- **Embeddings:** Sentence-Transformers (`all-MiniLM-L6-v2`, 384-dim, normalized)
- **Vector search:** FAISS (`faiss.IndexFlatIP` – exact inner product / cosine)
- **Numerical computing:** NumPy
- **Data handling:** Pandas (available as a dependency)
- **Configuration:** python-dotenv
- **Storage:** Local filesystem (`uploads/resumes/`) + in-memory session state

## Installation

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd "Resume Screening System"
```

### 2. Create a virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

The first time the embedder runs, the `all-MiniLM-L6-v2` model will be downloaded from the Hugging Face Hub and cached locally.

### 4. Environment variables

No environment variables are required. All configuration is centralized in `backend/config.py` (`API_HOST`, `API_PORT`, model name, ranking weights). `python-dotenv` is included in `requirements.txt` for future expansion.

## Running the Application

The backend and frontend must run as **two separate processes** in two separate terminals.

### Backend (FastAPI)

From the project root with the virtual environment activated:

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Or on Windows, simply run:

```bash
run_backend.bat
```

The API will be available at `http://127.0.0.1:8000`. Interactive API documentation is auto-generated at `http://127.0.0.1:8000/docs`.

### Frontend (Streamlit)

In a second terminal, from the project root with the virtual environment activated:

```bash
streamlit run frontend/app.py
```

Or on Windows, simply run:

```bash
run_frontend.bat
```

Streamlit will open (by default) at `http://localhost:8501`. The UI performs a `GET /` health check on load and displays a green "Backend is running" indicator if the API is reachable.

### Database

No database is used. Resume PDFs are persisted to `uploads/resumes/`. Candidate text, vectors, and ranking results are kept in process memory in the FastAPI server.

## API Endpoints

All endpoints are defined in `backend/main.py`. The frontend communicates exclusively with these.

| Method | Endpoint         | Description                                                                 |
|--------|------------------|-----------------------------------------------------------------------------|
| GET    | `/`              | Health check. Returns `{"status": "ok", "message": "..."}`.                |
| POST   | `/upload-jd`     | Stores the job description text in session state. Form field: `jd_text`.    |
| POST   | `/upload-resumes`| Accepts one or more PDF files (multipart `files`), parses and stores them. |
| POST   | `/rank`          | Runs the full embedding + FAISS + skill + ranking pipeline.                 |
| GET    | `/results`       | Returns the most recent ranking produced by `/rank`.                        |
| POST   | `/reset`         | Clears the JD, resumes, FAISS index, and stored results.                    |

### Example API requests (using `curl`)

**Upload a job description:**

```bash
curl -X POST http://127.0.0.1:8000/upload-jd \
  -F "jd_text=We are hiring a Senior Python Engineer with experience in NLP, FastAPI, AWS, and Docker."
```

**Upload resumes:**

```bash
curl -X POST http://127.0.0.1:8000/upload-resumes \
  -F "files=@alice.pdf" \
  -F "files=@bob.pdf"
```

**Trigger ranking:**

```bash
curl -X POST http://127.0.0.1:8000/rank
```

**Fetch the last ranking:**

```bash
curl http://127.0.0.1:8000/results
```

**Reset the session:**

```bash
curl -X POST http://127.0.0.1:8000/reset
```

## Workflow

The user-visible flow, implemented by the Streamlit frontend and the FastAPI backend:

```
User Input (Streamlit UI)
   │
   ├── Paste Job Description  ──▶  POST /upload-jd  ──▶  stored in session state
   │
   ├── Upload PDF Resumes     ──▶  POST /upload-resumes
   │                                       │
   │                                       ▼
   │                              pdf_parser.parse_resume
   │                              (text + candidate name)
   │                                       │
   │                                       ▼
   │                              stored in session state
   │
   └── Click "Run Screening"   ──▶  POST /rank
                                          │
                                          ▼
                              embedder.embed / embed_batch
                              (384-dim normalized vectors)
                                          │
                                          ▼
                              faiss_index.add + search
                              (cosine similarity via inner product)
                                          │
                                          ▼
                              skill_extractor.compare
                              (matched / missing / match_ratio)
                                          │
                                          ▼
                              ranker.rank_candidates
                              (0.7 * similarity + 0.3 * skill_match)
                                          │
                                          ▼
                              ranked list returned to UI
                                          │
                                          ▼
                              Streamlit renders summary table
                              and per-candidate detail expanders
```

The `GET /` health check runs automatically when the Streamlit app loads, displaying a green or red status banner.

## Core Modules

| Module | Responsibility |
|--------|----------------|
| `pdf_parser` | Open a PDF with PyMuPDF, concatenate text from all pages, clean whitespace and non-printable characters, and extract the candidate's name using a heuristic that examines the first eight non-empty lines, skipping lines with email addresses or digits. |
| `embedder` | Lazily load the `all-MiniLM-L6-v2` sentence-transformer model on first use, then produce normalized `float32` embeddings of shape `(384,)` for single strings or `(n, 384)` for batches. |
| `faiss_index` | Wrap `faiss.IndexFlatIP` to add a batch of vectors with associated metadata, perform a top-k nearest-neighbor search returning cosine-similarity scores, and reset the index between sessions. |
| `skill_extractor` | Load `data/skills.json`, flatten and de-duplicate the skill list, pre-compile a word-boundary, case-insensitive regex for each skill, then provide `extract(text)` to find present skills and `compare(jd, resume)` to return matched, missing, and extra skills with a `match_ratio`. |
| `ranker` | Merge FAISS similarity and skill `match_ratio` per candidate using the weights from `config.py` (`SIMILARITY_WEIGHT = 0.7`, `SKILL_WEIGHT = 0.3`), round the scores, sort by `final_score` descending, and assign a 1-based `rank` field. |
| `main` (FastAPI) | Define the FastAPI app, enable permissive CORS, hold a single in-memory `state` dictionary for the active session, instantiate the long-lived `Embedder`, `SkillExtractor`, and `FaissIndex` objects, and expose the endpoints that orchestrate the full pipeline. |

## Example Usage

### Input

**Job Description (pasted into the UI):**

```
We are looking for a Senior Python Engineer with experience in NLP, FastAPI,
Docker, AWS, and PostgreSQL. The ideal candidate has worked with machine
learning models, deployed them to production, and is comfortable with
Git-based CI/CD pipelines.
```

**Resumes uploaded:** `alice.pdf`, `bob.pdf`, `charlie.pdf`

### Output (returned by `POST /rank`)

```json
{
  "message": "Ranking complete.",
  "jd_skills": ["python", "fastapi", "docker", "aws", "postgresql", "nlp", "machine learning", "git", "ci/cd"],
  "candidates": [
    {
      "rank": 1,
      "name": "Alice Johnson",
      "file": "alice.pdf",
      "similarity_score": 0.7821,
      "skill_match_ratio": 0.8889,
      "final_score": 0.8141,
      "matched_skills": ["python", "fastapi", "docker", "aws", "postgresql", "nlp", "machine learning", "git"],
      "missing_skills": ["ci/cd"],
      "extra_skills": ["kubernetes", "tensorflow"]
    }
  ]
}
```

In the Streamlit UI the same data is rendered as a sortable summary table plus per-candidate expanders showing similarity, skill match, and final score as percentage metrics, and full lists of matched, missing, and extra skills.

## Future Improvements

- Persist session state (job description, parsed resumes, FAISS index) in a database such as PostgreSQL or Redis so that rankings survive server restarts.
- Replace the in-memory `IndexFlatIP` with an approximate index such as `IndexIVFFlat` or `IndexHNSWFlat` for sub-millisecond search over very large resume corpora.
- Use a stronger embedding model (e.g. `all-mpnet-base-v2`, `bge-large-en`, or a domain-tuned model) for higher semantic accuracy.
- Add a section-aware resume parser that extracts explicit fields (education, experience, certifications) rather than relying on raw text and a name heuristic.
- Allow recruiters to upload multiple job descriptions simultaneously and rank a single resume pool against each.
- Support non-PDF inputs such as `.docx` and `.txt` resumes.
- Add user authentication, role-based access, and multi-tenant support.
- Add unit and integration tests for the parser, embedder, FAISS wrapper, and ranking logic.
- Add Docker and `docker-compose` configuration for one-command deployment.
- Add explainability features (e.g. highlight which resume sentences most influenced the similarity score).

## Troubleshooting

### `❌ Backend is not reachable. Start it with: uvicorn backend.main:app --reload`

The Streamlit UI cannot connect to the FastAPI server.

- Make sure the backend terminal is still running (`uvicorn backend.main:app --reload`).
- Verify it is listening on `http://127.0.0.1:8000` by opening the URL in a browser; you should see `{"status":"ok",...}`.
- Confirm no firewall or VPN is blocking port 8000.
- If you changed the host or port, update `API_BASE` in `frontend/app.py` accordingly.

### `ModuleNotFoundError: No module named 'backend'`

You are running `uvicorn` from inside the `backend/` directory or a wrong working directory.

- Run all commands from the **project root** (the folder that contains `backend/`, `frontend/`, `requirements.txt`).

### `uvicorn: command not found`

The virtual environment is not activated.

- Activate it: `.\.venv\Scripts\Activate.ps1` (Windows) or `source .venv/bin/activate` (macOS/Linux).
- Alternatively install uvicorn globally or use `python -m uvicorn backend.main:app --reload`.

### First `/rank` call is slow (10–30 seconds)

The sentence-transformer model is being downloaded and loaded on first use. Subsequent calls are significantly faster because the model is cached in process memory.

### `Failed to read <file>.pdf`

`pdf_parser` could not open the PDF (encrypted, corrupted, or scanned image-only). The function returns an empty string and the rest of the pipeline continues, but the affected resume will receive a very low score. Re-export the resume as a text-based PDF and try again.

### Port 8000 is already in use

Stop the other process, or change the port:

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
```

…and update `API_BASE` in `frontend/app.py` to the new port.

## License

This project is released under the **MIT License**.

```
MIT License

Copyright (c) 2026 Poridhi Labs

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
