"""Pydantic models shared across the application."""

from cv_generator.models.board_offer import BOARD_LABELS, BoardOffer, BoardSource
from cv_generator.models.cv import TailoredCV, TailoredExperience
from cv_generator.models.job import JobOffer
from cv_generator.models.profile import Education, Experience, Profile

__all__ = [
    "BOARD_LABELS",
    "BoardOffer",
    "BoardSource",
    "Education",
    "Experience",
    "JobOffer",
    "Profile",
    "TailoredCV",
    "TailoredExperience",
]
