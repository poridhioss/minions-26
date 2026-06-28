"""
Ranker module.
Combines embedding-based similarity (from FAISS) with skill-match ratio
to produce a final ranking of candidates.

Final score = w1 * similarity + w2 * skill_match
"""
from .config import SIMILARITY_WEIGHT, SKILL_WEIGHT


def rank_candidates(
    faiss_results: list[dict],
    skill_reports: dict[str, dict],
) -> list[dict]:
    """
    Args:
        faiss_results:  Output of FaissIndex.search - each item has 'name', 'score', etc.
        skill_reports:  Dict keyed by candidate name -> {matched, missing, match_ratio}

    Returns:
        Sorted list (desc by final_score) of dicts with all the info a
        recruiter wants to see.
    """
    combined: list[dict] = []
    for result in faiss_results:
        name = result.get("name", "Unknown")
        similarity = float(result.get("score", 0.0))
        skill_info = skill_reports.get(name, {"matched": [], "missing": [], "match_ratio": 0.0})
        skill_ratio = float(skill_info.get("match_ratio", 0.0))

        final_score = SIMILARITY_WEIGHT * similarity + SKILL_WEIGHT * skill_ratio

        combined.append(
            {
                "name": name,
                "file": result.get("file"),
                "similarity_score": round(similarity, 4),
                "skill_match_ratio": round(skill_ratio, 4),
                "final_score": round(final_score, 4),
                "matched_skills": skill_info.get("matched", []),
                "missing_skills": skill_info.get("missing", []),
                "extra_skills": skill_info.get("extra", []),
            }
        )

    # Highest final_score first
    combined.sort(key=lambda x: x["final_score"], reverse=True)
    # Add rank field
    for i, item in enumerate(combined, start=1):
        item["rank"] = i
    return combined
