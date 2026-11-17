"""Local dataset review, isolated from candidate records and training."""
import re
from fastapi import APIRouter, HTTPException,Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from ai.training.review_store import ReviewStore,ROOT

PACKS={'topcv':('TopCV · CV tổng hợp',None),'external-tailoring':('IterateCV · tailor/review','tailoring'),'external-matching':('Matching · nhãn tổng thể','matching'),'tailor-clean':('IterateCV · kiểm tra từng câu v3','@clean'),'tailor-expanded':('IterateCV · tập mở rộng, chưa duyệt','@expanded')}

def get_store(pack):
    if pack=='topcv':return ReviewStore()
    if pack not in PACKS:raise ValueError('Unknown reviewer pack')
    branch=PACKS[pack][1]
    if branch=='@clean':return ReviewStore(ROOT/'ai/data/processed/tailor-clean-v3',ROOT/'ai/data/reviews/tailor-clean-v3')
    if branch=='@expanded':return ReviewStore(ROOT/'ai/data/processed/tailor-expanded-v1',ROOT/'ai/data/reviews/tailor-expanded-v1')
    return ReviewStore(ROOT/'ai/data/processed/external-research-v1'/branch,ROOT/'ai/data/reviews/external-research-v1'/branch)

router=APIRouter(prefix='/api/data-review',tags=['local data review'])

class Change(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=0)
    annotation:dict
    action:str=Field(default='draft',pattern='^(draft|skip|approve)$')
    reviewer:str=Field(default='',max_length=200)
    confirmed:bool=False

class PairCheck(BaseModel):
    model_config=ConfigDict(extra='forbid')
    proposal_id:str=Field(pattern='^[a-f0-9]{24}$')
    source_ref:str=''
    proposed_text:str=Field(max_length=20000)
    reason:str=Field(max_length=20000)

class Version(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=0)

class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    pair_ids:list[str]=Field(min_length=1,max_length=10)


def run(operation,pack='topcv'):
    try:return operation(get_store(pack))
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(status_code=409,detail=str(e)) from None

@router.get('/packs')
def packs():
    return {'packs':[{'id':key,'title':title} for key,(title,branch) in PACKS.items() if branch is None or ((ROOT/'ai/data/processed/tailor-clean-v3/manifest.json') if branch=='@clean' else (ROOT/'ai/data/processed/tailor-expanded-v1/manifest.json') if branch=='@expanded' else ROOT/'ai/data/processed/external-research-v1'/branch/'manifest.json').exists()]}

