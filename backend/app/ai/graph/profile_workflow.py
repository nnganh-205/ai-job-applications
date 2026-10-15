from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from backend.app.ai.agents.profile_agent import extract_profile, validate_against_source
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


def parse_cv_node(state: ProfileState) -> ProfileState:
    return {"resume_text": read_cv(state["filename"], state["file_bytes"])}


def extract_profile_node(state: ProfileState) -> ProfileState:
    profile = extract_profile(state["resume_text"])
    return {"profile": profile.model_dump()}


def validate_profile_node(state: ProfileState) -> ProfileState:
    profile = MasterProfile.model_validate(state["profile"])
    warnings = validate_against_source(profile, state["resume_text"])
    return {"warnings": warnings, "status": "pending_confirmation"}


def human_confirmation_node(state: ProfileState) -> ProfileState:
    # Graph dừng tại đây; API confirm sẽ resume bằng profile người dùng đã sửa.
    confirmed_profile = interrupt({"profile": state["profile"], "warnings": state["warnings"]})
    profile = MasterProfile.model_validate(confirmed_profile)
    return {"profile": profile.model_dump(), "status": "confirmed"}


def save_profile_node(state: ProfileState) -> ProfileState:
    # thread_id được LangGraph dùng để resume và được API đưa vào state khi xác nhận.
    save_master_profile(state["thread_id"], MasterProfile.model_validate(state["profile"]))
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
    return builder.compile(checkpointer=MemorySaver())


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

