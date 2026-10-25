"""Bounded public-feed import for the local demo; never calls a model."""

import html
import re
from datetime import datetime, timezone
from threading import Lock
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup

from backend.app.db.job_posting_repository import (
    atomic_json, canonical_url, get_posting, posting_id, storage_root, upsert_posting, utc_now, read_aux, write_aux,
)
from backend.app.schemas.dashboard import JobImportRequest, JobPosting
from backend.app.services.job_fetcher import (
    JobContentError, JobFetchError, UnsafeJobUrl, _html_text, fetch_job_content, fetch_public_json,
)


BOARDS = {"palantir": "Palantir Technologies", "spotify": "Spotify"}
SYNC_QUERIES = (("palantir", "Delta", 2), ("spotify", "Platform", 2))
SYNC_FEEDS = ("himalayas", "remoteok", "greenhouse")
GREENHOUSE_BOARDS = {"grafanalabs": "Grafana Labs"}
DOMESTIC_SOURCES = {"TopCV", "ITviec", "JobsGO"}
_sync_lock = Lock()


def timestamp(value) -> str | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def is_expired(job: JobPosting) -> bool:
    expiry = timestamp(job.expires_at)
    return bool(expiry and datetime.fromisoformat(expiry) <= datetime.now(timezone.utc))


def description_text(value: str) -> str:
    """Decode feed HTML and keep nested alternatives indented for JD extraction."""
    soup = BeautifulSoup(html.unescape(value), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for root in list(soup.find_all(["ul", "ol"])):
        if not root.find_parent(["ul", "ol"]):
            root.replace_with("\n" + list_html_text(str(root)) + "\n")
    for tag in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "section", "br"]):
        tag.insert_before("\n")
        tag.append("\n")
    return "\n".join(line.rstrip() for line in soup.get_text().splitlines() if line.strip()).strip()


def source_link(value: str, domain: str) -> str:
    # Validate feed-owned attribution links, not arbitrary employer HTML links.
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or not (parsed.hostname.lower() == domain or parsed.hostname.lower().endswith("." + domain)) or parsed.username or parsed.password:
        raise JobContentError("Nguồn trả về URL không thuộc nền tảng tuyển dụng")
    return value


def salary_text(low, high, currency, period) -> str | None:
    values = [value for value in (low, high) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0]
    if not values:
        return None
    return f"{min(values):g} – {max(values):g} {currency or '(chưa công bố tiền tệ)'} / {period or '(chưa công bố kỳ lương)'}"


def himalayas_job(data: dict) -> JobPosting:
    url = source_link(data["guid"], "himalayas.app")
    apply_url = source_link(data["applicationLink"], "himalayas.app")
    locations = data.get("locationRestrictions")
    now = utc_now()
    return JobPosting(
        posting_id=posting_id("himalayas", "", url), title=data["title"], company=data.get("companyName"),
        # Empty API restrictions are not proof of worldwide eligibility: some
        # descriptions still explicitly restrict the region. Leave it unknown.
        location=", ".join(locations) if locations else None,
        location_restrictions=locations or [], timezone_restrictions=[str(x) for x in data.get("timezoneRestrictions", [])],
        workplace_type="remote", employment_type=data.get("employmentType"),
        salary=salary_text(data.get("minSalary"), data.get("maxSalary"), data.get("currency"), data.get("salaryPeriod")),
        description=description_text(data["description"]), source_name="Himalayas", external_id=url,
        source_url=url, apply_url=apply_url, fetched_at=now, imported_at=now,
        source_created_at=timestamp(data.get("pubDate")), expires_at=timestamp(data.get("expiryDate")), import_method="fetch",
    )


def remoteok_job(data: dict) -> JobPosting:
    url = source_link(data["url"], "remoteok.com")
    now = utc_now()
    # The feed does not specify currency/period for these numeric fields. Keep
    # that uncertainty rather than assuming USD/year from the provider's market.
    return JobPosting(
        posting_id=posting_id("remoteok", "", str(data["id"])), title=data["position"], company=data.get("company"),
        location=data.get("location") or None, workplace_type="remote",
        salary=salary_text(data.get("salary_min"), data.get("salary_max"), data.get("salary_currency"), data.get("salary_period")),
        description=description_text(data["description"]), source_name="Remote OK", external_id=str(data["id"]),
        source_url=url, apply_url=url, fetched_at=now, imported_at=now,
        source_created_at=timestamp(data.get("date") or data.get("epoch")), import_method="fetch",
    )


