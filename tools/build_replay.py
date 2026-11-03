"""Build site/replay.html: one self-contained file (inline CSS and JS, no network calls, no keys) that replays the Thursday evening of the demo scene.
The data is exported from the fictional seed (app/seed.py) and the message wording is rendered by the real templates (app/tmpl.py), so the replay says what the product says.
Usage: python tools/build_replay.py   (writes site/replay.html and its copy docs/replay.html; nothing is published)"""
import json, pathlib, sys
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import seed, tmpl

P, MEDS = "Nanaji", ["metformin", "atorvastatin"]
DAY = datetime(2026, 11, 5, 12, 0)
LANG = {"en": "English", "hi": "Hindi", "es": "Spanish"}
LANG_OF = {"m2": "hi", "m5": "es"}                       # members.language in the seed


def members():
    out = []
    for mid, name, rel, tz, role, kind, _ in seed.MEMBERS:
        off = int(DAY.replace(tzinfo=ZoneInfo(tz)).utcoffset().total_seconds() // 60)
        out.append(dict(id=mid, name=name, rel=rel.replace(" (simulated)", ""), role=role, sim=kind == "sim", city=tz.split("/")[-1].replace("_", " "), utcOffsetMin=off))
    return out


def local(m, ist):
    h, mm = (int(x) for x in ist.split(":"))
    t = (h * 60 + mm - 330 + m["utcOffsetMin"]) % 1440
    return f"{t // 60:02d}:{t % 60:02d}"


def msg(to, at, kind, direction="to", **slots):
    lang = LANG_OF.get(to, "en")
    text = tmpl.render(kind, lang, **slots) if kind else slots["text"]
    return dict(dir=direction, who=M[to]["name"], at=at, lang=lang, langName=LANG[lang], text=text, en=tmpl.render(kind, "en", **slots) if kind else None)


M = {}
ms = members()
M.update({m["id"]: m for m in ms})
nudge = msg("m2", "20:15", "nudge", name="Meena", patient=P, meds=MEDS, time="20:00")
common = [
    dict(clock="19:55", status="upcoming", log="Evening doses coming up: metformin and atorvastatin at 8 PM.", wait=1500),
    dict(clock="20:00", status="due", log="8 PM: metformin and atorvastatin are due."),
    dict(clock="20:15", status="overdue", log="Fifteen minutes passed with no confirmation, so both doses are overdue."),
    dict(skip="m4", log="Sunita (on duty tonight) chose STOP, so she is skipped.", wait=1400),
    dict(ask="m2", log="CareCircle nudged Meena privately.", msgs=[nudge]),
    dict(choice=True),
]
done = [
    dict(clock="20:17", log="Meena replied: done.", msgs=[dict(dir="from", who="Meena", at="20:17", lang="en", langName="English", text="done", en=None)], wait=1300),
    dict(status="given", log="Both doses are recorded as given by Meena.", note="The circle settles. Arjun, Kabir and Sofía hear about it in their daily summary.",
         msgs=[msg("m2", "20:17", "logged", giver="Meena", meds=MEDS, time="20:00"), msg("m5", "daily summary", "relay_given", giver="Meena", patient=P, meds=MEDS, time="20:00", clock="20:17")]),
]
ignore = [
    dict(clock="20:16", skip="m1", log=f"Arjun was skipped: asleep ({local(M['m1'], '20:16')} in Los Angeles).", wait=1300),
    dict(ask="m3", log="CareCircle asked Kabir to check.", msgs=[msg("m3", "20:16", "escalate", first="Meena", patient=P, meds=MEDS, time="20:00")]),
    dict(clock="20:17", ask="m5", log="Nobody answered, so CareCircle asked Sofía.", msgs=[msg("m5", "20:17", "escalate", first="Meena", patient=P, meds=MEDS, time="20:00")]),
    dict(clock="20:18", log="Everyone who is awake has been asked. The doses stay open and the board shows it.", note="Still overdue. Nobody has confirmed."),
    dict(clock="20:40", org=True, log="Meena sent a photo of the pill organiser."),
    dict(log="The Thursday PM compartment is still full: that dose wasn't given.", note="The doses stay open until the next dose of the same medicine falls due; then they are recorded as missed.",
         msgs=[msg("m2", "20:41", "organiser_missed", day="THU", part="PM")], wait=2500),
]
data = dict(start="19:55", meds=MEDS, members=ms, common=common, done=done, ignore=ignore)
src = (ROOT / "site" / "replay.src.html").read_text(encoding="utf-8")
out = src.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\/"))
(ROOT / "site" / "replay.html").write_text(out, encoding="utf-8")
(ROOT / "docs" / "replay.html").write_text(out, encoding="utf-8")        # a copy GitHub Pages can serve from /docs
print("site/replay.html", len(out), "bytes")
