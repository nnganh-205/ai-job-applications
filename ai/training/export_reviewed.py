"""Export human-approved CVPlan packets. Pending/model-only labels cannot train."""
import argparse
import hashlib
import json
from pathlib import Path
from ai.training.review_pack import assert_isolated,load_verified
from ai.training.prepare_data import validate_example
from ai.prompts.cv_prompt import CV_REVIEW_PROMPT,CV_PROMPT_VERSION
from ai.agents.cv_grounding import job_brief,catalog_context,GUARD_VERSION
from backend.app.schemas.job import JobRequirements

POLICY='cv-identity-and-jd-group-v1'

def verify_approval(packet):
    if packet.get('split_policy')!=POLICY or packet.get('split') not in {'train','validation','test'}:
        raise ValueError('Original grouped split metadata is required')
    annotation=packet.get('annotation',{})
    reviewers=annotation.get('reviewer_ids',[])
    if annotation.get('status')!='approved' or not reviewers or not all(isinstance(v,str) and v.strip() for v in reviewers):
        raise ValueError('Human approval and reviewer IDs are required')
    if annotation.get('source_usage_confirmed') is not True:
        raise ValueError('Source usage must be confirmed by the reviewer')
    if packet.get('synthetic_cv') is not True and annotation.get('cv_usage_confirmed') is not True:
        raise ValueError('Real CV usage needs explicit training consent')
    return reviewers


def approved_example(packet):
    if packet.get('task')=='matching':raise ValueError('Matching labels are not CVPlan answers')
    reviewers=verify_approval(packet)
    annotation=packet['annotation']
    requirements=validate_content(packet)
    catalog=packet['catalog']
    from backend.app.schemas.cv import CVDocument
    payload={'catalog_context':catalog_context(CVDocument.model_validate(packet['cv'])),'mode':'generate','review_language':packet['cv']['language'],'catalog':catalog,'job_requirements':job_brief(requirements.model_dump(mode='json'))}
    row={'messages':[{'role':'system','content':CV_REVIEW_PROMPT},{'role':'user','content':json.dumps(payload,ensure_ascii=False)},{'role':'assistant','content':json.dumps(annotation['cv_plan'],ensure_ascii=False)}],
         'split_policy':POLICY,'split':packet['split'],'cv_identity':packet['cv_identity'],'jd_group':packet['jd_group'],
         'synthetic_cv':packet.get('synthetic_cv') is True,'cv_usage_confirmed':annotation.get('cv_usage_confirmed') is True,'review_status':'approved','reviewer_ids':reviewers,'source_usage_confirmed':True,'prompt_version':CV_PROMPT_VERSION,
         'source_hash':packet['job']['content_hash'],'pair_id':packet['pair_id']}
    row['guard_version']=GUARD_VERSION
    if packet.get('cleaning'):row['cleaning_provenance']={k:packet['cleaning'][k] for k in ('version','guard_version','scope','complete_original_target','corpus_registry')}
    if packet.get('cleaning'):row['corpus_registry']=packet['cleaning']['corpus_registry']
    for key in ('source_record','source_record_sha256','label_provenance'):
        if key in packet:row[key]=packet[key]
    return validate_example(row)


