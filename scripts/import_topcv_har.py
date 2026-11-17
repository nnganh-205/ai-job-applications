"""Extract public TopCV JobPosting JSON-LD from a browser-exported HAR.

Default is dry-run. Only normalized job documents and manifest are persisted;
request headers, cookies, POST bodies and unrelated responses are never copied.
"""
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit,urlunsplit
from bs4 import BeautifulSoup
from backend.app.schemas.dashboard import JobPosting
from backend.app.db.job_posting_repository import posting_id,source_hash,utc_now
from backend.app.services.job_importer import description_text, salary_metadata


def visible_metadata(soup,data):
    """Read the same header labels a visitor sees, retaining JSON-LD conflicts."""
    values={}
    for block in soup.select('.list-info__content'):
        label=block.select_one('.list-info__content__title')
        value=block.select_one('.list-info__content__desc')
        if label and value:
            values.setdefault(label.get_text(' ',strip=True),set()).add(value.get_text(' ',strip=True))
    def only(label):
        found=values.get(label,set())
        return next(iter(found)) if len(found)==1 else None
    structured=data.get('validThrough')
    expiry=structured;display=only('Hạn ứng tuyển');source='structured_data';conflict=False
    if display:
        try:
            day=datetime.strptime(display,'%d/%m/%Y')
            # The source publishes a calendar date, normalized to end-of-day VN.
            expiry=day.replace(hour=23,minute=59,second=59,tzinfo=ZoneInfo('Asia/Ho_Chi_Minh')).isoformat()
            source='visible_page'
            if structured:conflict=datetime.fromisoformat(structured.replace('Z','+00:00')).date()!=day.date()
        except ValueError:
            pass
    places=data.get('jobLocation') or [];places=places if isinstance(places,list) else [places]
    regions=list(dict.fromkeys(str(p.get('address',{}).get('addressRegion')) for p in places if p.get('address',{}).get('addressRegion')))
    return dict(location=only('Địa điểm') or ', '.join(regions) or None,experience_level=only('Kinh nghiệm') or (data.get('experienceRequirements') if isinstance(data.get('experienceRequirements'),str) else None),expires_at=expiry,structured_expires_at=structured,source_expires_at_text=display,expiry_source=source,expiry_conflict=conflict)


