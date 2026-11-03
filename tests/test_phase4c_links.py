"""Phase 4c: personal board links (hashed, revocable), link previews, the Today card, the 'board' command, the live stream."""
import pathlib, shutil
import pytest
from datetime import timedelta
from helpers import make, seed_d1, advance
from app import db, links, cards, intake, record, board
from app.clock import clock


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_TICKER", "0")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(cards, "DIR", tmp_path / "cards")
    monkeypatch.setattr(cards, "render_png", lambda html, out: (pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True), pathlib.Path(out).write_bytes(b"\x89PNG fake"), pathlib.Path(out))[2])
    monkeypatch.setenv("BOARD_TOKEN", "board-test-token")
    monkeypatch.setenv("ADMIN_TOKEN", "admin-test-token")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.invalid")
    from app import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as c:
        yield c


def test_member_tokens_are_personal_hashed_and_revocable(client):
    conn = db.connect()
    toks = {m: links.token_for(conn, m) for m in ("m1", "m2", "m3")}
    assert len(set(toks.values())) == 3
    stored = " ".join(r[0] for r in conn.execute("SELECT token_hash FROM board_tokens"))
    assert not any(t in stored for t in toks.values())                              # only hashes are stored
    for m, t in toks.items():
        assert links.verify(conn, t) == m
        assert client.get(f"/api/state?token={t}").status_code == 200
        assert client.get(f"/board?token={t}").status_code == 200
        assert client.post("/admin/clock", json={"speed": 0}, headers={"X-Admin-Token": t}).status_code == 403     # a member link is never admin
    assert client.post("/admin/revoke", json={"member": "m2"}).status_code == 403
    assert client.post("/admin/revoke", json={"member": "m2"}, headers={"X-Admin-Token": "admin-test-token"}).json() == {"revoked": 1}
    assert client.get(f"/api/state?token={toks['m2']}").status_code == 403           # the revoked link is refused everywhere
    assert client.get(f"/board?token={toks['m2']}").status_code == 403
    assert client.get(f"/doctor?token={toks['m2']}").status_code == 403
    assert client.get(f"/api/state?token={toks['m1']}").status_code == 200           # the others still work
    new = links.token_for(conn, "m2")
    assert new != toks["m2"] and client.get(f"/api/state?token={new}").status_code == 200


def test_board_page_has_link_preview_tags_and_card_expires_after_24_hours(client):
    html = client.get("/board?token=board-test-token").text
    import re
    img = re.search(r'property="og:image" content="(https://example.invalid/card/[^"]+\.png)"', html)
    assert img and 'property="og:title"' in html and 'property="og:description"' in html and 'content="1080"' in html and "noindex" in html
    path = img.group(1).replace("https://example.invalid", "")
    r = client.get(path)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get("/card/not-a-real-card.png").status_code == 404
    clock.set(clock.now() + timedelta(hours=25), speed=0)
    assert client.get(path).status_code == 404                                      # expired


def test_board_command_sends_the_card_in_the_members_language_with_their_own_link():
    for text, lang, start in (("board", "en", "Today for Nanaji."), ("बोर्ड", "hi", "आज की स्थिति, Nanaji।"), ("tablero", "es", "Hoy, Nanaji.")):
        conn, ob, ch = make("2026-11-03T08:30:00", all_tz="Asia/Kolkata")
        conn.execute("UPDATE members SET language=? WHERE id='m2'", (lang,))
        conn.commit()
        seed_d1(conn, confirmed_at="2026-11-02T00:00:00Z")
        assert intake.handle(conn, ob, "m2", text=text)["intent"] == "board"
        (mid, caption), = ch.log
        assert mid == "m2" and caption.startswith(start) and "token=" + links.token_for(conn, "m2") in caption
        assert len(ch.media) == 1 and ch.media[0][1].startswith("http") and ch.media[0][1].endswith(".png")


@pytest.mark.skipif(not cards.chrome(), reason="no Chrome on this machine")
def test_card_renders_as_a_1080_by_1350_png(tmp_path):
    from PIL import Image
    conn, ob, ch = make("2026-11-03T02:45:30", all_tz="Asia/Kolkata")
    seed_d1(conn, confirmed_at="2026-11-02T00:00:00Z")
    out = cards.render_png(cards.card_html(board.state(conn, clock.now())), tmp_path / "c.png")
    assert Image.open(out).size == (1080, 1350)


def test_card_is_made_for_each_change_of_state_not_each_minute():
    conn, ob, ch = make("2026-11-03T02:45:30", all_tz="Asia/Kolkata")
    seed_d1(conn, confirmed_at="2026-11-02T00:00:00Z")
    a = cards.current(conn)
    advance(60)
    assert cards.current(conn) == a
    record.add_event(conn, "metformin_08:00", clock.now().astimezone(record.patient_tz(conn)).date(), "confirmed", "m2", "m2", "t", None, record.iso(clock.now()))
    assert cards.current(conn) != a


def test_daily_summary_carries_the_card_and_the_board_line():
    conn, ob, ch = make("2026-11-03T14:40:00", all_tz="Asia/Kolkata")               # 20:10 in Kolkata
    seed_d1(conn, confirmed_at="2026-11-02T00:00:00Z")
    conn.execute("UPDATE members SET relay_pref='daily', language='es' WHERE id='m1'")
    conn.execute("UPDATE members SET tz='Asia/Kolkata' WHERE id='m1'")
    conn.commit()
    ob.relay_t("missed", dict(patient="Nanaji", meds=["metformin"], time="08:00"), [], "t")   # a plain relay is queued for the summary
    ob.flush_queue()
    msgs = [t for m, t in ch.log if m == "m1"]
    assert msgs and msgs[-1].startswith("Resumen diario de CareCircle:") and "Tablero (opcional): https://" in msgs[-1] and "No consta que Nanaji haya tomado metformin" in msgs[-1]
    assert any(m == "m1" for m, _ in ch.media)


def test_live_stream_pushes_state_first(client):
    with client.stream("GET", "/api/stream?token=board-test-token") as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("event:"):
                assert line == "event: state"
                break
    assert client.get("/api/stream?token=wrong").status_code == 403


def test_board_page_wires_the_doctor_link_theme_toggle_and_stream():
    html = open(pathlib.Path(board.__file__).with_name("board.html"), encoding="utf-8").read()
    for needle in ("'/doctor?token='", "new EventSource('/api/stream?token='", "localStorage.setItem('cc-theme'", "prefers-color-scheme", "prefers-reduced-motion", "safe-area-inset"):
        assert needle in html, needle
    assert html.count("try{localStorage") + html.count("try{localStorage.setItem") >= 1