def greenhouse_job(data: dict, board: str) -> JobPosting:
    now = utc_now()
    return JobPosting(
        posting_id=posting_id("greenhouse", board, str(data["id"])), title=data["title"],
        company=data.get("company_name") or GREENHOUSE_BOARDS[board], location=(data.get("location") or {}).get("name"),
        description=description_text(data["content"]), source_name="Greenhouse", source_board=board, external_id=str(data["id"]),
        source_url=data["absolute_url"], apply_url=data["absolute_url"], fetched_at=now, imported_at=now,
        source_created_at=timestamp(data.get("first_published")), source_updated_at=timestamp(data.get("updated_at")),
        expires_at=timestamp(data.get("application_deadline")), import_method="fetch",
    )


def technology_role(title: str) -> bool:
    return bool(re.search(r"\b(software|backend|front[ -]?end|full[ -]?stack|developer|devops|data engineer|machine learning|ai engineer|platform engineer|security engineer)\b", title, re.I))


def fetch_feed(provider: str) -> list[JobPosting]:
    """At most one feed page, plus two Greenhouse detail requests; no crawl."""
    if provider == "himalayas":
        data = fetch_public_json("https://himalayas.app/jobs/api/search?q=software%20engineer&country=VN")
        rows, convert = data.get("jobs"), himalayas_job
    elif provider == "remoteok":
        rows = fetch_public_json("https://remoteok.com/api?tag=dev")
        convert = remoteok_job
    elif provider == "greenhouse":
        board = "grafanalabs"
        data = fetch_public_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs")
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise JobContentError("Greenhouse không trả về danh sách jobs")
        selected = [row for row in data["jobs"] if technology_role(row.get("title", ""))][:2]
        return [greenhouse_job(fetch_public_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{int(row['id'])}"), board) for row in selected]
    else:
        raise JobContentError("Nguồn jobs không được hỗ trợ")
    if not isinstance(rows, list):
        raise JobContentError("Nguồn jobs không trả về danh sách")
    jobs = []
    for row in rows:
        # Remote OK's first entry contains API terms, not a job.
        if not isinstance(row, dict) or not technology_role(row.get("title") or row.get("position") or ""):
            continue
        job = convert(row)
        if not is_expired(job):
            jobs.append(job)
        if len(jobs) == 3:
            break
    return jobs


def source_label(url: str | None) -> str:
    host = (urlsplit(url).hostname or "").lower() if url else ""
    for domain, name in (("topcv.vn", "TopCV"), ("itviec.com", "ITviec"),
                         ("jobsgo.vn", "JobsGO"), ("indeed.com", "Indeed"),
                         ("indeed.vn", "Indeed"), ("linkedin.com", "LinkedIn")):
        if host == domain or host.endswith("." + domain):
            return name
    return "URL do người dùng cung cấp" if url else "JD người dùng nhập"


def list_html_text(html: str) -> str:
    """Keep nesting: a parent 'one of' must retain its child alternatives."""
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all("li")
    if not items:
        return _html_text(html)
    lines = []
    for item in items:
        depth = max(0, len(item.find_parents(["ul", "ol"])) - 1)
        copy = BeautifulSoup(str(item), "html.parser")
        for nested in copy.find_all(["ul", "ol"]):
            nested.decompose()
        text = copy.get_text(" ", strip=True)
        if text:
            lines.append("  " * depth + "- " + text)
    return "\n".join(lines)


def lever_job(data: dict, board: str) -> JobPosting:
    if board not in BOARDS or not isinstance(data, dict):
        raise JobContentError("Company board không được hỗ trợ")
    external_id = data.get("id")
    if not isinstance(external_id, str) or not external_id or len(external_id) > 128:
        raise JobContentError("Tin tuyển dụng thiếu ID hợp lệ")
    source_url = data.get("hostedUrl")
    for url in (source_url, data.get("applyUrl")):
        if url and (urlsplit(url).scheme != "https" or urlsplit(url).hostname != "jobs.lever.co" or not urlsplit(url).path.startswith(f"/{board}/")):
            raise JobContentError("URL tin tuyển dụng không thuộc company board")
    if not source_url or not data.get("text"):
        raise JobContentError("Tin tuyển dụng thiếu tên hoặc URL nguồn")
    parts = [data.get("descriptionPlain") or _html_text(data.get("description") or "")]
    for section in data.get("lists") or []:
        parts.extend([section.get("text") or "", list_html_text(section.get("content") or "")])
    parts.append(data.get("additionalPlain") or _html_text(data.get("additional") or ""))
    salary = data.get("salaryDescriptionPlain")
    salary_range = data.get("salaryRange") or {}
    if not salary and salary_range:
        low, high = salary_range.get("min"), salary_range.get("max")
        if low is not None or high is not None:
            salary = f"{low if low is not None else '?'} – {high if high is not None else '?'} {salary_range.get('currency') or ''} / {salary_range.get('interval') or 'kỳ chưa công bố'}"
    if salary:
        parts.append("Compensation\n" + salary)
    categories = data.get("categories") or {}
    created = data.get("createdAt")
    created_at = None
    if isinstance(created, (float, int)):
        try:
            created_at = datetime.fromtimestamp(created / 1000, timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError):
            pass
    now = utc_now()
    return JobPosting(
        posting_id=posting_id("lever", board, external_id), title=data["text"],
        company=BOARDS[board], location=categories.get("location"),
        employment_type=categories.get("commitment"),
        workplace_type=None if data.get("workplaceType") == "unspecified" else data.get("workplaceType"),
        salary=salary, description="\n\n".join(part.strip() for part in parts if part and part.strip()),
        source_name="Lever", source_board=board, external_id=external_id,
        source_url=source_url, apply_url=data.get("applyUrl") or source_url,
        fetched_at=now, imported_at=now, source_created_at=created_at,
    )


def sync_state() -> dict:
    return read_aux("feed_state", "current") or {}


def sync_jobs() -> dict:
    if not SYNC_QUERIES and not SYNC_FEEDS:
        return {"inserted": 0, "updated": 0, "unchanged": 0, "fetched": 0,
                "cooldown": False, "sources": {}, "status": "source_not_configured",
                "errors": ["Chưa có API/feed được phép cho nguồn tuyển dụng Việt Nam. Đồng bộ Palantir/Spotify đã tắt; chưa lấy thêm tin mới."]}
    if not _sync_lock.acquire(blocking=False):
        raise JobFetchError("Đang đồng bộ jobs; vui lòng chờ lần hiện tại hoàn tất")
    try:
        state = sync_state()
        totals = {"inserted": 0, "updated": 0, "unchanged": 0}
        errors, fetched = [], 0
        now = utc_now()
        # Manual refresh only. Our own cooldown prevents repeated clicks from polling boards.
        if state.get("attempted_at") and (datetime.fromisoformat(now) - datetime.fromisoformat(state["attempted_at"])).total_seconds() < 30:
            return {**totals, "fetched": 0, "cooldown": True, "sources": state.get("sources", {}), "errors": ["Chờ 30 giây giữa các lần đồng bộ."]}
        sources = state.get("sources", {})
        cached_sources = []
        for provider in SYNC_FEEDS:
            previous = sources.get(provider, {})
            interval = 86400 if provider == "himalayas" else 3600
            last_success = timestamp(previous.get("last_success_at"))
            if last_success and (datetime.fromisoformat(now) - datetime.fromisoformat(last_success)).total_seconds() < interval:
                cached_sources.append(provider)
                continue
            try:
                imported = fetch_feed(provider)
                for job in imported:
                    if is_expired(job):
                        continue
                    _, outcome = upsert_posting(job)
                    totals[outcome] += 1
                    fetched += 1
                sources[provider] = {"source_name": {"himalayas": "Himalayas", "remoteok": "Remote OK", "greenhouse": "Greenhouse"}[provider],
                                     "attempted_at": now, "last_success_at": now, "status": "success", "count": len(imported)}
            except (JobFetchError, JobContentError, UnsafeJobUrl, ValueError, TypeError, KeyError, AttributeError):
                errors.append(f"{provider}: không đồng bộ được; giữ snapshot đã lưu.")
                sources[provider] = {**previous, "source_name": provider, "attempted_at": now, "status": "error"}
        succeeded_boards = set()
        for board, team, limit in SYNC_QUERIES:
            try:
                data = fetch_public_json(f"https://api.lever.co/v0/postings/{board}?mode=json&limit={limit}&team={quote(team)}")
                if not isinstance(data, list):
                    raise JobContentError("Nguồn jobs không trả về danh sách")
                for entry in data[:limit]:
                    _, outcome = upsert_posting(lever_job(entry, board))
                    totals[outcome] += 1
                    fetched += 1
                succeeded_boards.add(board)
            except (JobFetchError, JobContentError, UnsafeJobUrl, ValueError, TypeError, KeyError):
                errors.append(f"Lever / {board} / {team}: không đồng bộ được; giữ snapshot đã lưu.")
        for board in {entry[0] for entry in SYNC_QUERIES}:
            previous = sources.get(board, {})
            failed = any(f"/ {board} /" in error for error in errors)
            sources[board] = {
                "source_name": "Lever", "board": board, "attempted_at": now,
                "last_success_at": now if board in succeeded_boards else previous.get("last_success_at"),
                "status": "partial" if failed and board in succeeded_boards else "error" if failed else "success",
            }
        write_aux("feed_state", "current", {"attempted_at": now, "sources": sources, "errors": errors})
        return {**totals, "fetched": fetched, "cooldown": False, "sources": sources, "errors": errors, "cached_sources": cached_sources}
    finally:
        _sync_lock.release()


def import_job(request: JobImportRequest) -> JobPosting:
    if request.source_url and not request.job_description_text:
        text, url = fetch_job_content(request.source_url)
        external_id = canonical_url(url)
        fetched_at = utc_now()
    else:
        import hashlib
        text, url = request.job_description_text, request.source_url
        external_id = canonical_url(url) if url else hashlib.sha256(text.encode()).hexdigest()
        fetched_at = None
    job = JobPosting(
        posting_id=posting_id("manual", "", external_id),
        title=next(line.strip() for line in text.splitlines() if line.strip())[:200],
        description=text, source_name=source_label(url), external_id=external_id,
        source_url=url, apply_url=url, fetched_at=fetched_at, imported_at=utc_now(),
        import_method="text" if request.job_description_text else "fetch",
    )
    return upsert_posting(job)[0]


def refresh_job(key: str) -> dict:
    previous = get_posting(key)
    if previous is None:
        raise LookupError("Không tìm thấy công việc")
    if previous.import_method == "text":
        return {"job": previous, "warning": "JD do người dùng nhập, chưa xác minh trực tiếp với nguồn. Nhập lại nội dung cùng URL để cập nhật; hệ thống không tự thay nội dung này bằng trang web."}
    try:
        if previous.source_name == "Lever":
            data = fetch_public_json(f"https://api.lever.co/v0/postings/{previous.source_board}/{quote(previous.external_id, safe='')}")
            job = lever_job(data, previous.source_board)
            if job.posting_id != previous.posting_id:
                raise JobContentError("Nguồn trả về ID khác công việc đã chọn")
        elif previous.source_name in {"Himalayas", "Remote OK"}:
            return {"job": previous, "warning": "Nguồn này được cập nhật qua feed có cache. Dùng Refresh tin tuyển dụng để đồng bộ khi hết thời gian cache; giữ snapshot hiện tại."}
        elif previous.source_name == "Greenhouse":
            if previous.source_board not in GREENHOUSE_BOARDS or not previous.external_id.isdigit():
                raise JobContentError("Company board hoặc job ID không hợp lệ")
            data = fetch_public_json(f"https://boards-api.greenhouse.io/v1/boards/{previous.source_board}/jobs/{previous.external_id}")
            job = greenhouse_job(data, previous.source_board)
        elif previous.source_url:
            text, _ = fetch_job_content(previous.source_url)
            job = previous.model_copy(update={"description": text, "fetched_at": utc_now()})
            job = JobPosting.model_validate(job.model_dump())
        else:
            return {"job": previous, "warning": "JD nhập thủ công không có URL để cập nhật."}
        return {"job": upsert_posting(job)[0], "warning": None}
    except (JobFetchError, JobContentError, UnsafeJobUrl, ValueError, TypeError, KeyError):
        return {"job": previous, "warning": "Không cập nhật được nguồn. Đang hiển thị snapshot theo thời điểm lấy đã lưu; chưa xác minh tình trạng tuyển dụng hiện tại."}
