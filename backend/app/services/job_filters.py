"""Source-only job filters shared by JSON and PostgreSQL candidate queries."""
from backend.app.schemas.dashboard import JobPosting


def matches(job: JobPosting, *, q='', location='', employment_type='', workplace_type='',
            saved=False, source_name='', industry='', experience_level='', salary_min=None,
            salary_currency='VND', salary_period='month'):
    # All query words must occur; punctuation (C++, .NET) stays literal.
    text = ' '.join(filter(None, [job.title, job.company, job.description])).casefold()
    if any(word.casefold() not in text for word in q.split()):
        return False
    for field, value in [('location', location), ('employment_type', employment_type),
                         ('workplace_type', workplace_type), ('source_name', source_name),
                         ('industry', industry), ('experience_level', experience_level)]:
        if value and getattr(job, field) != value:
            return False
    if saved and not job.saved:
        return False
    if salary_min is not None:
        # Filter on the disclosed floor, not an optimistic upper bound. Unknown
        # currency/periods cannot be compared, and no FX conversion is implied.
        if job.salary_min is None or job.salary_min < salary_min or job.salary_currency != salary_currency or job.salary_period != salary_period:
            return False
    return True
