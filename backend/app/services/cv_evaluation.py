"""Project only visible CV text into the existing evidence engine; never load hidden profile facts."""
import re
from backend.app.schemas.profile import MasterProfile


def displayed_profile(document):
    data=dict(contact=document.contact.model_dump(),experience=[],project=[],education=[],involvement=[],skills=[],summary=None)
    refs={}
    for si,section in enumerate(document.sections):
        for ei,entry in enumerate(section.entries):
            kind=section.kind;index=len(data[kind]);base=f'/{kind}/{index}';cv=f'/document/sections/{si}/entries/{ei}'
            texts=[b.text for b in entry.bullets]
            fields={}
            if kind=='skills':fields={'group':entry.title,'items':texts}
            elif kind=='education':fields={'institution':entry.title,'degree':entry.subtitle,'field_of_study':entry.subtitle,'details':texts}
            elif kind=='experience':fields={'job_title':entry.title,'company':entry.subtitle,'description':texts}
            elif kind=='project':fields={'project_name':entry.title,'role':entry.subtitle,'description':texts}
            elif kind=='involvement':fields={'role':entry.title,'organization':entry.subtitle,'description':texts}
            if kind!='skills' and entry.period:
                dates=re.fullmatch(r'(.+?)\s+[–-]\s+(.+)',entry.period)
                if dates:
                    fields.update(start_date=dates[1],end_date=dates[2])
            data[kind].append(fields)
            for field,value in fields.items():
                if isinstance(value,list):
                    for bi in range(len(value)):refs[f'{base}/{field}/{bi}']=f'{cv}/bullets/{bi}/text'
                else:refs[f'{base}/{field}']=f'{cv}/'+('period' if field in {'start_date','end_date'} else 'title' if value==entry.title else 'subtitle')
            # Degree assessor may emit all three paths, including a missing major.
            if kind=='education':
                for field in ('degree','major','field_of_study'):refs[f'{base}/{field}']=f'{cv}/subtitle'
    return MasterProfile.model_validate(data),refs


def visible_evidence(result,refs):
    def convert(value):
        if isinstance(value,dict):
            return {k:([refs[ref] for ref in v if ref in refs] if k=='evidence_refs' else convert(v)) for k,v in value.items()}
        if isinstance(value,list):return [convert(v) for v in value]
        return value
    return type(result).model_validate(convert(result.model_dump(mode='json')))
