"""The Today card: a 1080 x 1350 PNG of The Circle plus today's doses (docs/DESIGN.md v2), rendered on the server.
The HTML is built here from the board state and screenshotted with headless Chrome (no Playwright dependency; set CHROME_PATH to override).
Each card has an unguessable id; it is served at /card/<id>.png and expires 24 hours after it was made. Read-only; says nothing about any value."""
import hashlib, html, json, math, os, pathlib, secrets, shutil, subprocess, tempfile
from datetime import datetime, timedelta, timezone
from . import board
from .clock import clock

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIR = ROOT / "outputs" / "cards"
E = html.escape
TTL_HOURS = 24
SWORD = {"given": "given", "not_yet_due": "not yet due", "due": "due, not confirmed", "overdue": "overdue, escalating", "skipped": "skipped", "unsure": "unsure", "missed": "missed"}
COLORS = dict(canvas="#FAF7F2", surface="#FFFFFF", ink="#1C2733", muted="#5B6672", line="#E7E1D8", accent="#E8833A", within="#1F8A70", outside="#B26B00", missed="#6B5B95", sim="#9AA3AD")


def _clock12(t):
    h, m = (int(x) for x in t.split(":"))
    return f"{(h % 12) or 12}{':%02d' % m if m else ''} {'AM' if h < 12 else 'PM'}"


def state_hash(s):
    """Changes when a dose changes state or a ladder step happens; not every minute."""
    key = [(d["slot"], d["status"], d.get("by")) for d in s["doses"]] + [(l["slot"], len(l["steps"])) for l in s["ladder"]] + [s["patient_local"][:10]]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]


