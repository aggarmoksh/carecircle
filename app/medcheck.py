"""P9 medicine-name check: Spark with web search says whether a drug name (and strength) appears in public medicine listings; code then
fetches the cited page and counts it only if the domain is on the allowlist, the page loads and it contains the name.
Only the medicine name and strength are ever sent to the search. No suggestions, no judgement of any dose."""
import json, re, time
from urllib.parse import urlparse
import httpx
from . import llm

ALLOWED = ["dailymed.nlm.nih.gov", "medlineplus.gov", "drugs.com", "ema.europa.eu", "medicines.org.uk", "nhs.uk", "healthdirect.gov.au", "1mg.com", "practo.com", "pharmeasy.in", "apollopharmacy.in"]
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["found", "product", "strength_found", "source_url"], "properties": {
    "found": {"type": "string", "enum": ["yes", "no"]}, "product": {"type": "string"}, "strength_found": {"type": "string", "enum": ["yes", "no", "not_asked"]}, "source_url": {"type": "string"}}}
PROMPT = ("Search the web: is \"{name}\" the name of a medicine product listed in public medicine listings (drug label databases, national health services, "
          "pharmacy listings)? If a strength is part of the name, is that exact strength listed for that product? Use only these sites: {domains}. "
          "Answer found=yes only if you find a listing page for this exact product name; otherwise found=no. product = the product name as listed (empty if none). "
          "strength_found = yes or no if a strength was asked, else not_asked. source_url = the one listing page you rely on (empty if none). Give no advice.")


def domain_ok(url):
    h = (urlparse(url).hostname or "").lower()
    return any(h == d or h.endswith("." + d) for d in ALLOWED), h


def base_name(q):
    """'Dolo 650 mg' -> ('Dolo', '650'); 'Pan-D' -> ('Pan-D', None)."""
    m = re.match(r"^(.*?)(?:\s+(\d[\d.,]*)\s*(?:mg|mcg|units/mL))?$", q.strip())
    return m.group(1).strip(), m.group(2)


def search(name):
    llm.guard("muse-spark-1.3", 0.03)
    body = {"model": "muse-spark-1.3", "input": PROMPT.format(name=name, domains=", ".join(ALLOWED)), "tools": [{"type": "web_search"}], "max_tool_calls": 2, "reasoning": {"effort": "low"},
            "text": {"format": {"type": "json_schema", "name": "medcheck", "strict": True, "schema": SCHEMA}}}
    t = time.time()
    r = httpx.post(f"{llm.BASE}/responses", json=body, headers={"Authorization": f"Bearer {llm.key()}"}, timeout=180)
    dt = time.time() - t
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    u = j.get("usage") or {}
    calls = sum(1 for o in j.get("output", []) if o.get("type") == "web_search_call")
    usd = u.get("input_tokens", 0) * llm.PRICE_IN + u.get("output_tokens", 0) * llm.PRICE_OUT + calls * 0.0025
    llm.log_spend("P9", name, usd, kind="spark_search", seconds=dt, http=r.status_code, searches=calls)
    return r.status_code, j


def answer_of(j):
    for o in reversed(j.get("output", [])):               # the last message is the answer; earlier ones are commentary
        for c in o.get("content", []) or []:
            if c.get("type") == "output_text":
                try:
                    return json.loads(c["text"])
                except ValueError:
                    return None
    return None


def verify(q, ans):
    """-> (found:boolean, domain, why). Counted as found only with a valid source: allowed domain, page loads, page contains the product name (and the strength when one was asked)."""
    if not ans or ans.get("found") != "yes" or not ans.get("source_url"):
        return False, "", "model: not found"
    ok, host = domain_ok(ans["source_url"])
    if not ok:
        return False, host, "source domain not on the allowlist"
    brand, strength = base_name(q)
    try:
        r = httpx.get(ans["source_url"], timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (CareCircle name check)"})
    except Exception as e:
        return False, host, "page did not load (" + type(e).__name__ + ")"
    if r.status_code != 200:
        return False, host, f"page did not load (HTTP {r.status_code})"
    page = re.sub(r"\s+", " ", r.text).lower()
    if brand.lower() not in page:
        return False, host, "page does not contain the name"
    if strength and not (ans.get("strength_found") == "yes" and re.search(r"(?<![\d.])" + re.escape(strength) + r"(?![\d])", page)):
        return False, host, "strength not on the page"
    return True, host, "ok"
