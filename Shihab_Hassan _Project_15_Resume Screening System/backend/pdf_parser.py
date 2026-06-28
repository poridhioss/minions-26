"""
PDF Parser module.
Uses PyMuPDF (fitz) to extract raw text from resume PDFs.
Falls back gracefully if a file is encrypted, empty, or corrupted.
"""
import re
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """
    Read a PDF file and return its full text content.

    Returns an empty string if the PDF cannot be read so that the
    rest of the pipeline can continue without crashing.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    text_chunks: list[str] = []
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                page_text = page.get_text("text")
                if page_text:
                    text_chunks.append(page_text)
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[pdf_parser] Failed to read {pdf_path.name}: {exc}")
        return ""

    return "\n".join(text_chunks).strip()


def clean_text(text: str) -> str:
    """
    Normalize whitespace and strip non-printable characters so the
    embedding model receives clean input.
    """
    if not text:
        return ""
    # Replace any whitespace (newlines, tabs, multiple spaces) with a single space
    text = re.sub(r"\s+", " ", text)
    # Remove control characters
    text = re.sub(r"[^\x20-\x7E]", " ", text)
    return text.strip()


def extract_candidate_name(text: str, fallback: str = "Unknown Candidate") -> str:
    """
    Heuristic to pull a candidate's name from the first lines of the resume.
    Most resumes start with the candidate's full name as the first non-empty line.
    """
    if not text:
        return fallback

    # Look at the first 8 non-empty lines
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:8]
    for line in lines:
        # Skip lines that contain an email or phone number
        if "@" in line or re.search(r"\d{3,}", line):
            continue
        # Accept lines that look like a name (2-4 words, capitalized, alphabetic)
        words = line.split()
        if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
            return line

    return fallback


def parse_resume(pdf_path: str | Path) -> dict:
    """
    Convenience helper: parse a resume PDF and return both the
    cleaned text and the extracted candidate name.
    """
    raw = extract_text_from_pdf(pdf_path)
    cleaned = clean_text(raw)
    name = extract_candidate_name(raw, fallback=Path(pdf_path).stem)
    return {"name": name, "text": cleaned}
