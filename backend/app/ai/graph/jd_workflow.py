from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.app.ai.agents.jd_agent import analyze_job_description
from backend.app.schemas.job import JobRequirements
from backend.app.services.job_fetcher import fetch_job_content


class JobAnalysisState(TypedDict, total=False):
    source_url: str
    final_url: str
    job_description_text: str
    job_description_raw: str
    job_requirements: dict
    warnings: list[str]
    status: str


def receive_jd_node(state: JobAnalysisState) -> JobAnalysisState:
    if not state.get("source_url") and not state.get("job_description_text"):
        raise ValueError("Cần cung cấp URL hoặc nội dung JD")
    return {}


def fetch_content_node(state: JobAnalysisState) -> JobAnalysisState:
    if state.get("job_description_text"):
        return {"job_description_raw": state["job_description_text"]}
    content, final_url = fetch_job_content(state["source_url"])
    return {"job_description_raw": content, "final_url": final_url}


def extract_requirements_node(state: JobAnalysisState) -> JobAnalysisState:
    requirements, warnings = analyze_job_description(state["job_description_raw"])
    return {"job_requirements": requirements.model_dump(), "warnings": warnings}


def validate_requirements_node(state: JobAnalysisState) -> JobAnalysisState:
    JobRequirements.model_validate(state["job_requirements"])
    status = "review" if state.get("warnings") else "completed"
    return {"status": status}


def build_jd_graph():
    builder = StateGraph(JobAnalysisState)
    builder.add_node("receive_jd", receive_jd_node)
    builder.add_node("fetch_content", fetch_content_node)
    builder.add_node("extract_requirements", extract_requirements_node)
    builder.add_node("validate_requirements", validate_requirements_node)
    builder.add_edge(START, "receive_jd")
    builder.add_edge("receive_jd", "fetch_content")
    builder.add_edge("fetch_content", "extract_requirements")
    builder.add_edge("extract_requirements", "validate_requirements")
    builder.add_edge("validate_requirements", END)
    return builder.compile()


jd_graph = build_jd_graph()


def run_jd_analysis(
    source_url: str | None = None,
    job_description_text: str | None = None,
) -> JobAnalysisState:
    return jd_graph.invoke({
        "source_url": source_url,
        "job_description_text": job_description_text,
    })

