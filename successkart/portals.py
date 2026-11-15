"""External job-board search shortcuts. These are links, not scraped feeds."""
from urllib.parse import quote_plus

PORTALS = [
    ("Unstop", "unstop.com", "Jobs, internships, challenges"),
    ("Indeed India", "in.indeed.com", "Broad job listings"),
    ("Naukri", "naukri.com", "India private-sector jobs"),
    ("LinkedIn Jobs", "linkedin.com/jobs", "Company and recruiter listings"),
    ("Internshala", "internshala.com", "Internships and fresher roles"),
    ("Foundit", "foundit.in", "India jobs and fresher roles"),
    ("Wellfound", "wellfound.com/jobs", "Startup jobs"),
    ("Cutshort", "cutshort.io", "Technology and startup jobs"),
    ("Hirist", "hirist.com", "IT and technology jobs"),
    ("Instahyre", "instahyre.com", "Technology hiring"),
    ("Glassdoor", "glassdoor.co.in", "Jobs, company reviews and salaries"),
    ("Remotive", "remotive.com", "Remote jobs"),
    ("Arbeitnow", "arbeitnow.com", "Remote and international jobs"),
]


def portal_search_url(domain: str, query: str) -> str:
    # Search-engine site query avoids guessing undocumented query parameters
    # or scraping pages whose terms do not permit redistribution.
    q = quote_plus(f"site:{domain} {query}")
    return f"https://www.google.com/search?q={q}"


def build_portal_searches(query: str):
    return [(name, description, portal_search_url(domain, query))
            for name, domain, description in PORTALS]
