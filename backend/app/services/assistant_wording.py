"""Role wording advice is a proposal, never an automatic new CV fact."""
import hashlib
import json
import re
from copy import deepcopy
from backend.app.schemas.profile import MasterProfile
from backend.app.services.assistant_answers import fold, clarification_topic


def wording_request(text, path=''):
    plain = fold(' '.join(text.split()))
    query = bool(re.search(r'\b(?:viet|ghi|dien|dien dat|mo ta|goi)\b.{0,65}\b(?:gi|the nao|ra sao|phu hop|chuyen nghiep|ngan gon)\b',plain))
    role = clarification_topic(text)=='role' or (path.endswith(('.role','.job_title')) and not re.search(r'\bcv\b',plain) and clarification_topic(text) is None)
    return query and role


def suggestion_acceptance(text):
    plain = fold(' '.join(text.split())).strip(' .!')
    if plain in {'ap dung','dong y'}: return True
    return bool(re.fullmatch(r'(?:(?:dung roi|ok|duoc|u),? )?(?:dung|su dung|chon|lay|ghi|viet|dien|ap dung|cap nhat) (?:cau (?:nay|do)|goi y (?:nay|do)|nhu vay|vay)(?: vao cv)?(?: giup (?:minh|toi|em))?(?: di| nhe| nha| a)?',plain))


def fingerprint(entry):
    return hashlib.sha256(json.dumps(entry,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def propose_role(intake, text, path):
    projects = intake['profile']['project']
    parts = path.split('.')
    index = int(parts[1]) if len(parts)==3 and parts[0]=='project' and parts[1].isdigit() else (0 if len(projects)==1 else None)
    if index is None or index >= len(projects):
        return 'Bạn muốn gợi ý câu chữ cho dự án nào? Bạn nhắc tên dự án nhé; mình sẽ giữ nguyên thông tin hiện tại.',None
    entry = projects[index]
    plain = fold(' '.join([text,entry.get('role') or '']))
    all_work = bool(re.search(r'\b(?:lam het|toan bo|tat ca|mot minh|tu lam)\b',plain))
    if all_work:
        personal = 'du an ca nhan' in plain or 'ca nhan' in fold(entry.get('project_type') or '')
        value = 'Tự thực hiện toàn bộ dự án' + (' cá nhân' if personal else '')
        explanation = 'Cách này mô tả phạm vi bạn đảm nhận; không cần tự gán chức danh trưởng nhóm hay full-stack, và cũng chưa khẳng định các công nghệ hoặc công việc cụ thể.'
    elif entry.get('role'):
        value = entry['role']
        explanation = 'Bạn có thể dùng mô tả phần mình thực sự phụ trách thay vì đặt thêm chức danh.'
    else:
        return 'Vai trò nên ghi bằng phần bạn thực sự phụ trách, không cần một chức danh lớn. Bạn kể phần mình làm, mình sẽ giúp diễn đạt lại gọn hơn; bản nháp hiện tại chưa thay đổi.',None
    reply = f'Với trường hợp bạn mô tả, có thể ghi vai trò: “{value}”. {explanation} Đây mới là gợi ý, chưa áp dụng vào CV. Nếu câu này đúng với bạn, nhắn “dùng câu này” để áp dụng.'
    return reply,dict(section='project',index=index,field='role',value=value,entry_fingerprint=fingerprint(entry))


def confirm_role(intake, text):
    result = deepcopy(intake)
    if not suggestion_acceptance(text): return result,'Mình chưa áp dụng gợi ý vì bạn chưa xác nhận dùng câu này.',False
    proposal = result.pop('pending_role_wording',None)
    if not proposal:
        return result,'Hiện chưa có câu gợi ý cụ thể để áp dụng. Bạn muốn mình gợi ý cách viết vai trò cho dự án nào?',False
    index = proposal['index']
    entries = result['profile']['project']
    if index >= len(entries) or fingerprint(entries[index]) != proposal['entry_fingerprint']:
        return result,'Thông tin dự án đã thay đổi sau lúc mình gợi ý. Mình chưa áp dụng câu cũ; bạn có thể yêu cầu gợi ý lại theo thông tin mới.',False
    entries[index]['role'] = proposal['value']
    result['profile'] = MasterProfile.model_validate(result['profile']).model_dump(mode='json')
    result['skipped'] = [p for p in result.get('skipped',[]) if p not in {'project',f'project.{index}.role'}]
    result['revision'] = result.get('revision',0)+1
    result.pop('draft_id',None)
    result['last_wording_confirmation'] = dict(index=index,value=proposal['value'],confirmation=text)
    return result,f'Đã áp dụng vai trò “{proposal["value"]}” theo xác nhận của bạn.',True
