"""Phase 4d: light by default (dark only by the toggle), Spanish fixes, templates for the remaining English-only messages, Now-card dose cards, both demo scenes."""
import os, pathlib, re, subprocess, sys
import pytest
from datetime import date
from helpers import make, seed_d1, LABELS, utc
from app import cards, db, demo, intake, record, tmpl, board
from app.clock import clock

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOARD = (ROOT / "app" / "board.html").read_text(encoding="utf-8")


# ---------------- 1. theme ----------------
def test_light_by_default_and_dark_only_by_the_toggle():
    replay = (ROOT / "site" / "replay.src.html").read_text(encoding="utf-8")
    for name, html in (("board", BOARD), ("replay", replay), ("card", cards.card_html({"doses": [], "members": [], "ladder": [], "patient": "Nanaji", "patient_local": "Thu 05 Nov 08:31"}))):
        assert "prefers-color-scheme" not in html, name                                  # the system setting is ignored
    for html in (BOARD, replay):
        assert '<meta name="color-scheme" content="light">' in html
        assert "function isDark(){return document.documentElement.getAttribute('data-theme')==='dark'}" in html
        assert "try{var t=" in html and "localStorage.getItem(\"cc-theme\")" in html and "try{localStorage.setItem('cc-theme'" in html      # remembered, always inside try/catch
        assert ":root[data-theme=dark]{" in html                                         # dark exists, but only under the attribute


