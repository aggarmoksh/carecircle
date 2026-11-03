"""Phase 4c: the replay page is one self-contained file with fictional data; both branches play (checked in headless Chrome when it is installed)."""
import pathlib, re, subprocess, sys, shutil
import pytest
from app import cards

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "site" / "replay.html"


def _build():
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_replay.py")], check=True, capture_output=True)
    return PAGE.read_text(encoding="utf-8")


def test_replay_is_self_contained_labelled_and_fictional():
    html = _build()
    assert "Interactive replay with fictional data. The real system runs on WhatsApp: see the video." in html.replace("<b>", "").replace("</b>", "")
    assert not re.search(r"https?://", html) and "<link" not in html and "src=" not in html and "fetch(" not in html and "XMLHttpRequest" not in html   # nothing leaves the page
    for key in ("MODEL_API_KEY", "TWILIO", "token=", "sk-", "whatsapp:"):
        assert key not in html
    assert "शाम 8 बजे" in html and "las 8 de la noche" in html          # the real templates, in Hindi and Spanish
    assert "prefers-color-scheme" in html and "prefers-reduced-motion" in html and "max-width:900px" in html


@pytest.mark.skipif(not cards.chrome(), reason="no Chrome on this machine")
@pytest.mark.parametrize("branch,expect,absent", [("done", ["given by Meena", "Meena replied: done.", "दर्ज हो गया"], ["still full"]),
                                                  ("ignore", ["Arjun was skipped: asleep", "asked Kabir", "still full: that dose wasn't given", "Try &quot;Reply done&quot; instead"], ["given by Meena"])])
def test_both_branches_play_to_the_end(branch, expect, absent):
    _build()
    out = subprocess.run([cards.chrome(), "--headless=new", "--disable-gpu", "--virtual-time-budget=20000", "--dump-dom", f"{PAGE.as_uri()}?auto={branch}&fast=1&theme=light"],
                         capture_output=True, text=True, timeout=90, encoding="utf-8").stdout
    out = re.sub(r"<script.*?</script>", "", out, flags=re.S)          # only what the page rendered, not its source
    for e in expect:
        assert e in out or e.replace("&quot;", '"') in out, e
    for a in absent:
        assert a not in out, a
    assert 'id="again"' in out and 'id="again" hidden' not in out          # the end-of-scene buttons are showing
