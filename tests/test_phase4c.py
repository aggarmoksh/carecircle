"""Phase 4c: fixed templates per language (no model rephrasing), Hindi and Spanish time words."""
import re
import pytest
from helpers import make, seed_d1
from app import tmpl, llm, escalation, intake, record
from app.clock import clock

ONE, THREE = ["metformin"], ["amlodipine", "aspirin", "metformin"]
SLOTS = dict(name="Meena", first="Meena", giver="Arjun", member="Kabir", patient="Nanaji", time="20:00", clock="20:07", n=4, day="WED", part="PM", date="2026-10-29", link="https://x.invalid/b/t")


@pytest.mark.parametrize("lang", ["en", "hi", "es"])
@pytest.mark.parametrize("meds", [ONE, THREE])
@pytest.mark.parametrize("kind", tmpl.KINDS)
def test_every_template_renders_for_one_and_three_medicines(kind, meds, lang):
    out = tmpl.render(kind, lang, meds=meds, **SLOTS)
    assert out and "{" not in out and "}" not in out
    if kind in ("nudge", "escalate", "relay_given", "missed", "logged"):
        assert all(m in out for m in meds)                               # names stay in Latin letters, exactly as in the record


def test_hindi_12_hour_clock_with_time_word_never_24_hour():
    assert tmpl.hi_time("20:00") == "शाम 8 बजे"
    for t, word in (("05:00", "सुबह"), ("11:59", "सुबह"), ("12:00", "दोपहर"), ("15:59", "दोपहर"), ("16:00", "शाम"), ("20:59", "शाम"), ("21:00", "रात"), ("04:59", "रात"), ("00:00", "रात")):
        assert tmpl.hi_time(t).startswith(word + " ")
    assert tmpl.hi_time("12:00") == "दोपहर 12 बजे" and tmpl.hi_time("08:30") == "सुबह 8:30 बजे"
    for k in ("nudge", "missed", "relay_given", "escalate"):
        out = tmpl.render(k, "hi", meds=ONE, **SLOTS)
        assert "शाम 8 बजे" in out and "20:00" not in out and "20:07" not in out


def test_spanish_time_words_and_accents():
    assert tmpl.es_time("20:00") == "las 8 de la noche" and tmpl.es_time("08:00") == "las 8 de la mañana" and tmpl.es_time("15:00") == "las 3 de la tarde"
    assert tmpl.es_time("13:00") == "la 1 de la tarde" and tmpl.es_time("04:00") == "las 4 de la madrugada"
    n = tmpl.render("nudge", "es", meds=ONE, **dict(SLOTS, name="Sofía"))
    assert n == "Hola Sofía, ¿Nanaji ya tomó metformin de las 8 de la noche? Responde «done» o dime cuáles tomó."
    assert "tomó" in n and "Sofía" in n


def test_hindi_templates_match_the_advisors_wording():
    assert tmpl.render("nudge", "hi", meds=ONE, **SLOTS) == "नमस्ते Meena, क्या Nanaji ने शाम 8 बजे वाली metformin दवा ले ली? 'done' लिखें, या बताएं कौन सी ली।"
    assert tmpl.render("missed", "hi", meds=ONE, **SLOTS) == "Nanaji की शाम 8 बजे वाली metformin दवा की पुष्टि नहीं हुई।"
    assert tmpl.render("organiser_missed", "hi", **SLOTS) == "दवा के डिब्बे में बुधवार शाम वाला हिस्सा अभी भरा है: वह दवा नहीं दी गई।"
    assert tmpl.render("schedule_live", "hi", **SLOTS) == "Arjun ने Nanaji की दवाओं की सूची पक्की कर दी: 4 दवाएं शुरू हो गई हैं।"
    assert tmpl.render("lab_added", "hi", **SLOTS).startswith("Kabir ने 29 अक्टूबर की लैब रिपोर्ट जोड़ी: 4 नतीजे लैब की छपी हुई रेंज से बाहर हैं।")
    assert tmpl.render("relay_given", "es", meds=THREE, **SLOTS) == "Arjun le dio a Nanaji amlodipine, aspirin y metformin de las 8 de la noche (a las 8:07 de la noche)."
    assert tmpl.render("organiser_missed", "es", **SLOTS) == "En el pastillero, el compartimento del miércoles por la noche sigue lleno: esa dosis no se dio."


def test_system_messages_reach_members_in_their_language_without_the_model(monkeypatch):
    monkeypatch.setattr(llm, "spark_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the model must not rephrase system messages")))
    conn, ob, ch = make("2026-11-02T02:45:30", all_tz="Asia/Kolkata")
    conn.execute("UPDATE members SET language='hi' WHERE id='m2'")
    conn.execute("UPDATE members SET language='es' WHERE id='m1'")
    conn.commit()
    seed_d1(conn, confirmed_at="2026-11-02T00:00:00Z")
    conn.execute("DELETE FROM dose_events")
    conn.commit()
    escalation.tick(conn, ob)
    assert ch.log[0] == ("m2", "नमस्ते Meena, क्या Nanaji ने सुबह 8 बजे वाली amlodipine, aspirin और metformin दवा ले ली? 'done' लिखें, या बताएं कौन सी ली।")
    ch.log.clear()
    monkeypatch.setattr(llm, "spark_json", lambda ph, lb, m, sc: ({"actor": "m2", "slot": "none", "action": "given"}, 0, 0))
    intake._dose(conn, ob, "m2", "done", clock.now())
    got = dict((m, t) for m, t in ch.log)
    assert got["m2"].startswith("दर्ज हो गया: सुबह 8 बजे वाली amlodipine, aspirin और metformin दवा दी गई")
    assert got["m1"] == "Meena le dio a Nanaji amlodipine, aspirin y metformin de las 8 de la mañana (a las 8:15 de la mañana)."
    assert got["m3"] == "CareCircle: Meena gave amlodipine, aspirin, metformin 08:00."
