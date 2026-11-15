import re

def tokens(s):
    return {x.lower() for x in re.findall(r"[a-zA-Z0-9+#.]+",s or "") if len(x)>1}

def parse_stipend(value):
    if not value: return None
    text=value.lower().replace(",","")
    nums=re.findall(r"\d+(?:\.\d+)?",text)
    if not nums: return None
    amount=int(float(nums[0]))
    if "k" in text: amount*=1000
    if "lpa" in text or "lakh" in text: amount*=100000
    if "lpa" in text or "per annum" in text or "year" in text: amount//=12
    return amount

def matches(user,job):
    wanted=tokens(user["skills"])
    found=tokens((job["skills"] or "")+" "+job["title"]+" "+(job["description"] or ""))
    if wanted and not wanted.intersection(found): return False
    kind=(user["opportunity_type"] or "Both").lower()
    if kind!="both" and kind not in (job["opportunity_type"] or "").lower(): return False
    pref=(user["location_preference"] or "Any").lower()
    loc=(job["location"] or "").lower()
    if pref=="remote" and "remote" not in loc: return False
    if pref=="india" and not any(x in loc for x in ("india","remote")): return False
    if pref not in ("any","remote","india") and pref not in loc and "remote" not in loc: return False
    minimum=user["min_stipend"]
    if minimum and (job["stipend_min"] is None or job["stipend_min"]<minimum): return False
    return True
