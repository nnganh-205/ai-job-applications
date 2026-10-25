import ipaddress
import json
import socket
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
FETCH_DEADLINE_SECONDS = 30


class UnsafeJobUrl(ValueError):
    pass


class JobFetchError(RuntimeError):
    pass


class JobContentError(ValueError):
    pass


def _is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return _is_public_ip(str(ip.ipv4_mapped))
    if isinstance(ip, ipaddress.IPv6Address) and (ip.sixtofour or ip.teredo):
        return False
    return ip.is_global and not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(url: str) -> list[str]:
    try:
        parsed = urlparse(url)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError as error:
        raise UnsafeJobUrl("URL không hợp lệ") from error
    if len(url) > 2048 or any(ord(char) < 33 for char in url) or "\\" in url:
        raise UnsafeJobUrl("URL không hợp lệ")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeJobUrl("URL phải sử dụng http/https và có hostname hợp lệ")
    if parsed.username or parsed.password:
        raise UnsafeJobUrl("URL không được chứa thông tin đăng nhập")
    hostname = hostname.casefold().rstrip(".")
    if port not in {None, 80, 443}:
        raise UnsafeJobUrl("Chỉ hỗ trợ cổng HTTP/HTTPS 80 hoặc 443")
    if hostname == "localhost" or hostname.endswith((".local", ".localhost")) or "%" in hostname:
        raise UnsafeJobUrl("Không được truy cập localhost hoặc mạng nội bộ")

    try:
        try:
            addresses = {str(ipaddress.ip_address(hostname))}
        except ValueError:
            addresses = {item[4][0] for item in socket.getaddrinfo(hostname, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except socket.gaierror as error:
        raise JobFetchError("Không phân giải được tên miền của URL") from error
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise UnsafeJobUrl("URL phân giải tới địa chỉ IP không công khai")
    return sorted(addresses)


def _html_text(value: str) -> str:
    soup = BeautifulSoup(value, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for tag in soup.find_all(["p", "li", "div", "h1", "h2", "h3", "h4", "section"]):
        tag.insert_before("\n")
        tag.append("\n")
    for tag in soup.find_all("br"):
        tag.replace_with("\n")
    return "\n".join(" ".join(line.split()) for line in soup.get_text(" ").splitlines() if line.strip())


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
        except (json.JSONDecodeError, RecursionError):
            continue
        if job:
            organization = job.get("hiringOrganization") or {}
            location = job.get("jobLocation") or ""
            parts = [
                job.get("title"),
                organization.get("name") if isinstance(organization, dict) else None,
                json.dumps(location, ensure_ascii=False) if isinstance(location, (dict, list)) else location,
                job.get("employmentType"),
                _html_text(str(job.get("description", ""))),
            ]
            text = "\n".join(str(part).strip() for part in parts if part).strip()
            if len(_html_text(str(job.get("description", "")))) >= 30:
                return text

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    candidates = soup.find_all(["main", "article"])
    container = max(candidates, key=lambda item: len(item.get_text()), default=soup.body)
    text = _html_text(str(container)) if container else ""
    if len(text) < 30:
        raise JobContentError("Trang web không chứa nội dung JD có thể đọc được")
    return text


def _fetch_public_response(
    url: str, client: httpx.Client | None, content_types: tuple[str, ...],
) -> tuple[str, str]:
    current_url = url
    own_client = client is None
    active_client = client or httpx.Client(timeout=10, follow_redirects=False, trust_env=False)
    started = time.monotonic()
    try:
        for _ in range(MAX_REDIRECTS + 1):
            addresses = validate_public_url(current_url)
            # Pin the checked IP, retaining the original Host and TLS certificate name.
            # This closes the DNS validation/connect rebinding gap; proxies are disabled.
            original = httpx.URL(current_url)
            target = original.copy_with(host=addresses[0], fragment=None)
            remaining = FETCH_DEADLINE_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                raise JobFetchError("Quá thời gian tải JD; vui lòng dán JD thủ công")
            try:
                with active_client.stream(
                    "GET",
                    target,
                    headers={"User-Agent": "KLTN-JD-Analyzer/1.0", "Host": original.netloc.decode("ascii")},
                    extensions={"sni_hostname": original.host},
                    timeout=min(10, remaining),
                    follow_redirects=False,
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise JobFetchError("Website redirect nhưng không cung cấp URL mới")
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    length = response.headers.get("content-length", "")
                    if length.isdigit() and int(length) > MAX_RESPONSE_BYTES:
                        raise JobContentError("Nội dung website vượt quá giới hạn 2 MB")
                    content_type = response.headers.get("content-type", "")
                    if content_type and not any(
                        value in content_type.casefold()
                        for value in content_types
                    ):
                        raise JobContentError("URL không trả về đúng loại nội dung yêu cầu")
                    content = bytearray()
                    for chunk in response.iter_bytes(chunk_size=16384):
                        if time.monotonic() - started > FETCH_DEADLINE_SECONDS:
                            raise JobFetchError("Quá thời gian tải JD; vui lòng dán JD thủ công")
                        content.extend(chunk)
                        if len(content) > MAX_RESPONSE_BYTES:
                            raise JobContentError("Nội dung website vượt quá giới hạn 2 MB")
                    html = bytes(content).decode(response.encoding or "utf-8", errors="replace")
                    return html, current_url
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


def fetch_job_content(url: str, client: httpx.Client | None = None) -> tuple[str, str]:
    html, final_url = _fetch_public_response(url, client, ("text/html", "application/xhtml+xml"))
    return extract_job_text(html), final_url


def fetch_public_json(url: str, client: httpx.Client | None = None):
    """Same DNS/IP/redirect/size protections as JD fetching; no arbitrary proxy."""
    text, _ = _fetch_public_response(url, client, ("application/json",))
    try:
        return json.loads(text)
    except (ValueError, RecursionError) as error:
        raise JobContentError("Nguồn tuyển dụng trả JSON không hợp lệ") from error

