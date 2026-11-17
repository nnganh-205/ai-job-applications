"""Conservative object anchors for CV rewrites, not a semantic truth classifier.

Closed equivalences let formatting/wording change while retaining the kind of
thing the user worked on. Source citations alone cannot establish this.
"""
import re
import unicodedata


ANCHORS={
 'phone_contact':(r'\bgọi điện\b',r'\bđiện thoại\b',r'\bphone\b',r'\btelephone\b'),
 'email_contact':(r'\bemail\b',r'\be-mail\b',r'\bthư điện tử\b'),
 'in_person':(r'\btrực tiếp gặp\b',r'\bin person\b'),
 'identifier':(r'\bmã\b(?!\s+nguồn\b)',r'\b(?:id|identifier)\b'),
 'source_code':(r'\bmã nguồn\b',r'\bsource code\b'),
 'parcel':(r'\bkiện hàng\b',r'\bparcels?\b',r'\bpackages?\b'),
 'invoice':(r'\bhóa đơn\b',r'\bhoá đơn\b',r'\binvoices?\b'),
 'order':(r'\bđơn hàng\b',r'\borders?\b'),
 'record':(r'\bhồ sơ\b',r'\bdossiers?\b'),
 'form':(r'\bbiểu mẫu\b',r'\bforms?\b'),
 'slip':(r'\bphiếu\b',r'\bslips?\b'),
 'report':(r'\bbáo cáo\b',r'\breports?\b'),
 'document':(r'\btài liệu\b',r'\bdocuments?\b',r'\bdocumentation\b'),
 'instructions':(r'\bhướng dẫn\b',r'\binstructions?\b',r'\bguides?\b'),
 'label':(r'\bnhãn\b',r'\blabels?\b'),
 'signature':(r'\bchữ ký\b',r'\bsignatures?\b'),
 'feedback':(r'\bphản hồi\b',r'\bfeedback\b'),
 'equipment':(r'\bthiết bị\b',r'\bequipment\b',r'\bdevices?\b'),
 'supplies':(r'\bvật tư\b',r'\bsupplies\b'),
 'audio':(r'\bâm thanh\b',r'\baudio\b'),
 'image':(r'\bhình ảnh\b',r'\bảnh\b',r'\bimages?\b',r'\bphotos?\b'),
 'video':(r'\bvideos?\b',),
 'file':(r'\btệp\b',r'\bfiles?\b'),
 'dataset':(r'\bbộ dữ liệu\b',r'\bdatasets?\b'),
}


def content_anchors(text):
    text=unicodedata.normalize('NFC',text).casefold()
    return [name for name,patterns in ANCHORS.items() if any(re.search(p,text,re.I) for p in patterns)]


def missing_content_anchors(original,proposed):
    present=set(content_anchors(proposed))
    return [name for name in content_anchors(original) if name not in present]
