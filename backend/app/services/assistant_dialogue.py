"""Explicit dialogue focus for resolving follow-up questions across chat turns."""
import re
from backend.app.services.assistant_answers import fold, entry_reference


def dialogue_context(intake, path, messages=None):
    parts = path.split('.')
    section = parts[0]
    index = int(parts[1]) if len(parts)==3 and parts[1].isdigit() else None
    entries = intake['profile'].get(section, [])
    entry = entries[index] if isinstance(entries,list) and index is not None and index < len(entries) else None
    field = parts[-1] if len(parts) > 1 else None
    action = 'add_optional_detail_to_existing_entry' if field=='work' else ('review_existing_entry' if field=='review' else 'fill_current_field')
    last = next((m for m in reversed(messages or []) if m.get('role')=='assistant'),None)
    previous = intake.get('dialogue_focus') or {}
    return dict(section=section,index=index,field=field,action=action,
                entity=entry_reference(intake['profile'],section,index) if entry is not None else None,
                known_role=(entry or {}).get('role'),
                previous_request=previous,
                last_assistant_message=(last or {}).get('text','')[:1400],
                recent_user_messages=[m.get('text','')[:600] for m in (messages or []) if m.get('role')=='user'][-4:],
                rule='Các câu hỏi lại về thêm/sửa/cái đó phải gắn với yêu cầu và đối tượng vừa nói. Bổ sung mô tả cho một dự án đã có KHÔNG phải yêu cầu thêm dự án khác. Không dùng câu hỏi làm dữ kiện CV.')


def followup_question(text):
    plain = fold(' '.join(text.split())).strip(' .!?…')
    asks = bool(re.search(r'\b(?:nghia la|y la|co phai|phai khong|dung khong)\b|\b(?:a|ha|nhi|vay)$|[?]',fold(text)))
    # A request to create another entry is different from checking what we meant.
    if re.search(r'\b(?:minh|toi|em|to) (?:muon|dinh|se|co the)\b',plain) and not re.search(r'\b(?:nghia la|y la|co phai)\b',plain):
        return False
    extra = bool(re.search(r'\b(?:them|bo sung|lam them|tao them)\b.{0,45}\b(?:du an|do an|muc|cai|cong viec)\b.{0,25}\b(?:khac|moi|nua)\b',plain))
    old = bool(re.search(r'\b(?:y la|nghia la|co phai)\b.{0,45}\b(?:cai cu|du an cu|du an do|vua ke|dang co)\b',plain))
    location = bool(re.search(r'\b(?:cau|goi y|cach viet) (?:do|nay)\b.{0,40}\b(?:o dau|cho nao|muc nao)\b',plain))
    return (asks and (extra or old)) or location


def resolve_followup(intake, path, text, messages=None):
    if not followup_question(text): return None
    frame = dialogue_context(intake,path,messages)
    proposal = intake.get('pending_role_wording')
    plain = fold(text)
    if proposal and re.search(r'\b(?:cau|goi y|cach viet) (?:do|nay)\b',plain):
        index=proposal['index']
        return f'Câu gợi ý “{proposal["value"]}” dùng cho ô Vai trò của {entry_reference(intake["profile"],"project",index)}, không phải một dự án mới. Câu này chưa được áp dụng; nếu thấy đúng, bạn có thể nhắn “dùng câu này”.'
    if frame['entity'] and frame['action']=='add_optional_detail_to_existing_entry':
        role = ' Phạm vi bạn đảm nhận đã được ghi nhận rồi.' if frame['known_role'] else ''
        return f'Không phải thêm dự án khác nhé. Mình đang nói tiếp về {frame["entity"]} bạn đã kể.{role} Câu vừa rồi chỉ hỏi bạn có muốn bổ sung một việc hoặc kết quả cho chính thông tin đó để CV rõ hơn không. Đây là tùy chọn; nếu chưa muốn bổ sung, nhắn “để sau”. Dự án hiện tại vẫn được giữ nguyên.'
    if frame['entity']:
        return f'Mình vẫn đang hỏi về {frame["entity"]} đã có, không yêu cầu tạo dự án hay mục mới. Bạn có thể bổ sung hoặc làm rõ thông tin cho chính mục này; các dữ kiện đã nhập không thay đổi.'
    if frame['section']=='project' and not intake['profile']['project']:
        return 'Mình đang hỏi dự án đầu tiên bạn muốn đưa vào CV, không yêu cầu phải có nhiều dự án. Bạn có thể kể một dự án cá nhân hoặc đồ án ở trường; nếu chưa có, cứ nói “chưa có”.'
    focus = intake.get('dialogue_focus') or {}
    if focus.get('entity'):
        return f'Câu trước vẫn nói về {focus["entity"]}, không yêu cầu thêm dự án khác. Hiện bạn có thể tiếp tục phần đang nhập hoặc nói rõ muốn quay lại bổ sung mục nào; thông tin cũ vẫn được giữ nguyên.'
    return 'Bạn đang hỏi có cần thêm một dự án khác hay chỉ bổ sung thông tin cho dự án đã kể? Mình chưa thêm hoặc thay đổi mục nào; bạn nhắc tên dự án để mình giải thích đúng ý nhé.'
