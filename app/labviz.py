"""Lab graphics as server-built SVG, shared by the board and the doctor summary (docs/DESIGN.md, "Lab values").
One row per test: name, value with unit, a 220 px range bar (the printed range as a soft band, the value as a dot), an optional 120 px trend.
Within the printed range = solid teal dot; outside = hollow amber dot with a triangle (up = above, down = below). One-sided ranges fade to the open side.
No range printed = the words, no bar. Status is always in words and a shape, never colour alone. Nothing here judges or explains a value."""
import html, itertools
from . import labs

E = html.escape
ICON = {"above": "▲", "below": "▼", "within": "●", "no_range": "–"}
WORD = {"above": "above the lab's printed range", "below": "below the lab's printed range", "within": "within the lab's printed range", "no_range": "no range printed"}
ORDER = {"above": 0, "below": 0, "no_range": 1, "within": 2}
_ids = itertools.count(1)

CSS = (
    ":root{--within:#1F8A70;--outside:#B26B00;--outsideb:#FFF4E0;--band:#E3DDD3;--bandedge:#C9C1B4;--lineink:#1C2733;--muted:#5B6672;--rule:#E7E1D8}"
    ".labrep{margin:0 0 8px}.lhead{font-size:15px;font-weight:600;margin:0 0 8px}.lorigin{font-size:13px;color:var(--muted);margin:-4px 0 8px}"
    ".lrow{display:grid;grid-template-columns:150px 130px 232px 130px 1fr;align-items:center;gap:8px;padding:6px 0;border-top:1px solid var(--rule);font-size:15px}"
    ".lrow .ln{font-weight:500}.lrow .lv{font-variant-numeric:tabular-nums}.lrow .u{color:var(--muted);font-size:13px}.lrow .lw{font-size:13px;color:var(--muted)}"
    ".lrow.above .lw,.lrow.below .lw{color:var(--outside);font-weight:600}.lrow.within .lw{color:var(--within)}.ico{display:inline-block;width:1.2em;text-align:center}"
    ".lwithin summary{cursor:pointer;font-size:14px;color:var(--muted);padding:8px 0;border-top:1px solid var(--rule)}.lwithin summary:focus-visible,.lswitch button:focus-visible{outline:2px solid #E8833A;outline-offset:2px}"
    ".lswitch{display:flex;gap:6px;margin:0 0 10px;flex-wrap:wrap}.lswitch button{font:inherit;font-size:13px;border:1px solid var(--rule);background:#fff;border-radius:999px;padding:3px 12px;cursor:pointer}"
    ".lswitch button[aria-pressed=true]{border-color:#2563EB;color:#2563EB;font-weight:600}"
    ".rbar text,.spark text{font-size:11px;fill:var(--muted);font-variant-numeric:tabular-nums}.rb-band{fill:var(--band);stroke:var(--bandedge);stroke-width:1}"
    ".rb-stop{stop-color:var(--band)}.rb-in{fill:var(--within)}.rb-out{fill:#fff;stroke:var(--outside);stroke-width:2}.rb-tri{fill:var(--outside)}.sp-line{fill:none;stroke:var(--lineink);stroke-width:1.5}"
    ".lrow.stacked{grid-template-columns:1fr}.lcompact .lrow{padding:3px 0;font-size:13px}"
    "@media(max-width:700px){.lrow{grid-template-columns:1fr 1fr}.lrow .lb,.lrow .lw{grid-column:1/-1}.lrow .ls{grid-column:1/-1}}")


def _lo(t):
    return t.get("parsed_low", t.get("range_low"))


def _hi(t):
    return t.get("parsed_high", t.get("range_high"))


def _dot(x, y, status, r=6):
    if status == "within":
        return f'<circle class="rb-in" cx="{x:.1f}" cy="{y:.1f}" r="{r}"/>'
    if status in ("above", "below"):
        s = 3.6 if r >= 6 else 2.6
        tri = (f"M{x:.1f},{y - s:.1f} L{x - s:.1f},{y + s * .7:.1f} L{x + s:.1f},{y + s * .7:.1f} Z" if status == "above"
               else f"M{x:.1f},{y + s:.1f} L{x - s:.1f},{y - s * .7:.1f} L{x + s:.1f},{y - s * .7:.1f} Z")
        return f'<circle class="rb-out" cx="{x:.1f}" cy="{y:.1f}" r="{r + 1}"/><path class="rb-tri" d="{tri}"/>'
    return ""


def _scale(vals, low, high):
    """From the smaller of the low end and the values to the larger of the high end and the values, plus 10 % padding on each side."""
    pts = [v for v in list(vals) + [low, high] if v is not None]
    a, b = min(pts), max(pts)
    span = (b - a) or abs(b) or 1.0
    return a - span * 0.1, b + span * 0.1


