"""LangGraph pipeline that produces a TailoredCV from a Profile and JobOffer.

Flow:
    start -> gap_node -> tailor_node -> validator_node
    validator_node -> END (when score OK or max iterations reached)
                    -> tailor_node (with feedback) otherwise
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from cv_generator.agents.gap_analyzer import analyze_gap
from cv_generator.agents.tailor import tailor_cv
from cv_generator.agents.validator import validate
from cv_generator.config import get_settings
from cv_generator.graph.state import GenerationState
from cv_generator.models import JobOffer, Profile, TailoredCV

logger = logging.getLogger(__name__)


def _gap_node(state: GenerationState) -> GenerationState:
    logger.info("Pipeline node=gap")
    profile = state["profile"]
    job = state["job"]
    return {"gap": analyze_gap(profile, job), "iteration": state.get("iteration", 0)}


def _tailor_node(state: GenerationState) -> GenerationState:
    settings = get_settings()
    language = state.get("language") or settings.app_language
    iteration = state.get("iteration", 0)
    logger.info("Pipeline node=tailor iteration=%d language=%s", iteration, language)
    cv = tailor_cv(
        profile=state["profile"],
        job=state["job"],
        gap=state.get("gap", {}),
        feedback=state.get("feedback", ""),
        language=language,
    )
    return {"tailored": cv, "iteration": iteration + 1}


def _validator_node(state: GenerationState) -> GenerationState:
    logger.info("Pipeline node=validator iteration=%d", state.get("iteration", 0))
    score, feedback, cv = validate(
        profile=state["profile"], job=state["job"], cv=state["tailored"]
    )
    return {"tailored": cv, "score": score, "feedback": feedback}


def _route_after_validation(state: GenerationState) -> str:
    settings = get_settings()
    score = state.get("score", 0)
    iteration = state.get("iteration", 0)
    if score >= settings.min_match_score or iteration >= settings.max_tailor_iterations:
        logger.info("Pipeline done score=%d iteration=%d", score, iteration)
        return "done"
    logger.info("Pipeline retry score=%d iteration=%d", score, iteration)
    return "retry"


def build_graph():
    graph = StateGraph(GenerationState)
    graph.add_node("gap", _gap_node)
    graph.add_node("tailor", _tailor_node)
    graph.add_node("validator", _validator_node)

    graph.set_entry_point("gap")
    graph.add_edge("gap", "tailor")
    graph.add_edge("tailor", "validator")
    graph.add_conditional_edges(
        "validator",
        _route_after_validation,
        {"retry": "tailor", "done": END},
    )
    return graph.compile()


def generate_cv(
    profile: Profile,
    job: JobOffer,
    *,
    language: str | None = None,
) -> TailoredCV:
    """Run the pipeline synchronously and return the final TailoredCV."""
    settings = get_settings()
    language = language or settings.app_language
    logger.info("Starting CV generation language=%s", language)
    graph = build_graph()
    final_state = graph.invoke(
        {
            "profile": profile,
            "job": job,
            "iteration": 0,
            "language": language,
        }
    )
    logger.info(
        "CV generation finished score=%s language=%s",
        final_state.get("score"),
        language,
    )
    return final_state["tailored"]
