import ipaddress
import json
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3


class UnsafeJobUrl(ValueError):
    pass


class JobFetchError(RuntimeError):
    pass


class JobContentError(ValueError):
    pass


def _is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeJobUrl("URL phải sử dụng http/https và có hostname hợp lệ")
    if parsed.username or parsed.password:
        raise UnsafeJobUrl("URL không được chứa thông tin đăng nhập")
    hostname = parsed.hostname.casefold()
    if hostname == "localhost" or hostname.endswith(".local"):
        raise UnsafeJobUrl("Không được truy cập localhost hoặc mạng nội bộ")

    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as error:
        raise JobFetchError("Không phân giải được tên miền của URL") from error
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise UnsafeJobUrl("URL phân giải tới địa chỉ IP không công khai")


def _find_job_posting(value):
    if isinstance(value, dict):
        item_type = value.get("@type")
        types = item_type if isinstance(item_type, list) else [item_type]
        if "JobPosting" in types:
            return value
        for child in value.values():
            result = _find_job_posting(child)
            if result:
                return result
    if isinstance(value, list):
        for child in value:
            result = _find_job_posting(child)
            if result:
                return result
    return None


def extract_job_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            job = _find_job_posting(json.loads(script.string or ""))
        except json.JSONDecodeError:
            continue
        if job:
            organization = job.get("hiringOrganization") or {}
            location = job.get("jobLocation") or ""
            parts = [
                job.get("title"),
                organization.get("name") if isinstance(organization, dict) else None,
                json.dumps(location, ensure_ascii=False) if isinstance(location, (dict, list)) else location,
                job.get("employmentType"),
                BeautifulSoup(str(job.get("description", "")), "html.parser").get_text("\n"),
            ]
            text = "\n".join(str(part).strip() for part in parts if part).strip()
            if text:
                return text

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    candidates = soup.find_all(["main", "article"])
    container = max(candidates, key=lambda item: len(item.get_text()), default=soup.body)
    text = container.get_text("\n", strip=True) if container else ""
    if len(text) < 30:
        raise JobContentError("Trang web không chứa nội dung JD có thể đọc được")
    return text


def fetch_job_content(url: str, client: httpx.Client | None = None) -> tuple[str, str]:
    current_url = url
    own_client = client is None
    active_client = client or httpx.Client(timeout=15, follow_redirects=False)
    try:
        for _ in range(MAX_REDIRECTS + 1):
            validate_public_url(current_url)
            try:
                with active_client.stream(
                    "GET",
                    current_url,
                    headers={"User-Agent": "KLTN-JD-Analyzer/1.0"},
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise JobFetchError("Website redirect nhưng không cung cấp URL mới")
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    if content_type and not any(
                        value in content_type.casefold()
                        for value in ("text/html", "application/xhtml+xml")
                    ):
                        raise JobContentError("URL không trả về nội dung HTML")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_RESPONSE_BYTES:
                            raise JobContentError("Nội dung website vượt quá giới hạn 2 MB")
                    html = bytes(content).decode(response.encoding or "utf-8", errors="replace")
                    return extract_job_text(html), str(response.url)
            except httpx.HTTPStatusError as error:
                raise JobFetchError(
                    f"Website tuyển dụng trả về HTTP {error.response.status_code}"
                ) from error
            except httpx.RequestError as error:
                raise JobFetchError("Không thể truy cập website tuyển dụng") from error
        raise JobFetchError("Website chuyển hướng quá nhiều lần")
    finally:
        if own_client:
            active_client.close()

