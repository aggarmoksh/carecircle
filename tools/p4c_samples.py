"""Write every Hindi and Spanish template, rendered for 1 and 3 medicines, to outputs/p4c_language_samples.txt for a person to read."""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import tmpl

ONE, THREE = ["metformin"], ["amlodipine", "aspirin", "metformin"]
LINK = "https://example.invalid/b/abc123"


def samples():
    out = []
    for lang, who in (("hi", "Meena"), ("es", "Sofía")):
        out.append(f"===== {lang} =====")
        for meds in (ONE, THREE):
            out.append(f"--- {len(meds)} medicine(s) ---")
            for t in ("08:00", "13:30", "18:00", "20:00", "22:15", "03:00"):
                out.append(f"nudge {t}: " + tmpl.render("nudge", lang, name=who, patient="Nanaji", meds=meds, time=t))
            out.append("escalate: " + tmpl.render("escalate", lang, first="Meena", patient="Nanaji", meds=meds, time="20:00"))
            out.append("relay-given: " + tmpl.render("relay_given", lang, giver="Arjun", patient="Nanaji", meds=meds, time="20:00", clock="20:07"))
            out.append("missed: " + tmpl.render("missed", lang, patient="Nanaji", meds=meds, time="20:00"))
            out.append("logged: " + tmpl.render("logged", lang, giver="Meena", meds=meds, time="08:00"))
        out.append("--- other ---")
        out.append("organiser-missed: " + tmpl.render("organiser_missed", lang, day="WED", part="PM"))
        out.append("organiser-missed: " + tmpl.render("organiser_missed", lang, day="THU", part="AM"))
        out.append("schedule-live: " + tmpl.render("schedule_live", lang, giver="Kabir", patient="Nanaji", n=4))
        out.append("lab-added: " + tmpl.render("lab_added", lang, member="Kabir", date="2026-10-29", n=4, link=LINK))
        out.append("daily-summary: " + tmpl.render("daily_header", lang) + chr(10) + "- " + tmpl.render("relay_given", lang, giver="Arjun", patient="Nanaji", meds=ONE, time="08:00", clock="08:03")
                   + chr(10) + "- " + tmpl.render("missed", lang, patient="Nanaji", meds=ONE, time="20:00"))
        out.append("fixed medical: " + tmpl.fixed("medical", lang))
        out.append("fixed urgent: " + tmpl.fixed("urgent", lang))
    return chr(10).join(out) + chr(10)


if __name__ == "__main__":
    (ROOT / "outputs" / "p4c_language_samples.txt").write_text(samples(), encoding="utf-8")
    print("written")
