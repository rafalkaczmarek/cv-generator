"""Shared LangGraph state passed between agent nodes."""

from __future__ import annotations

from typing import TypedDict

from cv_generator.models import JobOffer, Profile, TailoredCV


class GapAnalysis(TypedDict, total=False):
    matched_skills: list[str]
    missing_skills: list[str]
    relevant_experiences: list[int]
    emphasis_notes: list[str]


class GenerationState(TypedDict, total=False):
    profile: Profile
    job: JobOffer
    gap: GapAnalysis
    tailored: TailoredCV
    iteration: int
    score: int
    feedback: str
    done: bool
