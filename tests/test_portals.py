from successkart.portals import PORTALS, build_portal_searches, portal_search_url


def test_portal_search_links_include_requested_sites():
    names = {item[0] for item in PORTALS}
    assert {"Unstop", "Indeed India", "Naukri", "LinkedIn Jobs", "Internshala"} <= names


def test_search_url_encodes_query_and_domain():
    url = portal_search_url("unstop.com", "python internship")
    assert url.startswith("https://www.google.com/search?q=")
    assert "unstop.com" in url
    assert "python" in url


def test_build_searches_returns_one_link_per_portal():
    results = build_portal_searches("data analyst")
    assert len(results) == len(PORTALS)
    assert all(url.startswith("https://") for _, _, url in results)