@router.get('')
def listing(pack:str='topcv',batch:int=Query(default=0,ge=0)):
    def page(s):
        keys=s.all_review_keys();pages=max(1,(len(keys)+9)//10)
        if batch>=pages:raise ValueError('Đợt duyệt không tồn tại')
        return {'samples':s.summary(keys[batch*10:batch*10+10]),'cohort':s.cohort,'task':s.manifest.get('task','tailor_review'),'batch':batch,'batches':pages,'total':len(keys)}
    return run(page,pack)

@router.get('/samples/{key}')
def sample(key:str,pack:str='topcv'):return run(lambda s:{'packet':s.packets[key] if key in s.all_review_keys() else s.path(key),'progress':s.progress(key),'validation':s.validation(key)},pack)

@router.put('/samples/{key}')
def save(key:str,body:Change,pack:str='topcv'):return run(lambda s:{'progress':s.save(key,body.version,body.annotation,body.action,body.reviewer,body.confirmed),'validation':s.validation(key)},pack)

@router.post('/samples/{key}/validate')
def validate(key:str,pack:str='topcv'):return run(lambda s:s.validation(key),pack)

@router.post('/samples/{key}/check-pair')
def check_pair(key:str,body:PairCheck,pack:str='topcv'):
    def check(store):
        from ai.training.tailor_clean import assess_pair,word_diff
        packet=store.packet(key)
        pairs={p['id']:p for p in packet.get('cleaning',{}).get('pairs',[])}
        if body.proposal_id not in pairs:raise ValueError('Unknown proposal')
        pair=pairs[body.proposal_id]
        original=packet['catalog'].get(body.source_ref) or pair.get('original_text') or pair.get('comparison_original_text') or ''
        from ai.agents.cv_grounding import grounded_rewrite
        return {'runtime_guard_pass':grounded_rewrite(original,body.proposed_text),'assessment':assess_pair(packet,pair,body.proposed_text,body.source_ref or None,body.reason),'diff':word_diff(original,body.proposed_text)}
    return run(check,pack)

@router.post('/samples/{key}/prelabel')
def prelabel(key:str,body:Version,pack:str='topcv'):
    def generate(store):
        progress=store.progress(key)
        if progress['version']!=body.version:raise ValueError('Tiến độ đã thay đổi, tải lại trước khi gợi ý AI')
        if progress['annotation']['status']=='approved':raise ValueError('Lưu thành bản nháp trước khi chạy lại AI')
        from ai.agents.jd_agent import analyze_job_description
        from ai.agents.cv_agent import plan_cv,bullet_catalog
        from backend.app.schemas.cv import CVDocument
        packet=store.packets[key]
        requirements,warnings=analyze_job_description(packet['job']['description'])
        labels=[]
        fields=('required_skills','preferred_skills','unspecified_skills','experience_requirements','education_requirements','technical_requirements','certifications','languages')
        for field in fields:
            for item in getattr(requirements,field):
                labels.append({'name':getattr(item,'name',None) or item.description,'field':field,'requirement_type':item.requirement_type,'job_evidence':item.evidence,'status':'unknown','evidence_refs':[],'rationale':'AI: chưa có bằng chứng CV được reviewer đối chiếu.'})
        matching=packet.get('task')=='matching'
        annotation={k:v for k,v in progress['annotation'].items() if k in {'source_usage_confirmed','cv_usage_confirmed','matching_overall_label','matching_rationale','pair_decisions','partial_plan_review_confirmed'}}
        if matching or packet.get('cleaning'):
            annotation['cv_plan']=progress['annotation']['cv_plan']
        else:
            selected,review=plan_cv(CVDocument.model_validate(packet['cv']),requirements.model_dump(mode='json'))
            kept=set(bullet_catalog(selected));review.items=[item for item in review.items if item.source_ref in kept]
            annotation['cv_plan']={'selected_refs':list(bullet_catalog(selected)),'review':review.model_dump()}
            annotation['cv_plan']['review']['warnings']=warnings+annotation['cv_plan']['review'].get('warnings',[])+['Gợi ý AI là nháp. Tất cả nhãn unknown cần bạn đối chiếu bằng chứng.']
        annotation.update(requirements=labels,requirement_groups=[g.model_dump(exclude={'id','requirement_ids'}) for g in requirements.requirement_groups])
        if packet.get('source_record'):annotation['conversion_review_confirmed']=False
        from backend.app.core.config import settings
        from ai.agents.jd_extraction import JD_PROMPT_VERSION
        from ai.prompts.cv_prompt import CV_PROMPT_VERSION
        model_metadata={'status':'model_draft','model':settings.jd_model,'cv_model':None if matching or packet.get('cleaning') else settings.cv_model,'jd_prompt_version':JD_PROMPT_VERSION,'cv_prompt_version':None if matching or packet.get('cleaning') else CV_PROMPT_VERSION,'requirements':labels,'requirements_payload':requirements.model_dump(mode='json'),'warnings':warnings,'overall_label_generated':False}
        saved=store.save(key,body.version,annotation,'draft',origin='ai',model_metadata=model_metadata)
        return {'progress':saved,'validation':store.validation(key)}
    try:return run(generate,pack)
    except HTTPException:raise
    except Exception:raise HTTPException(status_code=503,detail='AI chưa hoàn tất. Bản đã lưu được giữ nguyên; bạn có thể thử lại hoặc gán nhãn thủ công.') from None

@router.post('/export')
def export(body:Selection,pack:str='topcv'):
    result=run(lambda s:s.export(body.pair_ids),pack)
    result['download_url']+='?pack='+pack
    return result

@router.get('/exports/{ident}')
def download(ident:str,pack:str='topcv'):
    if not re.fullmatch('[a-f0-9]{32}',ident):raise HTTPException(404)
    path=run(lambda s:s.root,pack)/'exports'/ident/'reviewed.jsonl'
    if not path.is_file():raise HTTPException(404)
    return FileResponse(path,media_type='application/x-ndjson',filename='reviewed-'+ident[:8]+'.jsonl')
