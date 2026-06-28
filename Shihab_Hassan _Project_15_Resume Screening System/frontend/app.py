"""
Streamlit Frontend for the Resume Screening System.

Run with:
    streamlit run frontend/app.py
Make sure the FastAPI backend is running on http://127.0.0.1:8000 first.
"""
import requests
import streamlit as st

# ---------- Config ----------
API_BASE = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="AI Resume Screener",
    page_icon="📄",
    layout="wide",
)

# ---------- Helpers ----------
def api_post(path: str, **kwargs):
    try:
        return requests.post(f"{API_BASE}{path}", timeout=300, **kwargs)
    except requests.exceptions.RequestException as exc:
        st.error(f"API call failed: {exc}")
        return None


def api_get(path: str):
    try:
        return requests.get(f"{API_BASE}{path}", timeout=60)
    except requests.exceptions.RequestException as exc:
        st.error(f"API call failed: {exc}")
        return None


# ---------- UI ----------
st.title("📄 AI Resume Screening System")
st.caption("Upload a job description and resumes — get ranked candidates instantly.")

# Health check
health = api_get("/")
if health and health.status_code == 200:
    st.success("✅ Backend is running")
else:
    st.error("❌ Backend is not reachable. Start it with: `uvicorn backend.main:app --reload`")
    st.stop()

# ----- Step 1: Job Description -----
st.header("1️⃣ Job Description")
jd_text = st.text_area(
    "Paste the job description below",
    height=220,
    placeholder="e.g. We are hiring a Senior Python Engineer with experience in NLP, FastAPI, AWS...",
)

if st.button("💾 Save Job Description"):
    if not jd_text.strip():
        st.warning("Please paste a job description first.")
    else:
        res = api_post("/upload-jd", data={"jd_text": jd_text})
        if res and res.status_code == 200:
            st.success(res.json()["message"])

st.divider()

# ----- Step 2: Resumes -----
st.header("2️⃣ Upload Resumes (PDF)")
uploaded_files = st.file_uploader(
    "Upload one or more PDF resumes",
    type=["pdf"],
    accept_multiple_files=True,
)

if st.button("📤 Upload & Parse Resumes"):
    if not uploaded_files:
        st.warning("Please select at least one PDF.")
    else:
        files = [("files", (f.name, f.getvalue(), "application/pdf")) for f in uploaded_files]
        res = api_post("/upload-resumes", files=files)
        if res and res.status_code == 200:
            data = res.json()
            st.success(data["message"])
            for r in data["resumes"]:
                st.write(f"  • **{r['filename']}** → {r['candidate']}")

st.divider()

# ----- Step 3: Rank -----
st.header("3️⃣ Rank Candidates")
if st.button("🚀 Run Screening"):
    with st.spinner("Analyzing resumes... (this may take 10-30s on first run while the model loads)"):
        res = api_post("/rank")
    if res and res.status_code == 200:
        st.session_state["results"] = res.json()
        st.success("Ranking complete!")
    elif res:
        st.error(res.json().get("detail", "Ranking failed."))

# ----- Results -----
if "results" in st.session_state:
    data = st.session_state["results"]
    candidates = data.get("candidates", [])

    st.divider()
    st.header("🏆 Ranked Candidates")

    # Summary table
    rows = [
        {
            "Rank": c["rank"],
            "Candidate": c["name"],
            "Final Score": c["final_score"],
            "Similarity": c["similarity_score"],
            "Skill Match": c["skill_match_ratio"],
            "Matched Skills": len(c["matched_skills"]),
            "Missing Skills": len(c["missing_skills"]),
        }
        for c in candidates
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # Detail expanders
    st.subheader("Candidate Details")
    for c in candidates:
        with st.expander(f"#{c['rank']}  •  {c['name']}  (score: {c['final_score']})"):
            col1, col2, col3 = st.columns(3)
            col1.metric("Similarity", f"{c['similarity_score']:.2%}")
            col2.metric("Skill Match", f"{c['skill_match_ratio']:.2%}")
            col3.metric("Final Score", f"{c['final_score']:.2%}")

            st.markdown("**✅ Matched Skills**")
            st.write(", ".join(c["matched_skills"]) if c["matched_skills"] else "—")

            st.markdown("**❌ Missing Skills**")
            st.write(", ".join(c["missing_skills"]) if c["missing_skills"] else "—")

            if c.get("extra_skills"):
                st.markdown("**➕ Extra Skills (not in JD)**")
                st.write(", ".join(c["extra_skills"]))
