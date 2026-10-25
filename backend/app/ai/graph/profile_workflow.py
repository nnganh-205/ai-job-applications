from typing import TypedDict

from backend.app.db.checkpoints import get_checkpointer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from backend.app.ai.agents.profile_agent import (
    assign_profile_metadata,
    build_source_evidence,
    confirmation_evidence,
    extract_profile,
    validate_against_source,
)
from backend.app.schemas.profile import MasterProfile
from backend.app.services.document_reader import read_cv
from backend.app.db.profile_repository import save_master_profile


class ProfileState(TypedDict, total=False):
    thread_id: str
    filename: str
    file_bytes: bytes
    resume_text: str
    profile: dict
    warnings: list[str]
    status: str
    evidence: list[dict]


def parse_cv_node(state: ProfileState) -> ProfileState:
    return {"resume_text": read_cv(state["filename"], state["file_bytes"])}


def extract_profile_node(state: ProfileState) -> ProfileState:
    profile = extract_profile(state["resume_text"])
    return {"profile": profile.model_dump()}


def validate_profile_node(state: ProfileState) -> ProfileState:
    profile = MasterProfile.model_validate(state["profile"])
    warnings = validate_against_source(profile, state["resume_text"])
    evidence = build_source_evidence(profile, state["resume_text"], state["thread_id"])
    return {"warnings": warnings, "evidence": [item.model_dump() for item in evidence], "status": "pending_confirmation"}


def human_confirmation_node(state: ProfileState) -> ProfileState:
    # Graph dừng tại đây; API confirm sẽ resume bằng profile người dùng đã sửa.
    confirmed_profile = interrupt({"profile": state["profile"], "warnings": state["warnings"], "evidence": state.get("evidence", [])})
    profile = assign_profile_metadata(MasterProfile.model_validate(confirmed_profile), preserve_ids=True)
    evidence = confirmation_evidence(profile, state["resume_text"], state["thread_id"])
    warnings = validate_against_source(profile, state["resume_text"])
    return {"profile": profile.model_dump(), "evidence": [item.model_dump() for item in evidence], "warnings": warnings, "status": "confirmed"}


def save_profile_node(state: ProfileState) -> ProfileState:
    # thread_id được LangGraph dùng để resume và được API đưa vào state khi xác nhận.
    save_master_profile(
        state["thread_id"], MasterProfile.model_validate(state["profile"]),
        evidence=state.get("evidence", []), warnings=state.get("warnings", []),
        source_text=state["resume_text"], source_filename=state["filename"],
    )
    return {"status": "confirmed"}


def build_profile_graph():
    builder = StateGraph(ProfileState)
    builder.add_node("parse_cv", parse_cv_node)
    builder.add_node("extract_profile", extract_profile_node)
    builder.add_node("validate_profile", validate_profile_node)
    builder.add_node("human_confirmation", human_confirmation_node)
    builder.add_node("save_profile", save_profile_node)
    builder.add_edge(START, "parse_cv")
    builder.add_edge("parse_cv", "extract_profile")
    builder.add_edge("extract_profile", "validate_profile")
    builder.add_edge("validate_profile", "human_confirmation")
    builder.add_edge("human_confirmation", "save_profile")
    builder.add_edge("save_profile", END)
    return builder.compile(checkpointer=get_checkpointer())


profile_graph = build_profile_graph()


def start_extraction(filename: str, file_bytes: bytes, thread_id: str) -> ProfileState:
    config = {"configurable": {"thread_id": thread_id}}
    state = {"filename": filename, "file_bytes": file_bytes, "thread_id": thread_id}
    profile_graph.invoke(state, config=config)
    return profile_graph.get_state(config).values


def confirm_extraction(thread_id: str, profile: MasterProfile) -> ProfileState:
    config = {"configurable": {"thread_id": thread_id}}
    current_state = profile_graph.get_state(config).values
    if not current_state or current_state.get("status") != "pending_confirmation":
        raise ValueError("Không tìm thấy phiên trích xuất đang chờ xác nhận")
    result = profile_graph.invoke(Command(resume=profile.model_dump()), config=config)
    return result

