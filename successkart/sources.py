"""Public job feeds and official recruitment-page monitors.

Only public pages/APIs are requested. No login, CAPTCHA, or anti-bot bypass is used.
"""
import hashlib
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .matching import parse_stipend

log = logging.getLogger(__name__)
USER_AGENT = "SuccessKartBot/1.1 (+public job-feed monitor)"


def key(source, url, discriminator=""):
    return hashlib.sha256(f"{source}:{url}:{discriminator}".encode()).hexdigest()


def _clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def _kind(title, category=""):
    text = f"{title} {category}".lower()
    return "Internship" if any(x in text for x in ("intern", "apprentice", "apprenticeship", "trainee")) else "Full-time"


def _job(source, title, company, url, description="", location="India", deadline="Not specified", kind=None):
    title = _clean(title)[:240]
    if not title or not url.startswith(("https://", "http://")):
        return None
    description = _clean(description)[:1800]
    return {
        "source_key": key(source, url, title + "|" + deadline),
        "source": source,
        "title": title,
        "company": _clean(company)[:180] or source,
        "skills": "",
        "qualification": "See official notification",
        "location": location or "India",
        "stipend_text": "Not disclosed",
        "stipend_min": None,
        "deadline": deadline or "Not specified",
        "url": url,
        "description": description,
        "opportunity_type": kind or _kind(title, description),
    }


def _date_from_text(text):
    match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", text or "")
    if match:
        try:
            return datetime.strptime(match.group(1), "%d/%m/%Y").strftime("%d %b %Y")
        except ValueError:
            pass
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text or "")
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").strftime("%d %b %Y")
        except ValueError:
            pass
    return "Not specified"


async def _fetch_json(client, source, url, limit):
    response = await client.get(url)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("jobs", []) if source == "Remotive" else payload.get("data", [])
    out = []
    for item in rows[:limit]:
        link = item.get("url", "")
        title = item.get("title") or "Untitled role"
        stipend = item.get("salary") or "Not disclosed"
        out.append({
            "source_key": key(source, link), "source": source, "title": title,
            "company": item.get("company_name") or "Not listed",
            "skills": ", ".join(item.get("tags") or []), "qualification": "",
            "location": item.get("candidate_required_location") or item.get("location") or ("Remote" if item.get("remote") else "Not specified"),
            "stipend_text": stipend, "stipend_min": parse_stipend(stipend),
            "deadline": "Not specified", "url": link,
            "description": _clean(item.get("description") or "")[:1500],
            "opportunity_type": _kind(title),
        }) if link.startswith(("https://", "http://")) else None
    return [x for x in out if x]


async def _fetch_ncs(client, limit):
    source = "National Career Service (Govt + Private)"
    page = "https://ncs.gov.in/latest-update"
    response = await client.get(page)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if len(cells) < 6:
            continue
        vals = [_clean(c.get_text(" ", strip=True)) for c in cells]
        title = vals[2]
        if not title or title.lower() == "position":
            continue
        anchor = cells[-1].find("a", href=True)
        url = urljoin(page, anchor["href"]) if anchor else page
        company = vals[1] or "National Career Service listing"
        location = "India"
        desc = f"Posting date: {vals[3]}; vacancies: {vals[4]}; listing type: {vals[5]}"
        item = _job(source, title, company, url, desc, location, "Not specified", _kind(title, vals[5]))
        if item:
            out.append(item)
        if len(out) >= limit:
            break
    return out


async def _fetch_employment_news(client, limit):
    source = "Employment News (Govt of India)"
    page = "https://employmentnews.gov.in/NewEmp/AllJobs.aspx?k=All"
    response = await client.get(page)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if len(cells) < 5:
            continue
        vals = [_clean(c.get_text(" ", strip=True)) for c in cells]
        if not vals[1] or vals[1].lower() == "organisation":
            continue
        title, company = vals[2], vals[1]
        deadline = _date_from_text(vals[4])
        anchor = next((a for c in cells for a in c.find_all("a", href=True)), None)
        url = urljoin(page, anchor["href"]) if anchor else page
        item = _job(source, title, company, url, f"Appointment: {vals[3]}", "India", deadline)
        if item:
            out.append(item)
        if len(out) >= limit:
            break
    return out