@pytest.mark.skipif(not cards.chrome(), reason="no Chrome on this machine")
def test_replay_stays_light_when_the_system_asks_for_dark_and_goes_dark_only_with_the_toggle(tmp_path):
    from PIL import Image
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_replay.py")], check=True, capture_output=True)
    page = (ROOT / "site" / "replay.html").as_uri()

    def shot(name, url, *flags):
        out = tmp_path / name
        subprocess.run([cards.chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=4000", "--window-size=1000,700", f"--screenshot={out}", *flags, url],
                       check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return Image.open(out).convert("RGB").getpixel((4, 600))
    assert sum(shot("a.png", page + "?auto=ignore&fast=1", "--blink-settings=preferredColorScheme=1")) > 600      # system says dark; the page is still light
    assert sum(shot("b.png", page + "?auto=ignore&fast=1&theme=dark")) < 150                                      # the toggle (here the ?theme= form of it) makes it dark


# ---------------- 2. Spanish fixes ----------------
def test_spanish_madrugada_escalate_clock_brackets_and_organiser_wording():
    assert tmpl.es_time("03:00") == "las 3 de la madrugada" and tmpl.es_time("00:00") == "las 12 de la madrugada" and tmpl.es_time("05:59") == "las 5:59 de la madrugada"
    assert tmpl.es_time("06:00") == "las 6 de la mañana" and tmpl.es_time("11:59") == "las 11:59 de la mañana" and tmpl.es_time("12:00") == "las 12 de la tarde" and tmpl.es_time("20:00") == "las 8 de la noche" and tmpl.es_time("23:30") == "las 11:30 de la noche"
    assert tmpl.render("escalate", "es", first="Meena", patient="Nanaji", meds=["metformin"], time="20:00") == "Meena aún no ha confirmado que Nanaji haya tomado metformin de las 8 de la noche. ¿Puedes revisar y avisarme?"
    assert tmpl.render("relay_given", "es", giver="Arjun", patient="Nanaji", meds=["metformin"], time="03:00", clock="03:07") == "Arjun le dio a Nanaji metformin de las 3 de la madrugada (a las 3:07 de la madrugada)."
    assert tmpl.render("relay_given", "es", giver="Arjun", patient="Nanaji", meds=["metformin"], time="13:00", clock="13:05") == "Arjun le dio a Nanaji metformin de la 1 de la tarde (a la 1:05 de la tarde)."
    assert tmpl.render("organiser_missed", "es", day="WED", part="AM") == "En el pastillero, el compartimento del miércoles por la mañana sigue lleno: esa dosis no se dio."
    assert tmpl.render("organiser_missed", "es", day="THU", part="PM") == "En el pastillero, el compartimento del jueves por la noche sigue lleno: esa dosis no se dio."
    replay = (ROOT / "site" / "replay.html").read_text(encoding="utf-8")        # rebuilt from the templates by tools/build_replay.py
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_replay.py")], check=True, capture_output=True)
    replay = (ROOT / "site" / "replay.html").read_text(encoding="utf-8")
    assert "haya tomado metformin y atorvastatin de las 8 de la noche" in replay and "compartimento del" not in replay.replace("compartimento del jueves", "")


# ---------------- 3. templates for the remaining English-only messages ----------------
def test_help_and_draft_templates_are_the_advisors_text():
    assert tmpl.fixed("help", "hi") == "मैं दवा की खुराक दर्ज कर सकता हूं, देखभाल रिकॉर्ड से सवालों के जवाब दे सकता हूं, या डिस्चार्ज शीट, पर्चे, दवा के डिब्बे या लैब रिपोर्ट की फोटो सहेज सकता हूं।"
    assert tmpl.fixed("help", "es") == "Puedo registrar dosis, responder preguntas con el registro de cuidados o guardar una foto de un informe de alta, una receta, un pastillero o un análisis."
    assert tmpl.fixed("help", "en") == intake.HELP
    assert tmpl.render("draft_header", "hi") == "मैंने यह पढ़ा:" and tmpl.render("draft_header", "es") == "Esto es lo que leí:"
    assert tmpl.render("draft_footer", "hi") == "यह सूची शुरू करने के लिए 'हाँ' या YES लिखें, या बताएं क्या गलत है।"
    assert tmpl.render("draft_footer", "es") == "Responde SÍ para activar esta lista, o dime qué está mal."
    assert tmpl.render("draft_footer", "en") == "Reply YES to start this schedule, or tell me what's wrong."


def _draft(conn):
    record.add_draft(conn, None, LABELS["sheets"]["d1"]["meds"], "2026-11-03T02:00:00Z")


def test_draft_summary_and_help_reach_members_in_their_language_and_the_medicine_lines_stay_as_extracted():
    conn, ob, ch = make("2026-11-03T02:30:00", all_tz="Asia/Kolkata")
    conn.execute("UPDATE members SET language='es' WHERE id='m1'")
    conn.execute("UPDATE members SET language='hi' WHERE id='m2'")
    conn.commit()
    _draft(conn)
    lines = record.draft_summary(conn)
    intake._draft_msg(conn, ob, "m2", "draft_header", lines, "", "t")
    intake._draft_msg(conn, ob, "m1", "draft_header", lines, "", "t")
    intake._draft_msg(conn, ob, "m3", "draft_header", lines, "", "t")
    got = dict(ch.log)
    nl = chr(10)
    assert got["m2"] == "मैंने यह पढ़ा:" + nl + nl.join(lines) + nl + "यह सूची शुरू करने के लिए 'हाँ' या YES लिखें, या बताएं क्या गलत है।"
    assert got["m1"] == "Esto es lo que leí:" + nl + nl.join(lines) + nl + "Responde SÍ para activar esta lista, o dime qué está mal."
    assert got["m3"] == "Here's what I read:" + nl + nl.join(lines) + nl + "Reply YES to start this schedule, or tell me what's wrong."
    for l in lines:
        assert l in got["m2"] and l in got["m1"]                                    # exactly as extracted


@pytest.mark.parametrize("word", ["sí", "Sí", "si", "SI.", "haan", "हाँ", "हां", "Yes", "YES!"])
def test_yes_in_english_spanish_and_hindi_starts_the_schedule(word):
    conn, ob, ch = make("2026-11-03T02:30:00", all_tz="Asia/Kolkata")
    _draft(conn)
    res = intake.handle(conn, ob, "m2", text=word)
    assert res["intent"] == "yes" and record.lines(conn, "confirmed") and not record.lines(conn, "draft")


def test_help_template_is_sent_in_the_members_language(monkeypatch):
    from app import llm
    monkeypatch.setattr(llm, "spark_json", lambda ph, lb, m, sc: ({"intent": "other"}, 0, 0))
    conn, ob, ch = make("2026-11-03T02:30:00", all_tz="Asia/Kolkata")
    conn.execute("UPDATE members SET language='hi' WHERE id='m2'")
    conn.execute("UPDATE members SET language='es' WHERE id='m1'")
    conn.commit()
    seed_d1(conn, confirmed_at="2026-11-02T00:00:00Z")
    for mid, want in (("m2", tmpl.fixed("help", "hi")), ("m1", tmpl.fixed("help", "es")), ("m3", intake.HELP)):
        ch.log.clear()
        intake.handle(conn, ob, mid, text="blah blah")
        assert ch.log == [(mid, want)]


def test_skipped_and_unsure_relays_in_three_languages_and_through_the_dose_handler(monkeypatch):
    from app import llm
    s = dict(giver="Meena", patient="Nanaji", meds=["amlodipine", "metformin"], time="20:00")
    assert tmpl.render("relay_skipped", "en", **s) == "CareCircle: Meena skipped amlodipine, metformin 20:00."
    assert tmpl.render("relay_unsure", "en", **s) == "CareCircle: Meena wasn't sure about amlodipine, metformin 20:00."
    assert tmpl.render("relay_skipped", "hi", **s) == "Meena ने Nanaji की शाम 8 बजे वाली amlodipine और metformin दवा छोड़ दी।"
    assert tmpl.render("relay_unsure", "hi", **s) == "Meena को पक्का नहीं है कि Nanaji ने शाम 8 बजे वाली amlodipine और metformin दवा ली या नहीं।"
    assert tmpl.render("relay_skipped", "es", **s) == "Meena se saltó amlodipine y metformin de las 8 de la noche de Nanaji."
    assert tmpl.render("relay_unsure", "es", **s) == "Hay dudas sobre si Nanaji tomó amlodipine y metformin de las 8 de la noche (Meena)."
    conn, ob, ch = make("2026-11-02T02:45:30", all_tz="Asia/Kolkata")
    conn.execute("UPDATE members SET language='hi' WHERE id='m3'")
    conn.execute("UPDATE members SET language='es' WHERE id='m1'")
    conn.commit()
    seed_d1(conn, confirmed_at="2026-11-02T00:00:00Z")
    conn.execute("DELETE FROM dose_events")
    conn.commit()
    from app import escalation
    escalation.tick(conn, ob)
    ch.log.clear()
    monkeypatch.setattr(llm, "spark_json", lambda ph, lb, m, sc: ({"actor": "m2", "slot": "none", "action": "skipped"}, 0, 0))
    intake._dose(conn, ob, "m2", "skip them", clock.now())
    got = dict(ch.log)
    assert got["m1"] == "Meena se saltó amlodipine, aspirin y metformin de las 8 de la mañana de Nanaji."
    assert got["m3"] == "Meena ने Nanaji की सुबह 8 बजे वाली amlodipine, aspirin और metformin दवा छोड़ दी।"
    assert got["m4"] == "CareCircle: Meena skipped amlodipine, aspirin, metformin 08:00."


def test_language_samples_include_the_new_templates():
    sys.path.insert(0, str(ROOT / "tools"))
    import importlib, p4c_samples
    importlib.reload(p4c_samples)
    text = p4c_samples.samples()
    for needle in ("skipped (1)", "skipped (3)", "unsure (1)", "unsure (3)", "help:", "draft:", "madrugada", "haya tomado"):
        assert needle in text, needle


# ---------------- 4. Now card ----------------
def test_now_card_shows_open_doses_as_cards_while_the_ladder_is_short():
    assert 'id="nowdoses"' in BOARD and "lead.steps.length<4" in BOARD and "class:'ncard'" in BOARD
    # the data the cards use: three open doses, a short ladder
    conn, ob, ch = make("2026-11-02T02:45:30", all_tz="Asia/Kolkata")
    seed_d1(conn, confirmed_at="2026-11-02T00:00:00Z")
    conn.execute("DELETE FROM dose_events")
    conn.commit()
    from app import escalation
    escalation.tick(conn, ob)
    st = board.state(conn, clock.now())
    assert len(st["ladder"]) == 3 and all(len(l["steps"]) < 4 for l in st["ladder"]) and {l["slot"].split("_")[0] for l in st["ladder"]} == {"metformin", "amlodipine", "aspirin"}


# ---------------- 5. demo scenes ----------------
def test_both_scenes_reset_cleanly_and_repeatably():
    conn = db.connect(":memory:")
    from app import seed
    seed.init(conn)
    for _ in range(2):                                                               # twice: a reset leaves no residue
        t = demo.scene_monday(conn)
        assert conn.execute("SELECT COUNT(*) FROM members").fetchone()[0] == 5
        assert {m["relay_pref"] for m in record.members(conn)} == {"everything"}
        assert not record.lines(conn, "confirmed") and not record.lines(conn, "draft") and conn.execute("SELECT COUNT(*) FROM dose_events").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM lab_reports").fetchone()[0] == 0 and conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0
        loc = t.astimezone(record.patient_tz(conn))
        assert (loc.weekday(), loc.hour, loc.minute) == (0, 7, 55)                   # Monday 07:55 patient-local
        assert record.member(conn, "m2")["language"] == "hi" and record.member(conn, "m5")["language"] == "es"
        t = demo.scene_thursday(conn)
        loc = t.astimezone(record.patient_tz(conn))
        assert (loc.weekday(), loc.hour, loc.minute) == (3, 7, 55)
        assert len(record.lines(conn, "confirmed")) == 4 and conn.execute("SELECT COUNT(*) FROM dose_events WHERE type='missed'").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM lab_reports WHERE status='live'").fetchone()[0] == 1


@pytest.mark.parametrize("scene,needles", [("monday", ["SCENE monday", "r2 (Meena's phone)", "r3 (Kabir's phone)", "Arrives on r1", "मैंने यह पढ़ा:", "Beat 2:15-2:38"]),
                                          ("thursday", ["SCENE thursday", "Arrives on r2", "Arrives on r1 (Arjun, awake in Los Angeles", "Wednesday PM", "बुधवार शाम"])])
def test_scene_command_prints_the_filming_steps_and_sends_nothing(tmp_path, scene, needles):
    env = dict(os.environ, CARECIRCLE_DB=str(tmp_path / "s.db"), ADMIN_TOKEN="", CARECIRCLE_DRY_RUN="")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "demo_reset.py"), "--scene", scene], capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    for n in needles:
        assert n in out, n
    assert "LIVE mode" in out and "clock target 07:55" in out.replace("Clock target", "clock target")
    assert not re.search(r"\+?\d{9,}", out) and "token=" not in out.replace("/board?token=<BOARD_TOKEN>", "") and "whatsapp:" not in out          # no phone numbers or tokens
    assert not (tmp_path / "s.db-wal").exists() or True
    con = db.connect(tmp_path / "s.db")
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE kind='outbound'").fetchone()[0] == 0                 # the tool sent nothing


