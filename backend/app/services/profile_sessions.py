"""API orchestration for Agent 4 and profile chat; no CV facts are silently saved."""

from threading import RLock
from uuid import uuid4

from langgraph.types import Command

from backend.app.ai.graph.profile_chat_workflow import chat_graph
from backend.app.ai.graph.profile_update_workflow import update_graph
from backend.app.db import database, profile_repository, workflow_repository as records
from backend.app.db.profile_revision_repository import current_revision, root_id, RevisionConflict
from backend.app.schemas.profile_update import SessionAction, SessionView, UpdateStart
from backend.app.services.dashboard_service import evaluate_job
from backend.app.services.profile_answers import requirement_targets

_session_lock = RLock()


def graph_for(session_id):
    index = records.get("sessions", session_id)
    if index is None:
        raise LookupError("Không tìm thấy phiên chat")
    return (update_graph if index["mode"] == "update" else chat_graph), {"configurable": {"thread_id": session_id}}


def view_session(session_id: str) -> SessionView:
    graph, config = graph_for(session_id)
    state = graph.get_state(config).values
    if not state:
        raise LookupError("Không có checkpoint cho phiên này; kiểm tra cấu hình persistence")
    finished = state.get("status") in {"completed", "cancelled"}
    index = state.get("index", 0)
    target = state["queue"][index] if state.get("queue") and index < len(state["queue"]) else None
    return SessionView(session_id=session_id, mode=state["mode"], status=state["status"],
                       profile_id=state.get("profile_id"), posting_id=state.get("posting_id"),
                       action_id=None if finished else state.get("action_id"), question=state.get("question"),
                       target=target, draft_profile=state.get("proposal") if state["mode"] == "update" else state.get("profile"),
                       changed_paths=state.get("changed_paths", []), messages=state.get("messages", []), warnings=state.get("warnings", []),
                       persistent_checkpoints=database.enabled())


def start_update(request: UpdateStart) -> SessionView:
    if current_revision(request.profile_id) != request.profile_id:
        raise RevisionConflict("Đây là revision cũ. Chọn hồ sơ mới nhất trước khi cập nhật.")
    result = evaluate_job(request.posting_id, request.profile_id)
    if result.matching is None:
        raise ValueError("Cần JD và Matching hợp lệ trước khi hỏi bổ sung hồ sơ")
    root = root_id(request.profile_id)
    targets = requirement_targets(result.analysis.job_requirements)
    queue = []
    deferred = 0
    for item in result.matching.assessments:
        if item.counted_in_score and item.status == "unknown" and item.requirement_id in targets:
            target = targets[item.requirement_id]
            if target["source_field"] in {"education_requirements", "certifications"}:
                deferred += 1
                continue
            if records.answer_for(root, target) is None:
                queue.append(target)
    session_id = uuid4().hex
    records.put("sessions", session_id, {"mode": "update"})
    state = {"session_id": session_id, "mode": "update", "profile_id": request.profile_id,
             "root_id": root, "posting_id": request.posting_id, "queue": queue[:5], "index": 0,
             "messages": [], "warnings": ["Phiên này hỏi tối đa 5 yêu cầu; bạn có thể mở phiên tiếp theo cho các mục còn lại."] if len(queue) > 5 else [], "status": "running"}
    if deferred:
        state["warnings"].append("Phiên này bổ sung kỹ năng/kinh nghiệm. Các mục học vấn/chứng chỉ chưa có bằng chứng vẫn giữ trong Gap Analysis, không tự thêm vào dự án.")
    config = {"configurable": {"thread_id": session_id}}
    if not queue:
        update_graph.update_state(config, {**state, "status": "completed"}, as_node="next")
    else:
        update_graph.invoke(state, config)
    return view_session(session_id)


def start_build() -> SessionView:
    session_id = uuid4().hex
    records.put("sessions", session_id, {"mode": "build"})
    chat_graph.invoke({"session_id": session_id, "mode": "build", "status": "pending_answer",
                       "action_id": f"{session_id}:0:message", "messages": [],
                       "question": "Bạn hãy giới thiệu thông tin liên hệ, kinh nghiệm, dự án, học vấn và kỹ năng có thật. Có thể bổ sung nhiều lượt; hồ sơ chỉ lưu khi bạn xác nhận."},
                      {"configurable": {"thread_id": session_id}})
    return view_session(session_id)


def act(session_id: str, action: SessionAction) -> SessionView:
    with _session_lock:
        graph, config = graph_for(session_id)
        if records.get("events", f"{session_id}:{action.event_id}"):
            return view_session(session_id)
        state = graph.get_state(config).values
        if not state or action.action_id != state.get("action_id") or state.get("status") in {"completed", "cancelled"}:
            raise RevisionConflict("Thao tác này đã cũ. Tải lại phiên trước khi trả lời.")
        allowed = {"approve", "reject", "continue", "finish"} if state["status"] == "pending_approval" else ({"yes", "no", "skip", "finish"} if state["mode"] == "update" else {"message", "finish"})
        if action.decision not in allowed:
            raise ValueError("Thao tác không phù hợp bước hiện tại")
        if state["mode"] == "build" and len(state.get("source", "")) + len(action.message) > 60000:
            raise ValueError("Nội dung hồ sơ vượt 60000 ký tự; hãy rút gọn thông tin")
        graph.invoke(Command(resume=action.model_dump()), config)
        records.put("events", f"{session_id}:{action.event_id}", {"processed": True})
        return view_session(session_id)


def retry(session_id: str) -> SessionView:
    with _session_lock:
        graph, config = graph_for(session_id)
        graph.invoke(None, config)
        return view_session(session_id)
