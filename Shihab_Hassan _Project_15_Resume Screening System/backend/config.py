"""
Configuration module.
Centralizes all paths, model names, and tunable hyperparameters
so the rest of the codebase stays clean and easy to modify.
"""
from pathlib import Path

# ---------- Project Paths ----------
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
RESUME_DIR = UPLOAD_DIR / "resumes"
SKILLS_FILE = BASE_DIR / "data" / "skills.json"

# Make sure required folders exist (idempotent)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESUME_DIR.mkdir(parents=True, exist_ok=True)

# ---------- ML Model ----------
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # Output dimension of all-MiniLM-L6-v2

# ---------- Ranking Weights ----------
# Final score = SIMILARITY_WEIGHT * similarity + SKILL_WEIGHT * skill_match
SIMILARITY_WEIGHT = 0.7
SKILL_WEIGHT = 0.3

# ---------- API Settings ----------
API_HOST = "127.0.0.1"
API_PORT = 8000