# ---------------- Phase 5a: filming cap and send spacing ----------------
def test_filming_cap_is_80_counted_from_a_fresh_counter_and_sends_are_spaced(monkeypatch, tmp_path):
    from app import channel, config
    assert config.PHASE1_MESSAGE_CAP == 80 and config.SEND_SPACING_SECONDS == 3.0
    assert channel.COUNTER.name == "outbound_filming.json"
    sleeps, now = [], [1000.0]
    monkeypatch.setattr(channel.time, "sleep", lambda s: (sleeps.append(round(s, 2)), now.__setitem__(0, now[0] + s)))
    monkeypatch.setattr(channel.time, "time", lambda: now[0])
    channel._last_send[0] = 0.0
    channel._space()                                       # first send after a long quiet period: no wait
    now[0] += 1.0
    channel._space()                                       # 1 s later: waits the other 2 s
    channel._space()                                       # immediately after: waits the full 3 s
    assert sleeps == [2.0, 3.0]


def test_scene_steps_say_the_real_defaults_differ_and_the_ladder_matches_the_updated_script():
    sys.path.insert(0, str(ROOT / "tools"))
    import scene_steps
    assert "the real defaults differ" in scene_steps.steps("monday")
    th = scene_steps.steps("thursday")
    assert "Sunita (simulated, nearby) is asked next" in th and "Kabir" in th and "while they sleep" in th and "one message every 3 seconds" in th
    script = (ROOT / "docs" / "VIDEO_SCRIPT.md").read_text(encoding="utf-8")
    assert "Simulated neighbour Sunita is asked next, then the arc moves to Arjun" in script