async def _fetch_appsc(client, limit):
    source = "Andhra Pradesh Public Service Commission (APPSC)"
    page = "https://portal-psc.ap.gov.in/HomePages/RecruitmentNotifications"
    response = await client.get(page)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    out, seen = [], set()
    for anchor in soup.find_all("a", href=True):
        title = _clean(anchor.get_text(" ", strip=True))
        if not title or not re.search(r"notification|recruitment|group[- ]?[i1v]+|group[- ]?ii|group[- ]?iv|assistant|officer|engineer|police|forest", title, re.I):
            continue
        url = urljoin(page, anchor["href"])
        if url in seen or urlparse(url).netloc.lower() not in ("portal-psc.ap.gov.in", "psc.ap.gov.in"):
            continue
        seen.add(url)
        item = _job(source, title, "Andhra Pradesh Government", url, "Official APPSC recruitment notification. Open the official notice for eligibility, vacancies, age limits and dates.", "Andhra Pradesh, India", _date_from_text(title), "Full-time")
        if item:
            out.append(item)
        if len(out) >= limit:
            break
    return out


async def _fetch_official_notice_page(client, source, page, limit, domain_allowlist=None):
    """Conservative generic monitor for official career/recruitment notice pages."""
    response = await client.get(page)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    allowed = set(domain_allowlist or [urlparse(page).netloc.lower()])
    out, seen = [], set()
    keywords = re.compile(r"recruit|vacanc|career|notification|advertisement|apprentice|hiring|job", re.I)
    for anchor in soup.find_all("a", href=True):
        title = _clean(anchor.get_text(" ", strip=True))
        if not title or len(title) < 12 or not keywords.search(title):
            continue
        url = urljoin(page, anchor["href"])
        if urlparse(url).scheme not in ("http", "https") or urlparse(url).netloc.lower() not in allowed or url in seen:
            continue
        seen.add(url)
        item = _job(source, title, source, url, "Official recruitment/career notice. Verify full eligibility and dates on the linked notice.", "India", _date_from_text(title))
        if item:
            out.append(item)
        if len(out) >= limit:
            break
    return out


