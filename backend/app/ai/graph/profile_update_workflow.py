"""Agent 4: ask -> exact-quote draft -> approval -> immutable revision -> next."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend.app.ai.agents.profile_update_agent import ask_about_gap, draft_update
from backend.app.db import profile_repository, workflow_repository as records
from backend.app.db.checkpoints import get_checkpointer
from backend.app.db.profile_revision_repository import commit_revision, current_revision, RevisionConflict
from backend.app.schemas.profile_update import SessionAction


class UpdateState(TypedDict, total=False):
    session_id: str
    mode: str
    profile_id: str
    root_id: str
    posting_id: str
    queue: list[dict]
    index: int
    status: str
    action_id: str
    question: str
    answer: dict
    proposal: dict | None
    changed_paths: list[str]
    messages: list[dict]
    warnings: list[str]
    attempt: int
    retry_question: bool


def generate_question(state: UpdateState):
    target = state["queue"][state["index"]]
    question = ask_about_gap(target)
    attempt = state.get("attempt", 0) + 1
    return {"question": question, "action_id": f"{state['session_id']}:{state['index']}:{attempt}:answer", "attempt": attempt, "retry_question": False,
            "status": "pending_answer", "proposal": None, "changed_paths": [],
            "messages": [*state.get("messages", []), {"role": "assistant", "content": question}]}


def receive_answer(state: UpdateState):
    answer = SessionAction.model_validate(interrupt({"action_id": state["action_id"], "question": state["question"]}))
    return {"answer": answer.model_dump(), "messages": [*state["messages"], {"role": "user", "content": answer.message or answer.decision}]}


def propose(state: UpdateState):
    answer = SessionAction.model_validate(state["answer"])
    target = state["queue"][state["index"]]
    if answer.decision == "no":
        records.put("answers", records.answer_key(state["root_id"], target), {"decision": "no", "target": target, "session_id": state["session_id"]})
        return {"proposal": None}
    if answer.decision != "yes":
        return {"proposal": None}
    if current_revision(state["profile_id"]) != state["profile_id"]:
        raise RevisionConflict("Hồ sơ đã thay đổi; tải revision mới để tránh ghi đè")
    record = profile_repository.load_profile_record(state["profile_id"], profile_repository.DEFAULT_STORAGE_DIR)
    try:
        proposed, paths = draft_update(record.profile, target, answer)
    except ValueError as error:
        return {"proposal": None, "retry_question": True, "warnings": [str(error)]}
    return {"proposal": proposed.model_dump(), "changed_paths": paths,
            "action_id": f"{state['session_id']}:{state['index']}:{state['attempt']}:approve", "status": "pending_approval"}


def approve(state: UpdateState):
    decision = SessionAction.model_validate(interrupt({"action_id": state["action_id"], "proposed_profile": state["proposal"], "changed_paths": state["changed_paths"]}))
    if decision.decision != "approve":
        return {"proposal": None}
    from backend.app.schemas.profile import MasterProfile
    answer = SessionAction.model_validate(state["answer"])
    revision = commit_revision(state["profile_id"], MasterProfile.model_validate(state["proposal"]),
                               session_id=state["session_id"], action_id=state["action_id"],
                               changed_paths=state["changed_paths"], quote=answer.message)
    target = state["queue"][state["index"]]
    records.put("answers", records.answer_key(state["root_id"], target), {"decision": "yes", "target": target, "session_id": state["session_id"], "profile_id": revision})
    return {"profile_id": revision, "proposal": None,
            "messages": [*state["messages"], {"role": "assistant", "content": "Đã lưu revision sau xác nhận của bạn. Hồ sơ gốc được giữ nguyên."}]}


def advance(state: UpdateState):
    index = state["index"] + 1
    finished = state["answer"]["decision"] == "finish" or index >= len(state["queue"])
    return {"index": index, "status": "completed" if finished else "running", "proposal": None, "changed_paths": []}


def build_update_graph(checkpointer=None):
    graph = StateGraph(UpdateState)
    for name, function in (("question", generate_question), ("answer", receive_answer), ("propose", propose), ("approve", approve), ("next", advance)):
        graph.add_node(name, function)
    graph.add_edge(START, "question")
    graph.add_edge("question", "answer")
    graph.add_edge("answer", "propose")
    graph.add_conditional_edges("propose", lambda state: "question" if state.get("retry_question") else "approve" if state.get("proposal") else "next")
    graph.add_edge("approve", "next")
    graph.add_conditional_edges("next", lambda state: END if state["status"] == "completed" else "question")
    return graph.compile(checkpointer=checkpointer if checkpointer is not None else get_checkpointer())


update_graph = build_update_graph()
