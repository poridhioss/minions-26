"""
Skill extractor module.
Loads the skills database and finds which skills are present or absent
in a given piece of text (job description or resume).

Matching is case-insensitive and uses whole-word boundary regex so that
"go" doesn't match "google" or "rust" doesn't match "trust".
"""
import json
import re
from pathlib import Path

from .config import SKILLS_FILE


class SkillExtractor:
    def __init__(self, skills_file: Path = SKILLS_FILE) -> None:
        self.skills_by_category: dict[str, list[str]] = self._load_skills(skills_file)
        # Flat list of all skills, lower-cased, sorted longest-first
        # (so "machine learning" matches before "learning")
        self.all_skills: list[str] = sorted(
            {s.lower() for skills in self.skills_by_category.values() for s in skills},
            key=len,
            reverse=True,
        )
        # Pre-compile one regex per skill for fast matching
        self._skill_regex = {
            skill: re.compile(rf"\b{re.escape(skill)}\b", flags=re.IGNORECASE)
            for skill in self.all_skills
        }

    @staticmethod
    def _load_skills(path: Path) -> dict[str, list[str]]:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def extract(self, text: str) -> list[str]:
        """Return the unique skills (lower-cased) found in the text."""
        if not text:
            return []
        found: list[str] = []
        for skill, pattern in self._skill_regex.items():
            if pattern.search(text):
                found.append(skill)
        return found

    def compare(self, jd_text: str, resume_text: str) -> dict:
        """
        Compare the skills required in a job description against a resume.
        Returns matched, missing, and a match ratio in [0, 1].
        """
        jd_skills = set(self.extract(jd_text))
        resume_skills = set(self.extract(resume_text))

        if not jd_skills:
            return {
                "matched": [],
                "missing": [],
                "extra": list(resume_skills),
                "match_ratio": 0.0,
            }

        matched = sorted(jd_skills & resume_skills)
        missing = sorted(jd_skills - resume_skills)
        extra = sorted(resume_skills - jd_skills)
        match_ratio = len(matched) / len(jd_skills)

        return {
            "matched": matched,
            "missing": missing,
            "extra": extra,
            "match_ratio": round(match_ratio, 4),
        }
