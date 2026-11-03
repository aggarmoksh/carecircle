"""The README: every relative link and image resolves to a file in the repository, the Pages link maps to docs/replay.html, and docs/replay.html is the same page as site/replay.html."""
import pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGES = "https://aggarmoksh.github.io/carecircle/replay.html"
PLACEHOLDERS = {"VIDEO_LINK"}                    # the demo video link is supplied later


def _targets(text):
    return re.findall(r"\]\(([^)\s]+)\)", text)


def test_readme_links_and_images_resolve():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    links = _targets(readme)
    assert PAGES in links and (ROOT / "docs" / "replay.html").exists()          # the Pages address serves docs/replay.html
    for l in links:
        if l in PLACEHOLDERS or l.startswith("http"):
            continue
        assert (ROOT / l.split("#")[0]).exists(), l
    for img in ("board-desktop.png", "board-phone.png", "today-card.png", "doctor-summary.png", "escalation.gif"):
        assert f"docs/img/{img}" in readme and (ROOT / "docs" / "img" / img).exists(), img


def test_docs_replay_is_the_same_page_as_site_replay():
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_replay.py")], check=True, capture_output=True)
    assert (ROOT / "docs" / "replay.html").read_bytes() == (ROOT / "site" / "replay.html").read_bytes()


def test_other_docs_links_resolve():
    for d in ("docs/ARCHITECTURE.md", "docs/EVALS.md"):
        p = ROOT / d
        for l in _targets(p.read_text(encoding="utf-8")):
            if not l.startswith("http"):
                assert (p.parent / l.split("#")[0]).exists(), (d, l)
