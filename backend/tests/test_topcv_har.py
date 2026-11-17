import json
import unittest
from scripts.import_topcv_har import extract


class TopCVHarTests(unittest.TestCase):
    def entry(self):
        data={'@type':'JobPosting','title':'Backend Engineer','description':'<h2>Mô tả công việc</h2><p>Python API</p><h2>Yêu cầu ứng viên</h2><p>SQL</p><h2>Quyền lợi</h2><p>Training</p>','identifier':{'value':777},'hiringOrganization':{'name':'Fixture Company'},'jobLocation':{'address':{'addressRegion':'Hà Nội'}},'validThrough':'2026-12-31T23:59:59+07:00'}
        return {'startedDateTime':'2026-11-09T00:00:00Z','request':{'url':'https://www.topcv.vn/viec-lam/backend-engineer/123456.html?tracking=fixture','headers':[{'name':'Cookie','value':'SECRET'}]},'response':{'status':200,'content':{'text':'<script>secret="SECRET"</script><script type="application/ld+json">'+json.dumps(data)+'</script>'}}}

    def test_job_identity_is_not_company_identifier(self):
        job,checks=extract(self.entry())
        self.assertEqual(job.external_id,'123456')
        self.assertTrue(all(checks.values()))
        self.assertNotIn('tracking',job.source_url)
        self.assertNotIn('SECRET',job.model_dump_json())

    def test_other_hosts_and_non_200_are_not_imported(self):
        entry=self.entry();entry['request']['url']=entry['request']['url'].replace('www.topcv.vn','example.com')
        self.assertIsNone(extract(entry))
        entry=self.entry();entry['response']['status']=403
        self.assertIsNone(extract(entry))

    def test_visible_header_retains_conflicting_structured_expiry(self):
        entry=self.entry()
        entry['response']['content']['text']+='<div class="list-info__content"><div class="list-info__content__title">Hạn ứng tuyển</div><div class="list-info__content__desc">30/11/2026</div></div><div class="list-info__content"><div class="list-info__content__title">Kinh nghiệm</div><div class="list-info__content__desc">2 năm</div></div>'
        job,_=extract(entry)
        self.assertEqual(job.expires_at,'2026-11-30T23:59:59+07:00')
        self.assertEqual(job.structured_expires_at,'2026-12-31T23:59:59+07:00')
        self.assertTrue(job.expiry_conflict)
        self.assertEqual(job.experience_level,'2 năm')
        self.assertEqual(job.expiry_source,'visible_page')

    def test_ambiguous_header_does_not_choose_arbitrary_date(self):
        entry=self.entry()
        for value in ('30/11/2026','01/12/2026'):
            entry['response']['content']['text']+='<div class="list-info__content"><div class="list-info__content__title">Hạn ứng tuyển</div><div class="list-info__content__desc">'+value+'</div></div>'
        job,_=extract(entry)
        self.assertEqual(job.expires_at,'2026-12-31T23:59:59+07:00')
        self.assertEqual(job.expiry_source,'structured_data')

    def test_city_facet_does_not_expose_street_as_location_choice(self):
        entry=self.entry()
        text=entry['response']['content']['text']
        text=text.replace('"addressRegion": '+json.dumps('Hà Nội'),'"streetAddress": "123 Fixture Street", "addressRegion": '+json.dumps('Hà Nội'))
        entry['response']['content']['text']=text
        job,_=extract(entry)
        self.assertEqual(job.location,'Hà Nội')
        self.assertEqual(job.work_locations,['123 Fixture Street, Hà Nội'])
