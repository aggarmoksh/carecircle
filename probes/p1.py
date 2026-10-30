import sys, json, statistics
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import common as c

L = json.loads((c.ROOT / "labels.json").read_text(encoding="utf-8"))
V = L["_vocab"]
SCHEMA = {"name": "discharge_sheet", "schema": {
    "type": "object", "additionalProperties": False, "required": ["meds"],
    "properties": {"meds": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["name", "dose_amount", "dose_unit", "frequency", "times", "with_food", "notes"],
        "properties": {
            "name": {"type": "string"},
            "dose_amount": {"type": "number"},
            "dose_unit": {"type": "string", "enum": V["dose_unit"]},
            "frequency": {"type": "string", "enum": V["frequency"]},
            "times": {"type": "array", "items": {"type": "string"}},
            "with_food": {"type": "string", "enum": V["with_food_values"]},
            "notes": {"type": "string"}}}}}}}
PROMPT = (
    "This is a photo of a fictional discharge sheet. Extract every medicine listed on it as structured data. "
    "Rules: name = generic drug name exactly as printed, lowercase. dose_amount = number only. "
    "times = clock times in HH:MM 24h ONLY if the sheet prints clock times; otherwise an empty list. Never invent or infer times. "
    "with_food: yes = with or after food; no = before food or empty stomach; unspecified = the sheet says nothing. "
    "A medicine that is crossed out or marked STOP is not listed. notes = any extra instruction text as printed. "
    "Copy what is printed; give no medical advice and add nothing that is not on the sheet.")

def norm(m):
    return dict(name=m["name"].strip().lower(), dose_amount=float(m["dose_amount"]), dose_unit=m["dose_unit"],
                frequency=m["frequency"], times=sorted(m["times"]), with_food=m["with_food"])

FIELDS = ["name", "dose_amount", "dose_unit", "frequency", "times", "with_food"]
tag = sys.argv[1] if len(sys.argv) > 1 else "run1"
out = {"prompt": PROMPT, "reasoning_effort": "low", "temperature": 0, "sheets": {}}
for sh in ("d1", "d2", "d3"):
    src = next((c.ROOT / "media" / "discharge").glob(sh + ".*"))
    p, _ = c.prep_image(src, sh)
    msgs = [{"role": "user", "content": [{"type": "text", "text": PROMPT},
                                          {"type": "image_url", "image_url": {"url": c.data_url(p)}}]}]
    txt, dt, usd, raw = c.spark("P1-screen", sh, msgs, SCHEMA)
    c.save_raw(f"p1_{tag}_{sh}", {"request_prompt": PROMPT, "response": raw})
    ext = json.loads(txt)
    lab = [norm(m) for m in L["sheets"][sh]["meds"]]
    got = [norm(m) for m in ext["meds"]]
    lab_names = {m["name"] for m in lab}; got_names = {m["name"] for m in got}
    gm = {m["name"]: m for m in got}
    exact = 0; diffs = []
    for m in lab:
        g = gm.get(m["name"])
        for f in FIELDS:
            ok = g is not None and (g[f] == m[f])
            exact += ok
            if not ok: diffs.append((m["name"], f, m[f], None if g is None else g[f]))
    invented_times = [g["name"] for g in got if g["times"] and not next((l for l in lab if l["name"] == g["name"]), {"times": ["x"]})["times"]]
    out["sheets"][sh] = dict(scored=len(lab) * 6, exact=exact, diffs=diffs,
                             invented_meds=sorted(got_names - lab_names), dropped_meds=sorted(lab_names - got_names),
                             invented_times=invented_times, seconds=dt, usd=usd,
                             notes=[(m["name"], m["notes"], next((x["notes"] for x in ext["meds"] if x["name"].strip().lower() == m["name"]), None)) for m in L["sheets"][sh]["meds"]])
    print(sh, exact, "/", len(lab) * 6, round(dt, 1), "s", round(usd, 4))
tot = sum(s["scored"] for s in out["sheets"].values()); ex = sum(s["exact"] for s in out["sheets"].values())
out["total"] = dict(scored=tot, exact=ex, pct=100 * ex / tot, spend=sum(s["usd"] for s in out["sheets"].values()),
                    median_s=statistics.median(s["seconds"] for s in out["sheets"].values()))
(c.ROOT / "outputs" / f"p1_{tag}_results.json").write_text(json.dumps(out, indent=1))
print(out["total"])