def extract(entry):
    parsed=urlsplit(entry['request']['url'])
    match=re.fullmatch(r'/viec-lam/[^/]+/(\d+)\.html',parsed.path)
    if parsed.hostname not in {'www.topcv.vn','topcv.vn'} or not match or entry['response']['status']!=200:return None
    content=entry['response'].get('content',{})
    raw=content.get('text','')
    if content.get('encoding')=='base64':raw=base64.b64decode(raw,validate=True).decode('utf-8')
    soup=BeautifulSoup(raw,'html.parser')
    data=None
    for script in soup.find_all('script',type='application/ld+json'):
        try:candidate=json.loads(script.get_text())
        except ValueError:continue
        candidates=candidate if isinstance(candidate,list) else [candidate]
        for row in candidates:
            if isinstance(row,dict) and row.get('@type')=='JobPosting':data=row;break
        if data:break
    if data is None:raise ValueError('Không có JobPosting JSON-LD')
    url=urlunsplit(('https','www.topcv.vn',parsed.path,'',''))
    org=data.get('hiringOrganization') or {}
    places=data.get('jobLocation') or [];places=places if isinstance(places,list) else [places]
    addresses=[]
    for place in places:
        address=place.get('address',{})
        addresses.append(', '.join(str(address[k]) for k in ('streetAddress','addressLocality','addressRegion','addressCountry') if address.get(k)))
    salary=data.get('baseSalary') or {};amount=salary.get('value') or {};salary_text=None
    if isinstance(amount,dict):
        bounds=[str(amount[k]) for k in ('minValue','maxValue','value') if amount.get(k) is not None]
        if bounds:salary_text=' - '.join(bounds)+' '+str(salary.get('currency',''))+' / '+str(amount.get('unitText','chưa rõ kỳ lương'))
    if not isinstance(amount,dict):amount={}
    job=JobPosting(posting_id=posting_id('TopCV','',match[1]),external_id=match[1],title=BeautifulSoup(data['title'],'html.parser').get_text(' ',strip=True),company=org.get('name'),description=description_text(data['description']),work_locations=[a for a in addresses if a],salary=salary_text,**salary_metadata(amount.get('minValue',amount.get('value')),amount.get('maxValue',amount.get('value')),salary.get('currency'),amount.get('unitText')),
        industry=data.get('industry') if isinstance(data.get('industry'),str) else None,
        **visible_metadata(soup,data),employment_type={'FULL_TIME':'full-time','PART_TIME':'part-time','INTERN':'internship','CONTRACTOR':'contract'}.get(data.get('employmentType')),source_name='TopCV',source_url=url,apply_url=url,fetched_at=entry['startedDateTime'],imported_at=utc_now(),source_created_at=data.get('datePosted'),import_method='fetch')
    job.content_hash=source_hash(job)
    checks={name:any(label in job.description for label in labels) for name,labels in [('description',('Mô tả công việc','Job Description')),('requirements',('Yêu cầu ứng viên','Candidate Requirements')),('benefits',('Quyền lợi','Benefits'))]}
    return job,checks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('har',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--apply',action='store_true');parser.add_argument('--tech-only',action='store_true')
    args=parser.parse_args()
    from backend.app.db import database
    from backend.app.db.job_posting_repository import upsert_posting
    if args.apply and not database.enabled():raise SystemExit('--apply requires KLTN_STORAGE=postgres')
    har=json.loads(args.har.read_text());jobs={};manifest=[]
    for entry in har.get('log',{}).get('entries',[]):
        try:
            result=extract(entry)
            if result is None:continue
            job,checks=result
            tech=bool(re.search(r'python|developer|tester|kiểm thử|lập trình|devops|software|data engineer|ai engineer|techlead',job.title,re.I))
            if args.tech_only and not tech:continue
            if args.apply and not all(checks.values()):raise ValueError('Missing required JD sections')
            identity=(job.posting_id,job.content_hash)
            duplicate=identity in jobs
            jobs[identity]=job
            status='duplicate' if duplicate else 'normalized'
            if args.apply and not duplicate:_,status=upsert_posting(job)
            manifest.append(dict(source_url=job.source_url,external_id=job.external_id,fetched_at=job.fetched_at,content_hash=job.content_hash,method='browser-har-jsonld',status=status,section_checks=checks,expiry_source=job.expiry_source,structured_expires_at=job.structured_expires_at,visible_expiry=job.source_expires_at_text,expiry_conflict=job.expiry_conflict))
        except (ValueError,KeyError,TypeError) as error:
            manifest.append(dict(status='invalid',error=type(error).__name__))
    args.output.mkdir(parents=True,exist_ok=True)
    payload='\n'.join(job.model_dump_json() for job in jobs.values())+'\n'
    (args.output/'jobs.jsonl').write_text(payload)
    (args.output/'manifest.json').write_text(json.dumps({'normalizer_version':'topcv-har-v2','mode':'apply' if args.apply else 'dry_run','unique_jobs':len({job.posting_id for job in jobs.values()}),'snapshots':len(jobs),'sha256':hashlib.sha256(payload.encode()).hexdigest(),'entries':manifest,'usage':'Local research/demo; source attribution retained; redistribution rights not established.'},ensure_ascii=False,indent=2))
    print(json.dumps({'unique_jobs':len({job.posting_id for job in jobs.values()}),'snapshots':len(jobs),'mode':'apply' if args.apply else 'dry_run','invalid':sum(r['status']=='invalid' for r in manifest)}))


if __name__=='__main__':main()