def range_bar(t, w=220):
    """SVG bar for one test, or '' when the lab printed no range."""
    low, high = _lo(t), _hi(t)
    if low is None and high is None:
        return ""
    H, Y, M = 34, 13, 8
    d0, d1 = _scale([t["value"]], low, high)
    X = lambda v: M + (v - d0) / (d1 - d0) * (w - 2 * M)
    x0, x1 = (X(low) if low is not None else M), (X(high) if high is not None else w - M)
    nums = labs_nums(t)
    gid = f"g{next(_ids)}"
    fill = "class=\"rb-band\""
    defs = ""
    if low is None or high is None:               # one-sided: the band fades to the open side
        a, b = (("1", "0") if high is None else ("0", "1"))
        defs = f'<defs><linearGradient id="{gid}" x1="{"0" if high is None else "1"}" x2="{"1" if high is None else "0"}"><stop class="rb-stop" offset="0"/><stop class="rb-stop" offset="1" stop-opacity="0"/></linearGradient></defs>'
        fill = f'fill="url(#{gid})" stroke="none"'
    out = [f'<svg class="rbar" width="{w}" height="{H}" viewBox="0 0 {w} {H}" role="img" aria-label="{E(t["test"])}: {labs.fmt_num(t["value"])} {E(t["unit"])}, {WORD[t["status"]]}">', defs,
           f'<rect {fill} x="{x0:.1f}" y="{Y - 5}" width="{max(x1 - x0, 1):.1f}" height="10" rx="5"/>']
    if low is not None:
        out.append(f'<text x="{x0:.1f}" y="{H - 2}" text-anchor="middle">{E(nums[0] if nums else labs.fmt_num(low))}</text>')
    if high is not None:
        out.append(f'<text x="{x1:.1f}" y="{H - 2}" text-anchor="middle">{E(nums[-1] if nums else labs.fmt_num(high))}</text>')
    out.append(_dot(X(t["value"]), Y, t["status"]))
    out.append("</svg>")
    return "".join(out)


def labs_nums(t):
    import re
    return re.findall(labs.NUM, t.get("range_text") or "")


def spark(pts, latest, w=120, h=34):
    """Value across reports (oldest first) with the printed band of the latest report behind it. pts: [{date,value,status}]."""
    low, high = _lo(latest), _hi(latest)
    d0, d1 = _scale([p["value"] for p in pts], low, high)
    Y = lambda v: h - 5 - (v - d0) / (d1 - d0) * (h - 10)
    X = lambda i: 6 + i * (w - 12) / max(len(pts) - 1, 1)
    out = [f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="trend across {len(pts)} reports: ' + ", ".join(labs.fmt_num(p["value"]) for p in pts) + '">']
    if low is not None or high is not None:
        top = Y(high) if high is not None else 0
        bot = Y(low) if low is not None else h
        out.append(f'<rect class="rb-band" x="0" y="{top:.1f}" width="{w}" height="{max(bot - top, 1):.1f}" opacity=".7"/>')
    out.append('<polyline class="sp-line" points="' + " ".join("%.1f,%.1f" % (X(i), Y(p["value"])) for i, p in enumerate(pts)) + '"/>')
    for i, p in enumerate(pts):
        out.append(_dot(X(i), Y(p["value"]), p["status"], r=3))
    out.append("</svg>")
    return "".join(out)


def _series(reps):
    """test -> [(date, row)] oldest first, for tests that appear in two or more reports."""
    s = {}
    for r in reps:
        for t in r["tests"]:
            s.setdefault(t["test"], []).append((r["report_date"], t))
    return {k: v for k, v in s.items() if len(v) > 1}


def _row(t, series):
    rows = series.get(t["test"])
    sp = spark([dict(date=d, value=x["value"], status=x["status"]) for d, x in rows], rows[-1][1]) if rows and rows[-1][1]["status"] != "no_range" else ""
    bar = range_bar(t) or '<span class="mut">no range printed</span>'
    word = WORD[t["status"]] + (f" {E(t['range_text'])}" if t["status"] != "no_range" and t.get("range_text") else "")
    wcell = "" if t["status"] == "no_range" else '<span class="ico">' + ICON[t["status"]] + "</span> " + word
    return (f'<div class="lrow {t["status"]}"><div class="ln">{E(t["test"])}</div><div class="lv"><b>{labs.fmt_num(t["value"])}</b> <span class="u">{E(t["unit"])}</span></div>'
            f'<div class="lb">{bar}</div><div class="ls">{sp}</div><div class="lw">{wcell}</div></div>')


def report_html(r, series=None, collapse=True, idx=0, hidden=False):
    """One report: '29 Oct · Lab · N of M outside the lab's printed range', outside tests first, within-range tests collapsed."""
    series = series or {}
    tests = sorted(r["tests"], key=lambda t: ORDER[t["status"]])
    n_out = sum(t["status"] in ("above", "below") for t in tests)
    inside = [t for t in tests if t["status"] == "within"]
    top = [t for t in tests if t["status"] != "within"]
    h = [f'<div class="labrep" data-rep="{idx}"{" hidden" if hidden else ""}><div class="lhead">{E(labs.pretty_date(r["report_date"]))} · {E(r["lab"])} · {n_out} of {len(tests)} outside the lab\'s printed range</div>']
    if r.get("origin"):
        h.append(f'<div class="lorigin">{E(r["origin"])}</div>')
    h += [_row(t, series) for t in top]
    if inside and collapse:
        h.append(f'<details class="lwithin"><summary>{len(inside)} within the lab\'s printed range</summary>' + "".join(_row(t, series) for t in inside) + "</details>")
    else:
        h += [_row(t, series) for t in inside]
    h.append("</div>")
    return "".join(h)


def section_html(reps, print_mode=False):
    """Everything for the lab section. Board: newest report first with a switcher between reports. Print: the newest report in full, trends from the earlier ones."""
    if not reps:
        return '<div class="mut">No lab reports yet.</div>'
    newest_first = list(reversed(reps))
    series = _series(reps)
    if print_mode:
        return '<div class="lcompact">' + report_html(newest_first[0], {}, collapse=False) + "</div>"
    sw = ""
    if len(newest_first) > 1:
        sw = '<div class="lswitch" role="group" aria-label="Lab reports">' + "".join(
            f'<button type="button" data-rep="{i}" aria-pressed="{"true" if i == 0 else "false"}">{E(labs.pretty_date(r["report_date"]))}</button>' for i, r in enumerate(newest_first)) + "</div>"
    return sw + "".join(report_html(r, series, idx=i, hidden=i > 0) for i, r in enumerate(newest_first))
