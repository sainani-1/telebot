from successkart.matching import matches,parse_stipend

def test_matching_skill_and_type():
    u={"skills":"Python, SQL","opportunity_type":"Internship","location_preference":"Remote","min_stipend":None}
    j={"skills":"Python, APIs","title":"Python Intern","description":"","opportunity_type":"Internship","location":"Remote","stipend_min":15000}
    assert matches(u,j)

def test_skill_mismatch():
    u={"skills":"Java","opportunity_type":"Internship","location_preference":"Any","min_stipend":None}
    j={"skills":"Python","title":"Python Intern","description":"","opportunity_type":"Internship","location":"Remote","stipend_min":15000}
    assert not matches(u,j)

def test_minimum_stipend():
    u={"skills":"Python","opportunity_type":"Internship","location_preference":"Any","min_stipend":20000}
    j={"skills":"Python","title":"Python Intern","description":"","opportunity_type":"Internship","location":"Remote","stipend_min":10000}
    assert not matches(u,j)

def test_parse_stipend():
    assert parse_stipend("₹15,000/month")==15000
    assert parse_stipend("6 LPA")==50000
