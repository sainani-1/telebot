from successkart.sources import _date_from_text, _job, _kind


def test_job_records_source_and_official_apply_url():
    item = _job("APPSC", "Group-II Services", "Andhra Pradesh Government",
                "https://portal-psc.ap.gov.in/notice.pdf", "Official notification",
                "Andhra Pradesh, India", "Not specified", "Full-time")
    assert item["source"] == "APPSC"
    assert item["url"].endswith("notice.pdf")
    assert item["opportunity_type"] == "Full-time"


def test_apprenticeship_is_classified_as_internship():
    assert _kind("Graduate Apprentice") == "Internship"


def test_government_recruitment_is_classified_as_full_time():
    assert _kind("Assistant Engineer Recruitment") == "Full-time"


def test_date_parser_supports_employment_news_format():
    assert _date_from_text("Last date 21/11/2026") == "21 Nov 2026"

import pytest
from successkart.sources import search_partner_sources

@pytest.mark.asyncio
async def test_partner_search_does_not_call_provider_without_key():
    items, health = await search_partner_sources("python internship", 5, "")
    assert items == []
    assert health[0]["ok"] is False
    assert "not configured" in health[0]["error"]

@pytest.mark.asyncio
async def test_partner_search_normalizes_unstop_and_internshala(monkeypatch):
    class FakeResponse:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def json(self): return self.payload

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, params=None):
            if "unstop" in url:
                return FakeResponse({"items": [{
                    "type": "jobs", "title": "Python Developer", "organisation": "Acme",
                    "url": "https://unstop.com/jobs/python-developer-123",
                    "locations": ["Remote"], "skills": ["Python"], "snippet": "Build APIs"
                }]})
            return FakeResponse({"results": [{
                "type": "internship", "title": "Python Intern", "company": "Beta",
                "url": "https://internshala.com/internship/detail/python-intern-123",
                "location_text": "Remote", "skills": ["Python"],
                "stipend_or_salary": "₹ 10,000 /month", "pay_min": 10000,
                "pay_period": "month", "snippet": "Internship role"
            }]})

    monkeypatch.setattr("successkart.sources.httpx.AsyncClient", FakeClient)
    items, health = await search_partner_sources("python", 5, "test-key")
    assert {x["source"] for x in items} == {"Unstop", "Internshala"}
    assert len(items) == 2
    assert all(x["url"].startswith("https://") for x in items)
    assert next(x for x in items if x["source"] == "Internshala")["stipend_min"] == 10000
    assert all(x["ok"] for x in health)
