"""Build a Master Profile from user messages with the existing extraction logic."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend.app.ai.agents.profile_agent import extract_profile, assign_profile_metadata, validate_against_source, confirmation_evidence
from backend.app.db.checkpoints import get_checkpointer
from backend.app.db.profile_repository import save_master_profile
from backend.app.schemas.profile import MasterProfile
from backend.app.schemas.profile_update import SessionAction


class BuildState(TypedDict, total=False):
    session_id: str
    mode: str
    status: str
    action_id: str
    question: str
    messages: list[dict]
    source: str
    profile: dict
    profile_id: str
    warnings: list[str]
    approved: bool
    finished: bool


def collect(state: BuildState):
    action = SessionAction.model_validate(interrupt({"action_id": state["action_id"], "question": state["question"]}))
    if action.decision == "finish":
        return {"status": "cancelled", "finished": True}
    messages = [*state.get("messages", []), {"role": "user", "content": action.message}]
    source = "\n\n".join(item["content"] for item in messages if item["role"] == "user")
    return {"messages": messages, "source": source}


def extract(state: BuildState):
    profile = extract_profile(state["source"])
    warnings = validate_against_source(profile, state["source"])
    return {"profile": profile.model_dump(), "warnings": warnings, "status": "pending_approval",
            "action_id": f"{state['session_id']}:{len(state['messages'])}:approve"}


def review(state: BuildState):
    action = SessionAction.model_validate(interrupt({"action_id": state["action_id"], "profile": state["profile"], "warnings": state["warnings"]}))
    if action.decision == "approve":
        profile = assign_profile_metadata(action.profile or MasterProfile.model_validate(state["profile"]), preserve_ids=True)
        return {"profile": profile.model_dump(), "approved": True}
    if action.decision == "finish":
        return {"finished": True, "approved": False, "status": "cancelled"}
    return {"approved": False, "status": "pending_answer", "action_id": f"{state['session_id']}:{len(state['messages'])}:message",
            "question": "Bạn muốn bổ sung hoặc đính chính thông tin nào? Chỉ nêu kinh nghiệm và thông tin có thật."}


def save(state: BuildState):
    profile = MasterProfile.model_validate(state["profile"])
    # Deterministic ID: resuming after a crash cannot create a second profile.
    from backend.app.db import profile_repository
    existing = profile_repository.load_profile_record(state["session_id"], profile_repository.DEFAULT_STORAGE_DIR)
    if existing is None:
        save_master_profile(state["session_id"], profile, profile_repository.DEFAULT_STORAGE_DIR, source_text=state["source"], source_filename="chat",
                            evidence=confirmation_evidence(profile, state["source"], state["session_id"]))
    elif existing.profile != profile:
        raise ValueError("Phiên đã lưu hồ sơ khác; không ghi đè")
    return {"profile_id": state["session_id"], "status": "completed"}


def build_chat_graph(checkpointer=None):
    graph = StateGraph(BuildState)
    for name, function in (("collect", collect), ("extract", extract), ("review", review), ("save", save)):
        graph.add_node(name, function)
    graph.add_edge(START, "collect")
    graph.add_conditional_edges("collect", lambda state: END if state.get("finished") else "extract")
    graph.add_edge("extract", "review")
    graph.add_conditional_edges("review", lambda state: END if state.get("finished") else "save" if state.get("approved") else "collect")
    graph.add_edge("save", END)
    return graph.compile(checkpointer=checkpointer if checkpointer is not None else get_checkpointer())


chat_graph = build_chat_graph()
