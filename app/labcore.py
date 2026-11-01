"""Pure lab-range logic: parse the printed range text and compute the status by code (no model, no I/O)."""
import re

NUM = r"(\d[\d,]*\.?\d*)"


def _n(s):
    return float(s.replace(",", ""))


def parse_range(text):
    """Printed range text -> (low, high). Unparseable or empty -> (None, None)."""
    t = (text or "").strip().replace("–", "-").replace("—", "-").replace("−", "-")
    if not t:
        return None, None
    m = re.fullmatch(NUM + r"\s*-\s*" + NUM + r"(?:\s*\S+)?", t)
    if m:
        return _n(m.group(1)), _n(m.group(2))
    m = re.fullmatch(r"(<=?|≤)\s*" + NUM + r"(?:\s*\S+)?", t)
    if m:
        return None, _n(m.group(2))
    m = re.fullmatch(r"(>=?|≥)\s*" + NUM + r"(?:\s*\S+)?", t)
    if m:
        return _n(m.group(2)), None
    return None, None


def status(value, text):
    """within / above / below / no_range, by the rules in tests/lab_labels.json _rules. '< b' and '> a' are exclusive bounds."""
    t = (text or "").strip().replace("−", "-")
    low, high = parse_range(t)
    if low is None and high is None:
        return "no_range"
    if low is not None and high is not None:
        return "within" if low <= value <= high else ("below" if value < low else "above")
    if high is not None:  # '< b'
        incl = t.startswith(("<=", "≤"))
        return "within" if (value <= high if incl else value < high) else "above"
    incl = t.startswith((">=", "≥"))  # '> a'
    return "within" if (value >= low if incl else value > low) else "below"


def norm_unit(u):
    return re.sub(r"\s+", "", (u or "").lower().replace("µ", "u").replace("μ", "u"))


def finish(raw):
    """Add parsed range and code-computed status to the model's copy of the report."""
    out = dict(raw, tests=[])
    for t in raw["tests"]:
        low, high = parse_range(t["range_text"])
        out["tests"].append(dict(t, test=t["test"].strip().lower(), parsed_low=low, parsed_high=high, status=status(t["value"], t["range_text"])))
    return out


