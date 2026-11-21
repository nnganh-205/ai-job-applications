"""Selected-job orchestration. Scoring and extraction stay in the existing Agents."""

import hashlib
import json
import re
from threading import Lock

from ai.agents.jd_agent import validate_evidence, normalize_requirements, assign_requirement_ids, build_requirement_groups
from ai.agents.matching_agent import match_profile, profile_facts
from ai.graph.jd_workflow import run_jd_analysis
from ai.llm.ollama_client import llm_deadline, OllamaTimeoutError
from backend.app.core.config import settings
from backend.app.db import job_repository, match_repository, profile_repository
from backend.app.db.job_posting_repository import (
    analysis_text, atomic_json, get_posting, list_postings, search_postings, storage_root, read_aux, write_aux,
)
from backend.app.schemas.dashboard import DashboardEvaluation, JobPosting
from backend.app.schemas.job import JobRequirements
from backend.app.services.job_importer import DOMESTIC_SOURCES, is_expired, sync_state
from backend.app.services.profile_answers import confirmed_denials


ANALYSIS_VERSION = "jd-dashboard-v9-mentions"
_analysis_locks: dict[str, Lock] = {}


def analysis_key(job: JobPosting) -> str:
    return hashlib.sha256(f"{job.content_hash}|{ANALYSIS_VERSION}|{settings.identity_for_task('jd')}".encode()).hexdigest()


def cached_analysis(job: JobPosting):
    try:
        pointer = read_aux("analysis_cache", analysis_key(job))
        if pointer is None:
            return None
        result = job_repository.load_job_analysis(pointer["job_id"], job_repository.DEFAULT_JOB_STORAGE)
        if result and result.analysis_version == ANALYSIS_VERSION and result.content_hash == job.content_hash and result.model == settings.model_for_task('jd'):
            return result
    except (ValueError, OSError, KeyError):
        pass
    return None


def analyze_selected_job(job: JobPosting):
    key = analysis_key(job)
    lock = _analysis_locks.setdefault(key, Lock())
    if not lock.acquire(timeout=300):
        raise OllamaTimeoutError("JD đang được phân tích; vui lòng thử lại sau.")
    try:
        previous = cached_analysis(job)
        if previous:
            return previous, True
        with llm_deadline(300):
            state = run_jd_analysis(job_description_text=analysis_text(job))
        from backend.app.services.ai_progress import report
        report('jd_save','Đang lưu phân tích JD đã kiểm tra')
        requirements = JobRequirements.model_validate(state["job_requirements"])
        result = job_repository.save_job_analysis(
            requirements, state.get("warnings", []), job.source_url, job_repository.DEFAULT_JOB_STORAGE,
            analysis_version=ANALYSIS_VERSION, content_hash=job.content_hash, model=settings.model_for_task('jd'),
        )
        write_aux("analysis_cache", key, {"job_id": result.job_id})
        return result, False
    finally:
        lock.release()


def confirmed_profiles() -> list[dict]:
    return [{"profile_id": key, "full_name": record.profile.contact.full_name, "parent_profile_id": record.parent_profile_id}
            for key, record in profile_repository.list_profile_records() if not key.startswith("cvlocal_")]


def dashboard_snapshot(q: str = "", location: str = "", employment_type: str = "", workplace_type: str = "", saved: bool = False, source_name: str = "", domestic_sources_only: bool = False, industry: str = "", experience_level: str = "", salary_min: float | None = None, salary_currency: str = "VND", salary_period: str = "month") -> dict:
    jobs = []
    all_jobs = [job for job in list_postings() if not is_expired(job)]
    if domestic_sources_only:
        all_jobs = [job for job in all_jobs if job.source_name in DOMESTIC_SOURCES]
    candidates = search_postings(q=q, location=location, employment_type=employment_type,
        workplace_type=workplace_type, saved=saved, source_name=source_name, industry=industry,
        experience_level=experience_level, salary_min=salary_min, salary_currency=salary_currency,
        salary_period=salary_period)
    eligible = {job.posting_id for job in all_jobs}
    for job in candidates:
        if job.posting_id not in eligible:
            continue
        analysis = cached_analysis(job)
        requirements = analysis.job_requirements if analysis else None
        skills = [item.name for item in requirements.required_skills + requirements.preferred_skills] if requirements else []
        summary = job.model_dump(mode="json", exclude={"description"})
        summary.update(analysis_status="analyzed" if analysis else "not_analyzed", skills=skills)
        if requirements:
            summary["salary"] = job.salary or requirements.salary
        jobs.append(summary)
    profiles = confirmed_profiles()
    active_id = profiles[0]["profile_id"] if profiles else None
    record = profile_repository.load_profile_record(active_id, profile_repository.DEFAULT_STORAGE_DIR) if active_id else None
    return {
        "jobs": jobs, "total": len(all_jobs), "profiles": profiles,
        "active_profile_id": active_id, "profile": record.profile if record else None,
        "filters": {field: sorted({getattr(job, field) for job in all_jobs if getattr(job, field)}) for field in ("location", "employment_type", "workplace_type", "source_name", "industry", "experience_level")},
        "sync": {} if domestic_sources_only else sync_state(),
    }


