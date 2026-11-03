"""Phase 4 item 8: ten real replies localised to Hindi through Spark; counts only. A reply passes when every medicine name and number is unchanged and the guard accepts it.
Usage: python probes/p4_hindi.py   (real Spark calls, about 10; writes outputs/p4_hindi.json)"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
from datetime import date
from helpers import make, seed_phase2
from app import lang, guard, record

REPLIES = [
    "CareCircle: Hi Meena, has Nanaji had his 8 PM metformin? Reply done, or tell me what happened.",
    "Logged: metformin 08:00 given (Meena). Thanks.",
    "CareCircle: Arjun gave amlodipine 08:00.",
    "Wednesday PM is still full in the organiser: that dose wasn't given.",
    "Schedule started: 4 medicine(s) are now live. I'll check in on each dose.",
    "Amlodipine 5 mg is at 08:00.",
    "CareCircle: metformin 20:00 for Nanaji is recorded as missed.",
    "Saved. The lab report from 29 Oct is now in the care record.",
    "Kabir added a lab report from 29 Oct: 4 values are outside the lab's printed range. See the board.",
    "I can't give medical advice. I've noted this as a question for the doctor visit. Who will ask the doctor? Reply 'I will' to take it.",
]
conn, ob, ch = make("2026-11-03T08:30:00", all_tz="Asia/Kolkata")
seed_phase2(conn, date(2026, 11, 3))
m = record.member(conn, "m2")
m["language"] = "hi"
rows = []
for en in REPLIES:
    out, used = lang.localize(conn, en, m)
    rows.append(dict(english=en, hindi=out, language=used, faithful=lang.faithful(conn, en, out), guard_ok=guard.check(conn, out)[0], unchanged_if_english=(out == en)))
res = dict(replies=len(rows), localized=sum(r["language"] == "hi" for r in rows), fell_back_to_english=sum(r["language"] == "en" for r in rows),
           guard_failures=sum(not r["guard_ok"] for r in rows), name_or_number_changed=sum(not r["faithful"] for r in rows), rows=rows)
(ROOT / "outputs" / "p4_hindi.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print({k: v for k, v in res.items() if k != "rows"})