def validate_content(packet):
    """Validate human content independently of source permission; never invent approval."""
    annotation=packet.get('annotation',{})
    if packet.get('cleaning'):
        from ai.training.tailor_clean import validate_decisions
        validate_decisions(packet,annotation)
    matching=packet.get('task')=='matching'
    if packet.get('source_record') and annotation.get('conversion_review_confirmed') is not True:
        raise ValueError('Cần xác nhận đã đối chiếu nhãn gốc và các cảnh báo chuyển đổi')
    labels=annotation.get('requirements') or []
    if not labels and not matching:raise ValueError('Reviewed requirements are required')
    raw=packet['job']['description'];catalog=packet['catalog'];requirements={}
    fields={'required_skills','preferred_skills','unspecified_skills','experience_requirements','education_requirements','technical_requirements','certifications','languages'}
    for label in labels:
        if label.get('status') not in {'met','partially_met','unknown','not_met'}:raise ValueError('Invalid requirement status')
        if not label.get('job_evidence') or label['job_evidence'] not in raw:raise ValueError('JD evidence must be verbatim')
        field=label.get('field')
        if field not in fields:raise ValueError('Requirement field must match the runtime JD contract')
        kind=label.get('requirement_type')
        if kind not in {'required','preferred','unspecified'}:raise ValueError('Missing required/preferred/unspecified label')
        title=label.get('name')
        if not isinstance(title,str) or not title.strip():raise ValueError('Missing requirement name')
        if field in {'required_skills','preferred_skills','unspecified_skills'} and field!=kind+'_skills':raise ValueError('Requirement field/type mismatch')
        requirements.setdefault(field,[]).append({('description' if field in {'experience_requirements','education_requirements'} else 'name'):title,'evidence':label['job_evidence'],'requirement_type':kind})
        refs=label.get('evidence_refs',[])
        if any(ref not in catalog for ref in refs):raise ValueError('CV evidence ref is not visible')
        if label['status'] in {'met','partially_met'} and not refs:raise ValueError('Positive labels need CV evidence')
        if label['status']=='not_met' and not refs:raise ValueError('not_met needs explicit denial evidence; absence is unknown')
    requirements=JobRequirements(**requirements,job_description_raw=raw)
    groups=annotation.get('requirement_groups',[])
    names={label['name'] for label in labels}
    for group in groups:
        if not group.get('evidence') or group['evidence'] not in raw or not set(group.get('members',[]))<=names:
            raise ValueError('Nhóm AND/OR cần dẫn chứng JD nguyên văn và thành viên đã gán nhãn')
    requirements=JobRequirements(**requirements.model_dump(exclude={'requirement_groups'}),requirement_groups=groups)
    if matching:
        if annotation.get('matching_overall_label') not in {'Good Fit','Potential Fit','No Fit'} or not annotation.get('matching_rationale','').strip():
            raise ValueError('Cần nhãn phù hợp tổng thể do reviewer chọn và lý do')
        if not catalog or not packet.get('source_resume_text'):raise ValueError('Missing matching source')
        return requirements
    from backend.app.schemas.cv import CVPlan
    from ai.agents.cv_grounding import grounded_rewrite as review_text_valid
    plan=CVPlan.model_validate(annotation.get('cv_plan'))
    if not plan.selected_refs or len(set(plan.selected_refs))!=len(plan.selected_refs) or any(ref not in catalog for ref in plan.selected_refs):
        raise ValueError('Chọn ít nhất một bullet nguồn, không trùng lặp')
    if packet.get('cleaning') and len(plan.review.items)>5:raise ValueError('CV prompt v4 chỉ nhận tối đa 5 câu sửa mỗi plan')
    seen=set()
    for item in plan.review.items:
        if item.source_ref not in plan.selected_refs or item.source_ref in seen or item.original_text!=catalog.get(item.source_ref):
            raise ValueError('Đề xuất phải thuộc bullet đã chọn và khớp nguyên văn nguồn')
        seen.add(item.source_ref)
        if not item.reason.strip() or not review_text_valid(item.original_text,item.proposed_text):
            raise ValueError('Đề xuất thiếu lý do hoặc không qua kiểm tra dữ kiện nguồn')
    return requirements


def approved_matching_example(packet):
    reviewers=verify_approval(packet)
    if packet.get('task')!='matching':raise ValueError('Not a matching packet')
    validate_content(packet);a=packet['annotation']
    return {'contract':'matching-review-v1','split_policy':POLICY,'split':packet['split'],'cv_identity':packet['cv_identity'],'jd_group':packet['jd_group'],
            'pair_id':packet['pair_id'],'resume':packet['source_resume_text'],'job_description':packet['job']['description'],
            'original_label':packet['original_matching_label'],'reviewed_label':a['matching_overall_label'],'rationale':a['matching_rationale'],
            'requirement_labels':a.get('requirements',[]),'requirement_groups':a.get('requirement_groups',[]),'model_annotations':packet.get('model_annotations'),
            'label_provenance':packet['label_provenance'],'source_record':packet['source_record'],'source_record_sha256':packet['source_record_sha256'],
            'review_status':'approved','reviewer_ids':reviewers,'source_usage_confirmed':True,'cv_usage_confirmed':a.get('cv_usage_confirmed') is True,'synthetic_cv':packet.get('synthetic_cv') is True}


def approved_packet(packet):
    return approved_matching_example(packet) if packet.get('task')=='matching' else approved_example(packet)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pack',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--reviews',type=Path,help='Separate reviewer progress directory');p.add_argument('--approved-only',action='store_true');p.add_argument('--validate-only',action='store_true');args=p.parse_args()
    if not args.validate_only and args.output is None:p.error('--output is required unless --validate-only')
    if args.output and args.output.exists():raise SystemExit('Output exists; reviewer work will not be overwritten')
    try:manifest,by_id=load_verified(args.pack)
    except (ValueError,KeyError,TypeError) as error:raise SystemExit('Export refused: '+str(error)) from None
    packets=list(by_id.values())
    if args.reviews:
        from ai.training.review_store import ReviewStore
        store=ReviewStore(args.pack,args.reviews)
        packets=[store.packet(key) for key in store.all_review_keys()]
    if args.approved_only:packets=[packet for packet in packets if packet.get('annotation',{}).get('status')=='approved']
    try:rows=[approved_packet(packet) for packet in packets]
    except (ValueError,KeyError,TypeError) as error:raise SystemExit('Export refused: '+str(error)) from None
    if not rows:raise SystemExit('No approved data')
    content=''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows)
    if args.validate_only:
        print(json.dumps({'approved_rows':len(rows),'valid':True,'training_started':False}));return
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:f.write(content)
    print(json.dumps({'approved_rows':len(rows),'sha256':hashlib.sha256(content.encode()).hexdigest(),'split_policy':POLICY,'training_started':False}))

if __name__=='__main__':main()