def evaluate_job(key: str, profile_id: str | None, *, cv_id: str | None = None) -> DashboardEvaluation:
    job = get_posting(key)
    if job is None:
        raise LookupError("Không tìm thấy công việc")
    if is_expired(job):
        raise ValueError("Tin tuyển dụng đã hết hạn theo dữ liệu nguồn")
    # Resolve a requested profile before spending model time; never silently replace a missing ID.
    if profile_id is None and cv_id is None:
        profiles = confirmed_profiles()
        profile_id = profiles[0]["profile_id"] if profiles else None
    record = profile_repository.load_profile_record(profile_id, profile_repository.DEFAULT_STORAGE_DIR) if profile_id else None
    if profile_id and record is None:
        raise LookupError("Master Profile chưa xác nhận hoặc không tồn tại")
    cv_refs = None
    if cv_id:
        if profile_id:
            raise ValueError("Chọn một loại đầu vào")
        from backend.app.db import workflow_repository as records
        from backend.app.schemas.cv import CVDocument
        from backend.app.schemas.profile import StoredProfile
        from backend.app.services.cv_evaluation import displayed_profile
        version = records.get('cv_versions', cv_id)
        if version is None:
            raise LookupError('Không tìm thấy CV version đã publish')
        projected, cv_refs = displayed_profile(CVDocument.model_validate(version['document']))
        record = StoredProfile(profile=projected)
        profile_id = cv_id
    analysis, hit = analyze_selected_job(job)
    # Revalidate cached extraction with current grouping rules. Historical warnings
    # are not proof that the current parser still cannot resolve a relationship.
    requirements, normalization_warnings = normalize_requirements(analysis.job_requirements.model_copy(deep=True))
    assign_requirement_ids(requirements)
    relationship_warnings = build_requirement_groups(requirements)
    warnings = list(dict.fromkeys([
        *[warning for warning in analysis.warnings if not any(marker in warning for marker in ("AND/OR", "OR chồng lấn"))],
        *normalization_warnings, *relationship_warnings,
    ]))
    analysis = analysis.model_copy(update={"job_requirements": requirements, "warnings": warnings})
    response = DashboardEvaluation(
        status="needs_profile" if record is None else "insufficient_data",
        job=job, analysis=analysis, profile_id=profile_id, profile=record.profile if record else None,
        analysis_version=ANALYSIS_VERSION, model=settings.model_for_task('jd'), analysis_cached=hit, warnings=warnings,
        input_type="cv" if cv_id else "profile", input_id=profile_id,
    )
    if cv_id:
        from backend.app.services.cv_lineage import version_status
        response.cv_version = version_status(cv_id,version)
    if record is None:
        return response
    if not profile_facts(record.profile):
        response.warnings.append("Hồ sơ chưa có dữ liệu chuyên môn để tính điểm.")
        return response
    critical = [warning for warning in validate_evidence(analysis.job_requirements)
                if warning.startswith(("required_skills", "experience_requirements", "education_requirements", "core_requirements"))]
    ambiguous_groups = [warning for warning in warnings if any(marker in warning for marker in ("AND/OR", "OR chồng lấn"))]
    if critical or ambiguous_groups:
        response.status = "needs_review"
        response.warnings = list(dict.fromkeys([*warnings, *critical, *ambiguous_groups]))
        return response
    result = match_profile(record.profile, analysis.job_requirements, profile_id, analysis.job_id,
                           confirmed_unmet={} if cv_id else confirmed_denials(profile_id, analysis.job_requirements))
    if cv_refs is not None:
        from backend.app.services.cv_evaluation import visible_evidence
        result = visible_evidence(result, cv_refs)
        result.profile_revision_id = version['document']['source_profile_revision_id']
        result.input_type = 'cv'
    result.input_id = profile_id
    result.warnings = list(dict.fromkeys([*result.warnings, *warnings, *record.warnings]))
    response.matching_cached = match_repository.load_match(result.result_id, match_repository.DEFAULT_MATCH_STORAGE) is not None
    response.matching = match_repository.save_match(result, match_repository.DEFAULT_MATCH_STORAGE)
    source={'document':version['document']} if cv_id else record.profile.model_dump(mode='json')
    for assessment in result.assessments:
        for ref in assessment.evidence_refs:
            value=source
            try:
                for part in ref.lstrip('/').split('/'):
                    value=value[int(part)] if isinstance(value,list) else value[part.replace('~1','/').replace('~0','~')]
                if isinstance(value,str):response.evidence_quotes[ref]=value
            except (KeyError,IndexError,ValueError,TypeError):
                continue
    response.status = "completed" if result.score is not None else "insufficient_data"
    return response
