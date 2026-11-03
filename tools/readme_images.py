"""Build the README images in docs/img/ from the fictional Thursday scene (data/shots.db, a throwaway database): board-desktop.png (1440x900), board-phone.png (390x844),
today-card.png (1080x1350), doctor-summary.png (first page) and escalation.gif (silent, 1200 px wide). Headless Chrome, so no browser chrome in the pictures; the board is loaded with
?live=0 (one fetch, no stream). Fictional data only; the board token used here is a throwaway string, not a real one.
Usage: python tools/readme_images.py"""
import os, pathlib, subprocess, sys, time
import httpx
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "img"
TMP = ROOT / "outputs" / "_frames"
CHROME = os.environ.get("CHROME_PATH") or "C:/Program Files/Google/Chrome/Application/chrome.exe"
PY = sys.executable
TOKEN = "shotstoken"
PORT = 8011
# (ticks of the scheduler so far, server clock at capture): 08:28:29 Meena nudged; 08:29:30 Sunita asked; 08:30:31 Arjun asked; 08:31:32 Kabir and Sofia skipped (03:01 in London)
STATES = [(1, "2026-11-05T02:58:40Z"), (2, "2026-11-05T02:59:40Z"), (3, "2026-11-05T03:00:40Z"), (4, "2026-11-05T03:01:40Z")]


def build(ticks):
    env = dict(os.environ, SHOT_TICKS=str(ticks), SHOT_SUNITA_STOP="0", PYTHONIOENCODING="utf-8")
    subprocess.run([PY, str(ROOT / "tools" / "make_shots_db.py")], cwd=ROOT, env=env, check=True, capture_output=True)


def serve(start):
    env = dict(os.environ, CC_START_TIME=start, CARECIRCLE_DB=str(ROOT / "data" / "shots.db"), BOARD_TOKEN=TOKEN, CC_TICKER="0", PUBLIC_BASE_URL="https://example.invalid", CARECIRCLE_DRY_RUN="1")
    p = subprocess.Popen([PY, "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(PORT)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/board?token={TOKEN}", timeout=2).status_code == 200:
                return p
        except Exception:
            time.sleep(0.5)
    p.terminate()
    raise SystemExit("server did not start")


def shot(url, out, w, h, budget=6000, extra=()):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--virtual-time-budget={budget}", f"--window-size={w},{h}", *extra, f"--screenshot={out}", url],
                   check=True, timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, (ticks, start) in enumerate(STATES):
        build(ticks)
        srv = serve(start)
        try:
            f = TMP / f"s{i}.png"
            shot(f"http://127.0.0.1:{PORT}/board?token={TOKEN}&theme=light&live=0", f, 1440, 900)
            frames.append(f)
            if i == len(STATES) - 1:                                   # the final state is the still, the phone, the card and the summary
                Image.open(f).convert("RGB").save(OUT / "board-desktop.png", optimize=True)
                page = TMP / "phone.html"
                page.write_text(f'<!doctype html><body style="margin:0;background:#fff"><iframe src="http://127.0.0.1:{PORT}/board?token={TOKEN}&theme=light&live=0" width="390" height="844" style="border:0;display:block"></iframe>', encoding="utf-8")
                shot(page.as_uri(), TMP / "phone.png", 500, 844, 8000)
                im = Image.open(TMP / "phone.png").convert("RGB")
                im.crop((0, 0, 390, min(844, im.height))).save(OUT / "board-phone.png", optimize=True)
                shot(f"http://127.0.0.1:{PORT}/doctor?token={TOKEN}&from=2026-11-02&to=2026-11-05", TMP / "doc.png", 900, 1273, 4000, ("--force-device-scale-factor=1.5",))
        finally:
            srv.terminate()
            srv.wait(10)
    # the Today card, from the same database and clock
    code = ("import os,sys;sys.path.insert(0,r'%s');os.environ['CARECIRCLE_DB']=r'%s';from datetime import datetime,timezone;from app import db,board,cards;from app.clock import clock;"
            "clock.set(datetime(2026,11,5,3,1,40,tzinfo=timezone.utc),speed=0);c=db.connect();cards.render_png(cards.card_html(board.state(c)),r'%s')" % (ROOT, ROOT / "data" / "shots.db", OUT / "today-card.png"))
    subprocess.run([PY, "-c", code], cwd=ROOT, check=True, capture_output=True, timeout=120)
    # first page of the doctor summary, cropped to the content
    d = Image.open(TMP / "doc.png").convert("RGB")
    from PIL import ImageChops
    box = ImageChops.difference(d, Image.new("RGB", d.size, d.getpixel((4, 4)))).getbbox()      # the page itself, without the empty canvas around it
    d = d.crop((max(box[0] - 24, 0), max(box[1] - 24, 0), min(box[2] + 24, d.width), min(box[3] + 24, d.height)))
    d.save(OUT / "doctor-summary.png", optimize=True)
    # the gif: the ladder advancing (three states) with short cross-fades, 1200 px wide, about 6.5 s
    crop = [Image.open(f).convert("RGB").crop((0, 0, 1440, 720)).resize((1200, 600), Image.LANCZOS) for f in frames]
    seq, dur = [], []
    for k, im in enumerate(crop):
        seq.append(im)
        dur.append(1500 if k < len(crop) - 1 else 2000)
        if k < len(crop) - 1:
            for a in (0.33, 0.66):
                seq.append(Image.blend(im, crop[k + 1], a))
                dur.append(110)
    pal = [im.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for im in seq]
    pal[0].save(OUT / "escalation.gif", save_all=True, append_images=pal[1:], duration=dur, loop=0, optimize=True, disposal=2)
    for p in sorted(OUT.iterdir()):
        im = Image.open(p)
        print(f"{p.name}: {im.size[0]}x{im.size[1]}, {p.stat().st_size // 1024} KB" + (f", {sum(dur) / 1000:.1f} s, {getattr(im, 'n_frames', 1)} frames" if p.suffix == ".gif" else ""))


if __name__ == "__main__":
    main()
