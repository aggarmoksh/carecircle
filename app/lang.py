"""Replies in each member's language (members.language). Code writes the English reply; Spark only rewrites it in the member's language.
Medicine names, doses, times and numbers must come back exactly as in the English text, in Latin letters and digits; the check is code and the guard
runs again on the result. Anything that fails the check is sent in English (and logged)."""
import re
from . import guard, llm, record
from .db import audit

LANGS = {"hi": "Hindi in Devanagari script"}
SCHEMA = {"name": "localized", "schema": {"type": "object", "additionalProperties": False, "required": ["text"], "properties": {"text": {"type": "string"}}}}
PROMPT = ("Rewrite this short message for a family member in {lang}. Keep it as short as the original and add nothing. Copy every medicine name, dose, clock time and number "
          "EXACTLY as written, in Latin letters and ASCII digits (never translate, transliterate or convert them). Keep people's names in Latin letters. Give no advice. "
          "Message: \"{text}\"")
DEVA_DIGITS = re.compile("[०-९]")


def _names(conn):
    names = set(guard.KNOWN_DRUGS)
    for st in ("confirmed", "draft"):
        for l in record.lines(conn, st):
            names |= guard._tokens(l["name"])
    return names


def faithful(conn, src, out):
    """True when every number and medicine name of `src` is in `out` unchanged, and `out` has no number that is not in `src`."""
    if DEVA_DIGITS.search(out):
        return False
    a, b = re.findall(r"\d+(?:[.,:]\d+)*", src), re.findall(r"\d+(?:[.,:]\d+)*", out)
    if sorted(set(a)) != sorted(set(b)):
        return False
    need = guard._tokens(src) & _names(conn)
    return need <= guard._tokens(out)


def localize(conn, text, member):
    """-> (text_to_send, language_used). English is returned unchanged when the member's language is English, or when the check fails."""
    code = (member.get("language") or "en")
    if code not in LANGS:
        return text, "en"
    try:
        r, _, _ = llm.spark_json("phase4", f"lang-{code}", [{"role": "user", "content": PROMPT.format(lang=LANGS[code], text=text)}], SCHEMA)
        out = r["text"].strip()
    except Exception as e:
        audit(conn, "lang_fallback", member["id"], type(e).__name__, "translation failed; sent in English")
        return text, "en"
    ok, why = guard.check(conn, out)
    if not out or not faithful(conn, text, out) or not ok:
        audit(conn, "lang_fallback", member["id"], {"english": text, "rejected": out, "why": why or "a name or number changed"}, "translation failed the check; sent in English")
        return text, "en"
    return out, code
