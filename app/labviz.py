"""Lab graphics as server-built SVG, shared by the board and the doctor summary.
Per test: the range the lab printed as a band, the reported value as a marker, status in words and a shape (never colour alone).
One-sided ranges are open-ended (the band runs off the end with an arrow); no range printed means no bar. Nothing here judges or explains a value."""
import html, re
from . import labs

E = html.escape
ICON = {"above": "▲", "below": "▼", "within": "●", "no_range": "–"}
WORD = {"above": "above the lab's printed range", "below": "below the lab's printed range", "within": "within the lab's printed range", "no_range": "no range printed"}
ORDER = {"above": 0, "below": 0, "within": 1, "no_range": 2}
INK, BAND, EDGE = "#15181d", "#d5dbe3", "#5b6573"


def _lo(t):
    return t.get("parsed_low", t.get("range_low"))


def _hi(t):
    return t.get("parsed_high", t.get("range_high"))


def _marker(x, y, status):
    """Shape per status so the state reads without colour: triangle up = above, triangle down = below, circle = within."""
    if status == "above":
        return f'<path d="M{x:.1f},{y-7:.1f} L{x-6:.1f},{y+5:.1f} L{x+6:.1f},{y+5:.1f} Z" fill="{INK}"/>'
    if status == "below":
        return f'<path d="M{x:.1f},{y+7:.1f} L{x-6:.1f},{y-5:.1f} L{x+6:.1f},{y-5:.1f} Z" fill="{INK}"/>'
    if status == "within":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="{INK}"/>'
    return f'<rect x="{x-4:.1f}" y="{y-4:.1f}" width="8" height="8" fill="none" stroke="{INK}" stroke-width="1.5"/>'


def _domain(vals, low, high):
    pts = list(vals) + [v for v in (low, high) if v is not None]
    mn, mx = min(pts), max(pts)
    span = (mx - mn) or abs(mx) or 1.0
    return mn - span * 0.35, mx + span * 0.35


def range_bar(t):
    """SVG bar for one test, or '' when the lab printed no range."""
    low, high = _lo(t), _hi(t)
    if low is None and high is None:
        return ""
    W, H, M, Y = 300, 56, 10, 36
    d0, d1 = _domain([t["value"]], low, high)
    X = lambda v: M + (v - d0) / (d1 - d0) * (W - 2 * M)
    x0, x1 = (X(low) if low is not None else M), (X(high) if high is not None else W - M)
    nums = re.findall(labs.NUM, t.get("range_text") or "")
    lo_txt = nums[0] if low is not None and nums else (labs.fmt_num(low) if low is not None else "")
    hi_txt = (nums[1] if len(nums) > 1 else nums[0]) if high is not None and nums else (labs.fmt_num(high) if high is not None else "")
    out = [f'<svg class="rbar" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{E(t["test"])}: {labs.fmt_num(t["value"])} {E(t["unit"])}, {WORD[t["status"]]}">',
           f'<rect x="{x0:.1f}" y="{Y-6}" width="{max(x1-x0, 1):.1f}" height="12" fill="{BAND}" stroke="{EDGE}" stroke-width="1"/>']
    if low is None:  # open to the left
        out.append(f'<path d="M{M+7},{Y-9} L{M},{Y} L{M+7},{Y+9}" fill="none" stroke="{EDGE}" stroke-width="1.5"/>')
    else:
        out.append(f'<text x="{x0:.1f}" y="{H-3}" text-anchor="middle">{E(lo_txt)}</text>')
    if high is None:  # open to the right
        out.append(f'<path d="M{W-M-7},{Y-9} L{W-M},{Y} L{W-M-7},{Y+9}" fill="none" stroke="{EDGE}" stroke-width="1.5"/>')
    else:
        out.append(f'<text x="{x1:.1f}" y="{H-3}" text-anchor="middle">{E(hi_txt)}</text>')
    vx = X(t["value"])
    out.append(f'<line x1="{vx:.1f}" y1="{Y-11}" x2="{vx:.1f}" y2="{Y+11}" stroke="{INK}" stroke-width="1.5"/>')
    out.append(_marker(vx, Y - 14 if t["status"] != "below" else Y - 14, t["status"]))
    out.append(f'<text x="{vx:.1f}" y="9" text-anchor="middle" style="font-weight:700;fill:{INK}">{labs.fmt_num(t["value"])}</text>')
    out.append("</svg>")
    return "".join(out)


