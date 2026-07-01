"""
Helper script that creates visually-rich placeholder PNGs for every
chapter of the README. Once you run the actual application and capture
real screenshots, replace the files in this folder with your own.

Usage:
    python docs/screenshots/generate_placeholders.py
"""
from pathlib import Path

OUT = Path(__file__).parent


def write_png(name: str, svg: str) -> None:
    """Write an SVG placeholder file. PNG conversion is optional."""
    (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")


# ---------- Chapter 1 ----------
write_png("ch1-uvicorn-running", """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="500">
  <rect width="100%" height="100%" fill="#0d1117"/>
  <text x="50%" y="20%" text-anchor="middle" fill="#58a6ff" font-family="Consolas" font-size="22">
    Uvicorn running on http://127.0.0.1:8000
  </text>
  <rect x="40" y="120" width="820" height="320" rx="8" fill="#161b22" stroke="#30363d"/>
  <text x="60" y="170" fill="#7ee787" font-family="Consolas" font-size="14">INFO:     Started server process [12345]</text>
  <text x="60" y="200" fill="#7ee787" font-family="Consolas" font-size="14">INFO:     Waiting for application startup.</text>
  <text x="60" y="230" fill="#7ee787" font-family="Consolas" font-size="14">INFO:     Application startup complete.</text>
  <text x="60" y="260" fill="#7ee787" font-family="Consolas" font-size="14">INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)</text>
  <text x="60" y="310" fill="#c9d1d9" font-family="Consolas" font-size="14">$ curl http://127.0.0.1:8000/</text>
  <text x="60" y="340" fill="#d2a8ff" font-family="Consolas" font-size="14">{&#x22;status&#x22;:&#x22;ok&#x22;,&#x22;message&#x22;:&#x22;Resume Screening API is running.&#x22;}</text>
  <text x="60" y="400" fill="#8b949e" font-family="sans-serif" font-size="13">
    Replace this placeholder with a real screenshot of uvicorn boot output + curl.
  </text>
</svg>""")


# ---------- Chapter 2 ----------
write_png("ch2-fastapi-docs", """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="500">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="50%" y="10%" text-anchor="middle" fill="#0b5fff" font-family="sans-serif" font-size="22">
    Interactive API docs at /docs
  </text>
  <rect x="40" y="80" width="820" height="380" rx="10" fill="#f6f8fa" stroke="#d0d7de"/>
  <text x="60" y="120" fill="#1f2328" font-family="sans-serif" font-size="16">GET /  Health check</text>
  <text x="60" y="150" fill="#1f2328" font-family="sans-serif" font-size="16">POST /upload-jd  Store the job description</text>
  <text x="60" y="180" fill="#1f2328" font-family="sans-serif" font-size="16">POST /upload-resumes  Upload PDFs</text>
  <text x="60" y="210" fill="#1f2328" font-family="sans-serif" font-size="16">POST /rank  Run the screening pipeline</text>
  <text x="60" y="240" fill="#1f2328" font-family="sans-serif" font-size="16">GET  /results  Last ranking output</text>
  <text x="60" y="270" fill="#1f2328" font-family="sans-serif" font-size="16">POST /reset  Start a new session</text>
  <text x="60" y="430" fill="#57606a" font-family="sans-serif" font-size="13">
    Replace with your own screenshot of http://127.0.0.1:8000/docs
  </text>
</svg>""")


# ---------- Chapter 3 ----------
write_png("ch3-embedder-loading", """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="500">
  <rect width="100%" height="100%" fill="#0d1117"/>
  <text x="50%" y="20%" text-anchor="middle" fill="#58a6ff" font-family="Consolas" font-size="22">
    First /rank call: sentence-transformer downloading all-MiniLM-L6-v2
  </text>
  <rect x="40" y="120" width="820" height="320" rx="8" fill="#161b22" stroke="#30363d"/>
  <text x="60" y="170" fill="#c9d1d9" font-family="Consolas" font-size="14">[embedder] Loading model: sentence-transformers/all-MiniLM-L6-v2</text>
  <text x="60" y="200" fill="#7ee787" font-family="Consolas" font-size="14">Batches: 100% 45/45 [00:12&lt;00:00,  3.50it/s]</text>
  <text x="60" y="230" fill="#7ee787" font-family="Consolas" font-size="14">384-dim normalized embeddings ready.</text>
  <text x="60" y="260" fill="#d2a8ff" font-family="Consolas" font-size="14">jd_vector.shape    = (384,)</text>
  <text x="60" y="290" fill="#d2a8ff" font-family="Consolas" font-size="14">resume_vectors.shape = (3, 384)</text>
  <text x="60" y="400" fill="#8b949e" font-family="sans-serif" font-size="13">
    Replace with your real screenshot of the first /rank terminal output.
  </text>
</svg>""")


# ---------- Chapter 4 ----------
write_png("ch4-faiss-search", """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="500">
  <rect width="100%" height="100%" fill="#0d1117"/>
  <text x="50%" y="12%" text-anchor="middle" fill="#58a6ff" font-family="sans-serif" font-size="22">
    FAISS IndexFlatIP - cosine similarity over normalized 384-dim vectors
  </text>
  <rect x="40" y="80" width="820" height="380" rx="8" fill="#161b22" stroke="#30363d"/>
  <text x="60" y="120" fill="#c9d1d9" font-family="Consolas" font-size="14">JD vector ----&gt; [0.012, -0.044, 0.081, ...]   (384 dims)</text>
  <text x="60" y="150" fill="#c9d1d9" font-family="Consolas" font-size="14">index.search(query, k=3)</text>
  <text x="60" y="190" fill="#7ee787" font-family="Consolas" font-size="14">score=0.7821  Alice Johnson        (alice.pdf)</text>
  <text x="60" y="220" fill="#7ee787" font-family="Consolas" font-size="14">score=0.6102  Bob Smith            (bob.pdf)</text>
  <text x="60" y="250" fill="#7ee787" font-family="Consolas" font-size="14">score=0.2930  Charlie Davis        (charlie.pdf)</text>
  <text x="60" y="430" fill="#8b949e" font-family="sans-serif" font-size="13">
    Replace with your real screenshot of FAISS search output.
  </text>
</svg>""")


# ---------- Chapter 5 ----------
write_png("ch5-skills-compare", """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="500">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="50%" y="12%" text-anchor="middle" fill="#0b5fff" font-family="sans-serif" font-size="22">
    Skill matching: matched vs missing vs extra
  </text>
  <rect x="40" y="80" width="820" height="380" rx="10" fill="#f6f8fa" stroke="#d0d7de"/>
  <text x="60" y="120" fill="#1a7f37" font-family="sans-serif" font-size="16">&#x2713; matched: python, fastapi, docker, aws, postgresql, nlp, machine learning, git</text>
  <text x="60" y="160" fill="#cf222e" font-family="sans-serif" font-size="16">&#x2717; missing: ci/cd</text>
  <text x="60" y="200" fill="#1f2328" font-family="sans-serif" font-size="16">&#x2795; extra:   kubernetes, tensorflow</text>
  <text x="60" y="260" fill="#0b5fff" font-family="sans-serif" font-size="18">match_ratio = 8 / 9 = 0.8889</text>
  <text x="60" y="430" fill="#57606a" font-family="sans-serif" font-size="13">
    Replace with your real screenshot showing matched/missing skills.
  </text>
</svg>""")


# ---------- Chapter 6 ----------
write_png("ch6-rank-output", """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="500">
  <rect width="100%" height="100%" fill="#0d1117"/>
  <text x="50%" y="12%" text-anchor="middle" fill="#58a6ff" font-family="Consolas" font-size="22">
    POST /rank response (FastAPI /docs)
  </text>
  <rect x="40" y="80" width="820" height="380" rx="8" fill="#161b22" stroke="#30363d"/>
  <text x="60" y="120" fill="#7ee787" font-family="Consolas" font-size="13">{</text>
  <text x="60" y="150" fill="#7ee787" font-family="Consolas" font-size="13">  "message": "Ranking complete.",</text>
  <text x="60" y="180" fill="#7ee787" font-family="Consolas" font-size="13">  "candidates": [</text>
  <text x="60" y="210" fill="#7ee787" font-family="Consolas" font-size="13">    {"rank": 1, "name": "Alice Johnson", "final_score": 0.8141},</text>
  <text x="60" y="240" fill="#7ee787" font-family="Consolas" font-size="13">    {"rank": 2, "name": "Bob Smith",     "final_score": 0.5560},</text>
  <text x="60" y="270" fill="#7ee787" font-family="Consolas" font-size="13">    {"rank": 3, "name": "Charlie Davis", "final_score": 0.2985}</text>
  <text x="60" y="300" fill="#7ee787" font-family="Consolas" font-size="13">  ]</text>
  <text x="60" y="330" fill="#7ee787" font-family="Consolas" font-size="13">}</text>
  <text x="60" y="430" fill="#8b949e" font-family="sans-serif" font-size="13">
    Replace with your real /rank JSON response.
  </text>
</svg>""")


# ---------- Chapter 7 ----------
write_png("ch7-streamlit-ui", """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="500">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="50%" y="12%" text-anchor="middle" fill="#ff4b4b" font-family="sans-serif" font-size="22">
    Streamlit UI - AI Resume Screening System
  </text>
  <rect x="40" y="80" width="820" height="380" rx="10" fill="#f6f8fa" stroke="#d0d7de"/>
  <text x="60" y="120" fill="#1a7f37" font-family="sans-serif" font-size="16">&#x2705; Backend is running</text>
  <text x="60" y="160" fill="#1f2328" font-family="sans-serif" font-size="16">1&#xFE0F;&#x20E3; Job Description ............... [saved]</text>
  <text x="60" y="190" fill="#1f2328" font-family="sans-serif" font-size="16">2&#xFE0F;&#x20E3; Upload Resumes (PDF) ........... 3 files parsed</text>
  <text x="60" y="220" fill="#1f2328" font-family="sans-serif" font-size="16">3&#xFE0F;&#x20E3; Rank Candidates &#x1F680; ......... Ranking complete!</text>
  <text x="60" y="270" fill="#0b5fff" font-family="sans-serif" font-size="16">| # | Candidate     | Final | Similarity | Skill |</text>
  <text x="60" y="300" fill="#1f2328" font-family="sans-serif" font-size="16">|---|---------------|-------|------------|-------|</text>
  <text x="60" y="330" fill="#1f2328" font-family="sans-serif" font-size="16">| 1 | Alice Johnson | 0.81  | 0.78       | 0.89  |</text>
  <text x="60" y="360" fill="#1f2328" font-family="sans-serif" font-size="16">| 2 | Bob Smith     | 0.56  | 0.61       | 0.44  |</text>
  <text x="60" y="430" fill="#57606a" font-family="sans-serif" font-size="13">
    Replace with your real browser screenshot of the Streamlit UI.
  </text>
</svg>""")


print("Placeholder SVGs written to:", OUT)
print("Replace each .svg with a real .png screenshot of your running app.")
