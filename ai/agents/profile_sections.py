import re
import unicodedata

from backend.app.schemas.profile import SkillGroup


HEADINGS = {
    'skills': ('skills', 'technical skills', 'professional skills', 'core skills', 'kỹ năng', 'kỹ năng chuyên môn', 'kỹ năng kỹ thuật'),
    'experience': ('experience', 'work experience', 'professional experience', 'employment', 'kinh nghiệm', 'kinh nghiệm làm việc', 'kinh nghiệm công tác'),
    'education': ('education', 'academic background', 'học vấn', 'trình độ học vấn'),
    'project': ('projects', 'project', 'personal projects', 'dự án', 'dự án cá nhân'),
    'certifications': ('certifications', 'certificates', 'chứng chỉ', 'chứng nhận'),
    'references': ('references', 'người giới thiệu', 'người tham chiếu'),
    'awards': ('awards', 'honors', 'honors and awards', 'danh hiệu và giải thưởng', 'giải thưởng'),
    'summary': ('summary', 'profile', 'objective', 'career objective', 'giới thiệu', 'tóm tắt', 'mục tiêu nghề nghiệp'),
    'involvement': ('activities', 'involvement', 'volunteering', 'hoạt động', 'hoạt động ngoại khóa'),
    'contact': ('contact', 'personal information', 'contact information', 'thông tin cá nhân', 'thông tin liên hệ'),
}


def section_kind(line):
    value = unicodedata.normalize('NFC', line).strip().casefold().rstrip(':：')
    value = re.sub(r'^\d+[.)]\s*', '', value)
    return next((kind for kind, names in HEADINGS.items() if value in names), None)


def _split_items(value):
    parts, start, depth = [], 0, 0
    for index, char in enumerate(value):
        if char in '([': depth += 1
        elif char in ')]': depth = max(0, depth - 1)
        elif char in ',;•' and depth == 0:
            parts.append(value[start:index].strip()); start = index + 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def explicit_skills(text):
    """None means no explicit section; an empty list means an explicitly empty section."""
    found, active, pending, rows = False, False, [], []
    def flush():
        if pending:
            rows.append(' '.join(pending)); pending.clear()
    for raw in text.splitlines():
        line = raw.strip()
        inline = re.match(r'^(technical skills|skills|kỹ năng(?: chuyên môn| kỹ thuật)?)\s*[:：]\s*(.*)$', line, re.I)
        kind = 'skills' if inline else section_kind(line)
        if kind:
            flush()
            if kind == 'skills':
                active = found = True
                line = inline.group(2) if inline else ''
            elif active:
                active = False
            else:
                continue
        if not active: continue
        if not line:
            flush(); continue
        marker = bool(re.match(r'^[•●▪◦*✨★✦\-–]', line))
        line = re.sub(r'^[\s•●▪◦*✨★✦\-–]+', '', line).strip()
        if not line or all(unicodedata.category(c) == 'Co' for c in line): continue
        if marker: flush()
        if pending and sum(part.count('(') + part.count('[') - part.count(')') - part.count(']') for part in pending) <= 0:
            flush()
        pending.append(line)
    flush()
    if not found: return None
    grouped, seen = {}, set()
    for row in rows:
        group, value = 'Chuyên môn' if 'kỹ năng' in text.casefold() else 'Skills', row
        if ':' in row or '：' in row:
            group, value = re.split(r'[:：]', row, maxsplit=1)
        else:
            match = re.fullmatch(r'([^()]+)\((.*)\)', row)
            if match: group, value = match.groups()
        for item in _split_items(value):
            normalized = unicodedata.normalize('NFC', item).casefold()
            if normalized not in seen and len(item) <= 180:
                grouped.setdefault(group.strip() or 'Skills', []).append(item)
                seen.add(normalized)
    return [SkillGroup(group=group, items=items) for group, items in grouped.items()]
