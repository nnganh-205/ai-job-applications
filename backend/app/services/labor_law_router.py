import re
import unicodedata


def is_law_question(text):
    plain=''.join(c for c in unicodedata.normalize('NFD',text.casefold()) if not unicodedata.combining(c)).replace('đ','d')
    law=re.search(r'\b(luat lao dong|bo luat lao dong|nghi dinh|dieu luat|phap luat lao dong|bao hiem xa hoi|bao hiem that nghiep|luong toi thieu|hop dong lao dong)\b',plain)
    topic=re.search(r'\b(nghi phep|nghi viec|thu viec|tang ca|lam them gio|sa thai|cham dut hop dong|tro cap thoi viec)\b',plain)
    question=re.search(r'[?]|\b(duoc|co phai|bao nhieu|quy dinh|the nao|theo luat|quyen loi|hop phap)\b',plain)
    return bool(law or (topic and question))
