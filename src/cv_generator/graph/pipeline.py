"""LangGraph pipeline that produces a TailoredCV from a Profile and JobOffer.

Flow:
    start -> gap_node -> tailor_node -> validator_node
    validator_node -> END (when score OK or max iterations reached)
                    -> tailor_node (with feedback) otherwise
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from cv_generator.agents.gap_analyzer import analyze_gap
from cv_generator.agents.tailor import tailor_cv
from cv_generator.agents.validator import validate
from cv_generator.config import get_settings
from cv_generator.graph.state import GenerationState
from cv_generator.models import JobOffer, Profile, TailoredCV


def _gap_node(state: GenerationState) -> GenerationState:
    profile = state["profile"]
    job = state["job"]
    return {"gap": analyze_gap(profile, job), "iteration": state.get("iteration", 0)}


def _tailor_node(state: GenerationState) -> GenerationState:
    settings = get_settings()
    cv = tailor_cv(
        profile=state["profile"],
        job=state["job"],
        gap=state.get("gap", {}),
        feedback=state.get("feedback", ""),
        language=settings.app_language,
    )
    return {"tailored": cv, "iteration": state.get("iteration", 0) + 1}


def _validator_node(state: GenerationState) -> GenerationState:
    score, feedback, cv = validate(
        profile=state["profile"], job=state["job"], cv=state["tailored"]
    )
    return {"tailored": cv, "score": score, "feedback": feedback}


def _route_after_validation(state: GenerationState) -> str:
    settings = get_settings()
    score = state.get("score", 0)
    iteration = state.get("iteration", 0)
    if score >= settings.min_match_score or iteration >= settings.max_tailor_iterations:
        return "done"
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


def generate_cv(profile: Profile, job: JobOffer) -> TailoredCV:
    """Run the pipeline synchronously and return the final TailoredCV."""
    graph = build_graph()
    final_state = graph.invoke({"profile": profile, "job": job, "iteration": 0})
    return final_state["tailored"]