def circle_svg(s, w=968, h=660):
    cx, cy, R = w / 2, h / 2 + 16, {"hands_on": 122, "remote": 214}
    pos = {}
    for role in ("hands_on", "remote"):
        g = [m for m in s["members"] if (m["role"] == "hands_on") == (role == "hands_on")]
        off = -50 if role == "hands_on" else -95
        for i, m in enumerate(g):
            a = math.radians(off + i * 360 / max(len(g), 1))
            pos[m["id"]] = (cx + R[role] * math.cos(a), cy + R[role] * math.sin(a))
    c = COLORS
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="Inter,Segoe UI,system-ui,sans-serif">']
    o += [f'<circle cx="{cx}" cy="{cy}" r="{R[k]}" fill="none" stroke="{c["line"]}" stroke-width="2"/>' for k in R]
    steps = [x for l in s["ladder"] for x in l["steps"]][-6:]
    seen = []
    for st in steps:                                   # the ladder: one arc from the patient to each member who was asked
        if st["actor"] in pos and st["actor"] not in seen:
            seen.append(st["actor"])
            x, y = pos[st["actor"]]
            mx, my = (cx + x) / 2 + (y - cy) * 0.18, (cy + y) / 2 - (x - cx) * 0.18
            o.append(f'<path d="M{cx},{cy} Q{mx:.1f},{my:.1f} {x:.1f},{y:.1f}" fill="none" stroke="{c["accent"]}" stroke-width="5" stroke-linecap="round"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="74" fill="{c["canvas"]}" stroke="{c["line"]}" stroke-width="2"/>')
    o.append(f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" font-size="30" font-weight="600" fill="{c["ink"]}">{E(s["patient"])}</text>')
    o.append(f'<text x="{cx}" y="{cy + 30}" text-anchor="middle" font-size="26" fill="{c["muted"]}">{E(s["patient_local"][-5:])}</text>')
    for m in s["members"]:
        x, y = pos[m["id"]]
        hot = m["id"] in seen
        dash = ' stroke-dasharray="8 6"' if m["simulated"] else ""
        op = ' opacity=".45"' if m["relay"] == "stop" else ""
        o.append(f'<g{op}><circle cx="{x:.1f}" cy="{y:.1f}" r="40" fill="{c["surface"]}" stroke="{c["accent"] if hot else (c["sim"] if m["simulated"] else "#8A939D")}" stroke-width="{5 if hot else 3}"{dash}/>')
        o.append(f'<text x="{x:.1f}" y="{y + 10:.1f}" text-anchor="middle" font-size="30" font-weight="600" fill="{c["ink"]}">{E(m["name"][:1])}</text>')
        side = x < cx - 150                                   # a far-left node: label to its left, clear of the inner ring's labels
        below = y >= cy
        ax, anchor, ly = (x - 54, "end", y + 2) if side else (x, "middle", y + 82 if below else y - 84)
        o.append(f'<text x="{ax:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-size="28" font-weight="600" fill="{c["ink"]}">{E(m["name"])}</text>')
        o.append(f'<text x="{ax:.1f}" y="{ly + 29:.1f}" text-anchor="{anchor}" font-size="24" fill="{c["muted"]}">{E(m["local"])} · {"awake" if m["awake"] else "asleep"}</text></g>')
    o.append("</svg>")
    return "".join(o)


def _marker(status):
    c = COLORS
    if status == "given":
        return f'<svg width="44" height="44" viewBox="0 0 44 44"><circle cx="22" cy="22" r="20" fill="{c["within"]}"/><path d="M12 23l7 7 13-14" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    if status in ("overdue", "due", "unsure"):
        return f'<svg width="44" height="44" viewBox="0 0 44 44"><circle cx="22" cy="22" r="19" fill="#FFF4E0" stroke="{c["outside"]}" stroke-width="4"/><path d="M22 12v12M22 30v2" stroke="{c["outside"]}" stroke-width="4" stroke-linecap="round"/></svg>'
    if status in ("missed", "skipped"):
        return f'<svg width="44" height="44" viewBox="0 0 44 44"><circle cx="22" cy="22" r="19" fill="none" stroke="{c["missed"]}" stroke-width="4"/><path d="M14 14l16 16M30 14L14 30" stroke="{c["missed"]}" stroke-width="4" stroke-linecap="round"/></svg>'
    return f'<svg width="44" height="44" viewBox="0 0 44 44"><circle cx="22" cy="22" r="19" fill="none" stroke="#B8C0C8" stroke-width="4" stroke-dasharray="6 5"/></svg>'


def card_html(s):
    c = COLORS
    rows = []
    for d in s["doses"]:
        by = f' by {E(d["by"])}' if d.get("by") and d["status"] == "given" else ""
        rows.append(f'<div class="r">{_marker(d["status"])}<div><b>{E(d["medicine"])}</b> <span class="t">{_clock12(d["time"])}</span><div class="s">{SWORD.get(d["status"], d["status"])}{by}</div></div></div>')
    day = E(s["patient_local"][:10])
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>*{{box-sizing:border-box}}body{{margin:0;width:1080px;height:1350px;background:{c["canvas"]};color:{c["ink"]};'
            f'font-family:Inter,"Segoe UI",system-ui,sans-serif;overflow:hidden}}.w{{padding:52px 56px}}.top{{display:flex;justify-content:space-between;align-items:baseline}}'
            f'.brand{{font-size:46px;font-weight:700}}.brand i{{color:{c["accent"]};font-style:normal}}.date{{font-size:34px;color:{c["muted"]}}}'
            f'.sub{{font-size:32px;color:{c["muted"]};margin:6px 0 0}}.sub b{{color:{c["ink"]}}}.card{{background:{c["surface"]};border:2px solid {c["line"]};border-radius:32px;margin-top:24px;padding:12px}}'
            f'h2{{font-size:40px;margin:30px 0 14px}}.g{{display:grid;grid-template-columns:1fr 1fr;gap:14px 28px}}.r{{display:flex;gap:18px;align-items:center;font-size:36px;line-height:44px}}'
            f'.r .t{{color:{c["muted"]};font-size:32px}}.r .s{{font-size:30px;color:{c["muted"]};line-height:36px}}.foot{{position:absolute;left:56px;bottom:40px;font-size:26px;color:{c["muted"]}}}</style></head>'
            f'<body><div class="w"><div class="top"><div class="brand">CareCircle<i>.</i></div><div class="date">{day}</div></div>'
            f'<div class="sub">Caring for <b>{E(s["patient"])}</b> · {E(s["patient_local"][-5:])} local time</div><div class="card">{circle_svg(s)}</div>'
            f'<h2>Today</h2><div class="g">{"".join(rows) or "<div class=sub>No doses scheduled.</div>"}</div></div>'
            f'<div class="foot">Not medical advice. Board is optional.</div></body></html>')


def chrome():
    p = os.environ.get("CHROME_PATH")
    for cand in ([p] if p else []) + ["C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"]:
        if cand and pathlib.Path(cand).exists():
            return cand
    return shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("chrome")


def render_png(html_text, out_path):
    """Screenshot `html_text` at 1080 x 1350 into out_path with headless Chrome."""
    exe = chrome()
    if not exe:
        raise RuntimeError("no Chrome found (set CHROME_PATH)")
    out_path = pathlib.Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "card.html"
        f.write_text(html_text, encoding="utf-8")
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1", "--window-size=1080,1350",
                        f"--screenshot={out_path}", "--virtual-time-budget=2000", f.as_uri()], check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not out_path.exists():
        raise RuntimeError("card was not rendered")
    return out_path


def current(conn, s=None):
    """The id of today's card for the current state (a new unguessable id when the state changed or the last one expired)."""
    s = s or board.state(conn)
    h = state_hash(s)
    now = clock.now()
    r = conn.execute("SELECT id, created_at FROM cards WHERE state_hash=? ORDER BY created_at DESC LIMIT 1", (h,)).fetchone()
    if r and now - datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) < timedelta(hours=TTL_HOURS - 1):
        return r["id"]
    cid = secrets.token_urlsafe(18)
    conn.execute("INSERT INTO cards(id,state_hash,created_at) VALUES(?,?,?)", (cid, h, clock.iso()))
    conn.commit()
    return cid


def png_path(conn, cid):
    """Path of the card's PNG (rendered on first request), or None when the id is unknown or older than 24 hours."""
    r = conn.execute("SELECT created_at FROM cards WHERE id=?", (cid,)).fetchone()
    if not r or clock.now() - datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= timedelta(hours=TTL_HOURS):
        return None
    p = DIR / f"{cid}.png"
    if not p.exists():
        render_png(card_html(board.state(conn)), p)
    return p


def purge(conn):
    """Delete expired cards (rows and files)."""
    for r in conn.execute("SELECT id, created_at FROM cards").fetchall():
        if clock.now() - datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= timedelta(hours=TTL_HOURS):
            (DIR / f"{r['id']}.png").unlink(missing_ok=True)
            conn.execute("DELETE FROM cards WHERE id=?", (r["id"],))
    conn.commit()