def trend(name, pts, latest):
    """Value across reports with the printed band of the latest report. pts: [{date,value,unit,status}]; latest: that report's test row."""
    low, high = _lo(latest), _hi(latest)
    W, H, ML, MR, MT, MB = 340, 130, 40, 40, 22, 24
    vals = [p["value"] for p in pts]
    d0, d1 = _domain(vals, low, high)
    xs = sorted({p["date"] for p in pts})
    X = lambda dt: ML + (xs.index(dt) / max(len(xs) - 1, 1)) * (W - ML - MR) if len(xs) > 1 else W / 2
    Y = lambda v: H - MB - (v - d0) / (d1 - d0) * (H - MT - MB)
    out = [f'<svg class="trend" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{E(name)} across reports">']
    if low is not None or high is not None:
        top = Y(high) if high is not None else MT
        bot = Y(low) if low is not None else H - MB
        out.append(f'<rect x="{ML}" y="{top:.1f}" width="{W-ML-MR}" height="{max(bot-top, 1):.1f}" fill="{BAND}" stroke="{EDGE}" stroke-dasharray="{"" if low is not None and high is not None else "4 3"}"/>')
    line = " ".join("%.1f,%.1f" % (X(p["date"]), Y(p["value"])) for p in pts)
    out.append(f'<polyline points="{line}" fill="none" stroke="{INK}" stroke-width="1.5"/>')
    for p in pts:
        x, y = X(p["date"]), Y(p["value"])
        out.append(_marker(x, y, p["status"]))
        out.append(f'<text x="{x:.1f}" y="{y-10:.1f}" text-anchor="middle" style="font-weight:700;fill:{INK}">{labs.fmt_num(p["value"])}</text>')
        anchor = "start" if x <= ML + 1 else ("end" if x >= W - MR - 1 else "middle")
        out.append(f'<text x="{x:.1f}" y="{H-8}" text-anchor="{anchor}">{E(p["date"])}</text>')
    out.append("</svg>")
    return "".join(out)


def _sorted(tests):
    return sorted(tests, key=lambda t: ORDER[t["status"]])


def report_html(r):
    """One report: 'N of M outside the lab's printed range', then the tests with out-of-range first."""
    tests = r["tests"]
    n_out = sum(t["status"] in ("above", "below") for t in tests)
    h = [f'<div class="labrep"><h3>{E(r["lab"])} · {E(r["report_date"])}</h3>',
         f'<div class="lsum"><b>{n_out} of {len(tests)} outside the lab\'s printed range</b></div>',
         '<table class="lt"><tr><th>Test</th><th>Result</th><th>Printed range</th><th>Status</th><th></th></tr>']
    for t in _sorted(tests):
        h.append(f'<tr class="{t["status"]}"><td>{E(t["test"])}</td><td>{labs.fmt_num(t["value"])} {E(t["unit"])}</td>'
                 f'<td>{E(t["range_text"] or "—")}</td><td><span class="ico">{ICON[t["status"]]}</span> {WORD[t["status"]]}</td><td>{range_bar(t)}</td></tr>')
    h.append("</table></div>")
    return "".join(h)


def trends_html(reps):
    """A trend per test that appears in two or more reports (live reports, oldest first)."""
    series = {}
    for r in reps:
        for t in r["tests"]:
            series.setdefault(t["test"], []).append((r["report_date"], t))
    out = []
    for name, rows in series.items():
        if len(rows) < 2:
            continue
        pts = [dict(date=d, value=t["value"], unit=t["unit"], status=t["status"]) for d, t in rows]
        latest = rows[-1][1]
        earlier = {t["range_text"] for _, t in rows[:-1]} - {latest["range_text"]}
        cap = f'printed range on the latest report: {E(latest["range_text"] or "none printed")}' + (f' (earlier: {E(", ".join(sorted(x or "none" for x in earlier)))})' if earlier else "")
        out.append(f'<div class="trendbox"><div><b>{E(name)}</b> <span class="mut">({E(latest["unit"])}) · {cap}</span></div>{trend(name, pts, latest)}</div>')
    return "".join(out)


def section_html(reps):
    """Everything for the lab section (newest report first, then trends)."""
    if not reps:
        return '<div class="mut">No lab reports yet.</div>'
    return "".join(report_html(r) for r in reversed(reps)) + trends_html(reps)