async def fetch_all(timeout, limit):
    """Fetch public APIs and official Indian recruitment pages independently."""
    all_items, health = [], []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json,*/*"}) as client:
        sources = [
            ("Remotive", lambda: _fetch_json(client, "Remotive", "https://remotive.com/api/remote-jobs", limit)),
            ("Arbeitnow", lambda: _fetch_json(client, "Arbeitnow", "https://www.arbeitnow.com/api/job-board-api", limit)),
            ("National Career Service (Govt + Private)", lambda: _fetch_ncs(client, limit)),
            ("Employment News (Govt of India)", lambda: _fetch_employment_news(client, limit)),
            ("Andhra Pradesh Public Service Commission (APPSC)", lambda: _fetch_appsc(client, limit)),
            ("Andhra Pradesh Police Recruitment Board (SLPRB)", lambda: _fetch_official_notice_page(client, "Andhra Pradesh Police Recruitment Board (SLPRB)", "https://slprb.ap.gov.in/", limit)),
            ("Railway Recruitment Board (RRB)", lambda: _fetch_official_notice_page(client, "Railway Recruitment Board (RRB)", "https://rrb.indianrailways.gov.in/", limit)),
            ("RRB Secunderabad", lambda: _fetch_official_notice_page(client, "RRB Secunderabad", "https://rrbsecunderabad.gov.in/cen-lists/", limit)),
            ("UPSC", lambda: _fetch_official_notice_page(client, "UPSC", "https://upsc.gov.in/recruitment/recruitment-advertisement", limit)),
            ("SSC", lambda: _fetch_official_notice_page(client, "SSC", "https://ssc.gov.in/home/notice-board", limit)),
            ("IBPS", lambda: _fetch_official_notice_page(client, "IBPS", "https://www.ibps.in/", limit)),
            ("SBI Careers", lambda: _fetch_official_notice_page(client, "SBI Careers", "https://sbi.co.in/web/careers/current-openings", limit)),
            ("RBI Opportunities", lambda: _fetch_official_notice_page(client, "RBI Opportunities", "https://opportunities.rbi.org.in/scripts/vacancies.aspx", limit, ["opportunities.rbi.org.in"])),
            ("ISRO Careers", lambda: _fetch_official_notice_page(client, "ISRO Careers", "https://www.isro.gov.in/Careers.html", limit)),
            ("DRDO Careers", lambda: _fetch_official_notice_page(client, "DRDO Careers", "https://www.drdo.gov.in/drdo/careers", limit)),
        ]
        for source, fetcher in sources:
            try:
                items = await fetcher()
                all_items.extend(items)
                health.append({"source": source, "ok": True, "count": len(items), "error": None})
            except Exception as exc:
                log.warning("Source fetch failed: %s: %s", source, exc)
                health.append({"source": source, "ok": False, "count": 0, "error": str(exc)[:400]})
    # De-duplicate across sources by normalized destination URL + title.
    unique, seen = [], set()
    for item in all_items:
        marker = (item["url"].rstrip("/").lower(), item["title"].lower())
        if marker not in seen:
            seen.add(marker)
            unique.append(item)
    return unique, health

async def search_partner_sources(query, timeout, api_key):
    """Search licensed/third-party structured public listing APIs on demand.

    API.SH is an independent data provider, not an official Unstop/Internshala API.
    Each endpoint call consumes provider credits. No calls are made without a key.
    """
    if not api_key:
        return [], [{"source": "API.SH (Unstop / Internshala)", "ok": False,
                     "count": 0, "error": "APISH_API_KEY is not configured"}]

    results, health = [], []
    headers = {"x-api-key": api_key, "Accept": "application/json",
               "User-Agent": USER_AGENT}
    requests = [
        ("Unstop", "https://api.api.sh/unstop/v1/search",
         {"type": "all", "q": query, "status": "open", "sort": "latest"}),
        ("Internshala", "https://api.api.sh/internshala/v1/search",
         {"type": "internships", "q": query, "page": 1}),
    ]
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for source, endpoint, params in requests:
            try:
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
                payload = response.json()
                if payload.get("success") is False:
                    raise ValueError(payload.get("error") or "Provider returned success=false")
                rows = payload.get("items", []) if source == "Unstop" else payload.get("results", [])
                count = 0
                for item in rows:
                    url = item.get("url") or item.get("short_url") or ""
                    title = item.get("title") or ""
                    if not title or not url.startswith("https://"):
                        continue
                    if source == "Unstop":
                        subtype = (item.get("type") or item.get("subtype") or "").lower()
                        if subtype not in ("jobs", "job", "internships", "internship"):
                            continue
                        org = item.get("organisation") or "Not listed"
                        locs = item.get("locations") or []
                        location = ", ".join(locs) if isinstance(locs, list) else str(locs)
                        skills = item.get("skills") or []
                        skills_text = ", ".join(str(s) for s in skills) if isinstance(skills, list) else str(skills)
                        salary = item.get("salary") or {}
                        salary_text = "Not disclosed"
                        if isinstance(salary, dict) and salary.get("min") is not None:
                            lo, hi = salary.get("min"), salary.get("max")
                            currency = "₹" if (salary.get("currency") or "").lower() in ("rupee", "inr") else str(salary.get("currency") or "") + " "
                            salary_text = f"{currency}{lo}" + (f"–{hi}" if hi is not None and hi != lo else "") + " (as listed; pay period not confirmed)"
                        deadline = _date_from_text(str(item.get("registration_end") or item.get("end_date") or ""))
                        if deadline == "Not specified":
                            raw_date = str(item.get("registration_end") or item.get("end_date") or "")[:10]
                            try: deadline = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d %b %Y")
                            except ValueError: pass
                        kind = "Internship" if "intern" in subtype or "intern" in title.lower() else "Full-time"
                        desc = item.get("snippet") or ""
                        stipend_min = None
                    else:
                        org = item.get("company") or "Not listed"
                        location = item.get("location_text") or ", ".join(item.get("locations") or []) or "Not specified"
                        skills = item.get("skills") or []
                        skills_text = ", ".join(str(s) for s in skills) if isinstance(skills, list) else str(skills)
                        salary_text = item.get("stipend_or_salary") or "Not disclosed"
                        stipend_min = item.get("pay_min") if (item.get("pay_period") or "").lower() == "month" else None
                        deadline = "Not specified"
                        kind = "Internship" if (item.get("type") or "internship").lower() == "internship" else "Full-time"
                        desc = item.get("snippet") or ""
                    results.append({
                        "source_key": key(source, url), "source": source,
                        "title": _clean(title)[:240], "company": _clean(org)[:180],
                        "skills": _clean(skills_text)[:500],
                        "qualification": "See original listing for eligibility",
                        "location": _clean(location)[:240] or "Not specified",
                        "stipend_text": _clean(salary_text)[:120],
                        "stipend_min": stipend_min, "deadline": deadline,
                        "url": url, "description": _clean(desc)[:1500],
                        "opportunity_type": kind,
                    })
                    count += 1
                health.append({"source": source, "ok": True, "count": count, "error": None})
            except Exception as exc:
                log.warning("Partner source search failed: %s: %s", source, exc)
                health.append({"source": source, "ok": False, "count": 0, "error": str(exc)[:400]})
    # Deduplicate while retaining the first source-grounded record.
    unique, seen = [], set()
    for item in results:
        marker = item["url"].rstrip("/").lower()
        if marker not in seen:
            seen.add(marker)
            unique.append(item)
    return unique, health
