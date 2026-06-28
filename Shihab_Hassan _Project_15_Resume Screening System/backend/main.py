"""
FastAPI backend for the Resume Screening System.

Endpoints:
    POST /upload-jd        - upload a job description (text)
    POST /upload-resumes   - upload one or more resume PDFs
    POST /rank             - run the full screening pipeline
    GET  /results          - fetch the most recent ranking
    POST /reset            - clear all stored data (start a new session)
"""
from __future__ import annotations

from typing import List

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import RESUME_DIR
from .embedder import Embedder
from .faiss_index import FaissIndex
from .pdf_parser import parse_resume
from .ranker import rank_candidates
from .skill_extractor import SkillExtractor

# ---------- App & State ----------
app = FastAPI(
    title="Resume Screening System",
    description="Upload a job description and resumes, get ranked candidates.",
    version="1.0.0",
)

# Streamlit runs in the browser - CORS is required
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory state for a single recruiter session.
# In production you would persist this in Redis/Postgres.
state: dict = {
    "jd_text": None,
    "resumes": [],   # list of {name, text, file}
    "results": None, # last ranking output
}

# Long-lived ML components (model is heavy - load once)
embedder = Embedder()
skill_extractor = SkillExtractor()
index = FaissIndex()


# ---------- Helpers ----------
def _save_upload(upload: UploadFile, dest_dir) -> str:
    """Persist an uploaded file to disk and return its saved path."""
    file_path = dest_dir / upload.filename
    with open(file_path, "wb") as f:
        f.write(upload.file.read())
    return str(file_path)


# ---------- Endpoints ----------
@app.get("/")
def health_check() -> dict:
    """Simple health check."""
    return {"status": "ok", "message": "Resume Screening API is running."}


@app.post("/upload-jd")
async def upload_jd(jd_text: str = Form(...)) -> dict:
    """
    Store the job description text.
    Accepts plain text from a form field so the UI can either type
    or paste a JD.
    """
    if not jd_text.strip():
        raise HTTPException(status_code=400, detail="Job description is empty.")
    state["jd_text"] = jd_text.strip()
    return {"message": "Job description saved.", "length": len(state["jd_text"])}


@app.post("/upload-resumes")
async def upload_resumes(files: List[UploadFile] = File(...)) -> dict:
    """
    Accept one or more PDF resume files, parse them, and store the
    extracted text in memory.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    saved = []
    for upload in files:
        if not upload.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"{upload.filename} is not a PDF.",
            )
        path = _save_upload(upload, RESUME_DIR)
        parsed = parse_resume(path)
        state["resumes"].append(
            {
                "name": parsed["name"],
                "text": parsed["text"],
                "file": upload.filename,
            }
        )
        saved.append({"filename": upload.filename, "candidate": parsed["name"]})

    return {"message": f"Parsed {len(saved)} resume(s).", "resumes": saved}


@app.post("/rank")
def rank() -> dict:
    """
    Run the full pipeline:
        1. embed JD + resumes
        2. add resume vectors to FAISS
        3. search with JD vector
        4. extract skills from each resume
        5. combine and rank
    """
    if not state["jd_text"]:
        raise HTTPException(status_code=400, detail="Upload a job description first.")
    if not state["resumes"]:
        raise HTTPException(status_code=400, detail="Upload at least one resume first.")

    # 1. Embed JD and all resumes
    jd_vector = embedder.embed(state["jd_text"])
    resume_texts = [r["text"] for r in state["resumes"]]
    resume_vectors = embedder.embed_batch(resume_texts)

    # 2 & 3. FAISS
    index.reset()
    index.add(resume_vectors, state["resumes"])
    faiss_hits = index.search(jd_vector)

    # 4. Skills
    skill_reports = {
        r["name"]: skill_extractor.compare(state["jd_text"], r["text"])
        for r in state["resumes"]
    }

    # 5. Rank
    ranked = rank_candidates(faiss_hits, skill_reports)
    state["results"] = ranked

    return {
        "message": "Ranking complete.",
        "candidates": ranked,
        "jd_skills": skill_extractor.extract(state["jd_text"]),
    }


@app.get("/results")
def get_results() -> dict:
    """Return the most recent ranking."""
    if state["results"] is None:
        raise HTTPException(status_code=404, detail="No ranking has been run yet.")
    return {"candidates": state["results"]}


@app.post("/reset")
def reset() -> dict:
    """Clear all stored data so a new session can start."""
    state["jd_text"] = None
    state["resumes"] = []
    state["results"] = None
    index.reset()
    return {"message": "Session reset."}
