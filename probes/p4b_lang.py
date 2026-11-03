"""Phase 4b: ten real replies localised through Spark for one language (hi or es). Counts, plus the text for a person to read.
Usage: python probes/p4b_lang.py es|hi   (about 10 real Spark calls; writes outputs/p4b_<lang>.json)"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
from datetime import date
from helpers import make, seed_phase2
from app import lang, guard, record

code = sys.argv[1]
mid = {"hi": "m2", "es": "m5"}[code]
REPLIES = [
    "Hi {n}, has Nanaji had his 8 AM medicines: amlodipine, aspirin, metformin? Reply done, or tell me which ones.",
    "Logged: amlodipine, aspirin, metformin 08:00 given ({n}). Thanks.",
    "CareCircle: Arjun gave amlodipine, aspirin, metformin 08:00.",
    "CareCircle: Meena hasn't confirmed the 8 AM medicines for Nanaji yet (amlodipine, aspirin, metformin). Can you check and tell me?",
    "CareCircle: atorvastatin 20:00 for Nanaji is recorded as missed.",
    "Wednesday PM is still full in the organiser: that dose wasn't given.",
    "Schedule started: 4 medicine(s) are now live. I'll check in on each dose.",
    "Kabir added a lab report from 29 Oct: 4 values are outside the lab's printed range. See the board.",
    "CareCircle daily summary:\n- Kabir gave metformin 20:00.\n- Meena took a task: Discuss the lab report from 29 Oct with the doctor",
    "I can't give medical advice. I've noted this as a question for the doctor visit. Who will ask the doctor? Reply 'I will' to take it.",
]
conn, ob, ch = make("2026-11-03T08:30:00", all_tz="Asia/Kolkata")
seed_phase2(conn, date(2026, 11, 3))
m = record.member(conn, mid)
m["language"] = code
rows = []
for en in REPLIES:
    en = en.format(n=m["name"])
    out, used = lang.localize(conn, en, m)
    rows.append(dict(english=en, text=out, language=used, faithful=lang.faithful(conn, en, out), guard_ok=guard.check(conn, out)[0], unchanged_if_english=(out == en)))
res = dict(language=code, replies=len(rows), localized=sum(r["language"] == code for r in rows), fell_back_to_english=sum(r["language"] == "en" for r in rows),
           guard_failures=sum(not r["guard_ok"] for r in rows), name_or_number_changed=sum(not r["faithful"] for r in rows), rows=rows)
(ROOT / "outputs" / f"p4b_{code}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print({k: v for k, v in res.items() if k != "rows"})
