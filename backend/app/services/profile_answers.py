"""Identity of a question and the user's confirmations, outside CV content."""

from backend.app.db import profile_repository, workflow_repository as records
from backend.app.ai.agents.jd_agent import normalize_requirements, assign_requirement_ids, build_requirement_groups


def requirement_targets(job) -> dict[str, dict]:
    # Old analyses may predate stable IDs. Use the same canonicalization as the
    # scoring engine, without rewriting the saved analysis or calling a model.
    job, _ = normalize_requirements(job.model_copy(deep=True))
    assign_requirement_ids(job)
    build_requirement_groups(job)
    targets = {}
    for field in ("required_skills", "preferred_skills", "experience_requirements", "education_requirements", "certifications", "languages", "technical_requirements"):
        for item in getattr(job, field):
            label = getattr(item, "name", None) or item.description
            targets[item.id] = {"requirement_id": item.id, "label": label, "skill_options": [label] if field in {"required_skills", "preferred_skills"} else [], "source_field": field}
    for group in job.requirement_groups:
        if group.operator == "any":
            targets[group.id] = {"requirement_id": group.id, "label": "Một trong: " + " / ".join(group.members), "skill_options": group.members, "source_field": "required_skills"}
    return targets


def confirmed_denials(profile_id: str, job) -> dict[str, str]:
    record = profile_repository.load_profile_record(profile_id, profile_repository.DEFAULT_STORAGE_DIR)
    if record is None:
        return {}
    root = record.root_profile_id or profile_id
    denied = {}
    for key, target in requirement_targets(job).items():
        answer = records.answer_for(root, target)
        if answer and answer["decision"] == "no":
            denied[key] = "Người dùng đã xác nhận chưa có kinh nghiệm/yêu cầu này; hồ sơ không được thêm kỹ năng."
    return denied
