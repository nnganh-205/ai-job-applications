"""Source scopes for 'one of' requirements, independent of mandatory/preferred."""

import re


ONE_OF = re.compile(r"\b(?:ít\s+nhất\s+)?(?:một|1)\s+trong\b|\b(?:at\s+least\s+)?one\s+of\b", re.I)
REQUIRED = re.compile(r"\b(?:must|mandatory|required)\b|bắt\s*buộc", re.I)
PREFERRED = re.compile(r"ưu tiên|điểm cộng|lợi thế|\b(?:preferred|preferably|bonus)\b|nice[- ]to[- ]have|a plus|advantage", re.I)
OPTIONAL = re.compile(r"không\s*bắt\s*buộc|not\s+(?:strictly\s+)?required|\boptional\b", re.I)
HEADINGS = {
    "requirements", "qualifications", "yêu cầu công việc", "yêu cầu ứng viên",
    "required skills", "mandatory requirements", "yêu cầu bắt buộc", "bắt buộc",
    "nice to have", "preferred skills", "ưu tiên", "điểm cộng",
    "responsibilities", "mô tả công việc", "benefits", "quyền lợi", "about the company",
}


def one_of_blocks(text: str) -> list[str]:
    """Preserve a choice clause and its nested list without absorbing sibling rules."""
    lines = text.splitlines()
    blocks = []
    for index, raw in enumerate(lines):
        if not ONE_OF.search(raw):
            continue
        marker = ONE_OF.search(raw)
        start = raw.rfind(";", 0, marker.start()) + 1
        clause = raw[start:].strip()
        end = re.search(r";\s*(?=(?i:bắt buộc|ưu tiên|phải\b|yêu cầu\b|must\b|preferred\b|required\b))|(?<=[.!?])\s+(?=[A-ZĐ])", clause)
        if end:
            clause = clause[:end.start()].strip()
        block = [clause]
        if clause.endswith((":", "：")):
            indent = len(raw) - len(raw.lstrip())
            parent_bullet = re.match(r"\s*([-+•*])\s+", raw)
            for child in lines[index + 1:]:
                stripped = child.strip()
                if not stripped:
                    if len(block) > 1:
                        break
                    continue
                if stripped.casefold().rstrip(":：") in HEADINGS or ONE_OF.search(child):
                    break
                child_indent = len(child) - len(child.lstrip())
                bullet = re.match(r"\s*([-+•*])\s+", child)
                if parent_bullet and bullet and bullet[1] == parent_bullet[1] and child_indent <= indent:
                    break
                content = re.sub(r"^[-+•*]\s*", "", stripped)
                if child_indent <= indent and re.match(r"(?:có\s+(?:kiến thức|kinh nghiệm)|cần\b|phải\b|yêu cầu\b|ưu tiên\b|bắt buộc\b|tốt nghiệp\b|must\b|preferred\b)", content, re.I):
                    break
                if not bullet and child_indent <= indent and len(content.split()) > 12:
                    break
                block.append(child)
        blocks.append("\n".join(block).strip())
    return blocks


def choice_type(block: str, raw_text: str) -> str:
    if OPTIONAL.search(block):
        return "unspecified"
    if PREFERRED.search(block):
        return "preferred"
    if REQUIRED.search(block):
        return "required"
    # A generic Requirements section does not make every alternative mandatory.
    mode = "unspecified"
    offset = raw_text.find(block.splitlines()[0].strip())
    for line in raw_text[:max(0, offset)].splitlines():
        heading = line.strip().casefold().rstrip(":：")
        if heading in HEADINGS:
            mode = "required" if heading in {"required skills", "mandatory requirements", "yêu cầu bắt buộc", "bắt buộc"} else "preferred" if heading in {"nice to have", "preferred skills", "ưu tiên", "điểm cộng"} else "unspecified"
    return mode


def choice_for_item(name: str, evidence: str, blocks: list[str]) -> str | None:
    normalize = lambda value: re.sub(r"\s+", " ", value).strip().casefold()
    for block in blocks:
        named_in_block = name and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", block, re.I)
        if evidence and (normalize(evidence) in normalize(block) or (named_in_block and normalize(block) in normalize(evidence))):
            return block
    return None
