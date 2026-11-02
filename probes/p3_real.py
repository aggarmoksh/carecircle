import sys, json, statistics, io, base64, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import common as c
import numpy as np
import meta_sam_parser as m
from PIL import Image, ImageDraw

LAB2 = json.loads((c.ROOT / "tests" / "organiser_real_labels_v2.json").read_text(encoding="utf-8"))["photos"]
DAYS = "MON TUE WED THU FRI SAT SUN".split()
SLOTS = [f"{d}_{s}" for d in DAYS for s in ("AM", "PM")]
tag = sys.argv[1] if len(sys.argv) > 1 else "run1"


def obj(props, req=None):
    return {"type": "object", "additionalProperties": False, "required": req or list(props), "properties": props}


def arr_schema(name, item_props):
    return {"name": name, "schema": obj({"items": {"type": "array", "items": obj(item_props)}})}


STATE = {"type": "string", "enum": ["full", "empty"]}
MAP_SCHEMA = arr_schema("slot_map", {"id": {"type": "integer"}, "slot": {"type": "string", "enum": SLOTS + ["NONE"]}})
JUDGE_SCHEMA = arr_schema("judge", {"id": {"type": "integer"}, "state": STATE})
ALONE_SCHEMA = arr_schema("organiser", {"slot": {"type": "string", "enum": SLOTS}, "state": STATE})

P_MAP = ("The photo shows a 7-day pill organiser with printed day labels (MON..SUN) and AM/PM labels. "
         "Below is a list of detected compartments, each as a box [x_min, y_min, x_max, y_max] on a 0-1000 grid "
         "((0,0) top-left, (1000,1000) bottom-right): {boxes}. Read the day and AM/PM labels in the photo and map each "
         "compartment id to its slot, written DAY_SLOT, e.g. MON_AM. Use NONE for anything that is not one of the 14 "
         "compartments. Each slot may be used at most once.")
P_JUDGE = ("Each image is a crop of one compartment of a pill organiser, preceded by its id. For each id say whether the "
           "compartment is 'full' (contains pills) or 'empty' (no pills visible). Judge only whether it is empty; do not count pills.")
sys.path.insert(0, str(c.ROOT))
from app.vision import ORG_PROMPT as P_ALONE  # the product prompt, unchanged


def u(url):
    return {"type": "image_url", "image_url": {"url": url}}


def jpg_url(im):
    b = io.BytesIO()
    im.save(b, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def monotone(groups):
    ms = [np.mean(v) for _, v in sorted(groups.items())]
    return all(a < b for a, b in zip(ms, ms[1:])) or all(a > b for a, b in zip(ms, ms[1:]))


res = {"prompts": dict(map=P_MAP, judge=P_JUDGE, alone=P_ALONE), "reasoning_effort": "low", "temperature": 0, "photos": {}}
for o in sorted(LAB2):
    lab = {k: v for k, v in LAB2[o].items() if not k.startswith("_")}
    path, (W, H) = c.prep_image(c.ROOT / "media" / "organiser_real" / f"{o}.jpeg", o)
    im = Image.open(path)
    r = {}
    # ---- pipeline: SAM -> Spark slot mapping -> Spark crop judging
    resp, sdt = c.sam("P3-real", o, path)
    c.save_raw(f"p3_{tag}_{o}_sam", {"status": resp.status_code, "body": resp.json()})
    txt = resp.json()["output"][0]["content"][0]["text"]
    p = m.image_segmentation_format().create_parser()
    p.push(txt)
    masks = [x for x in p.finish(m.CompletedOutcome()).result.records if x.kind == "mask"]
    boxes = [dict(id=i, l=x.bounds.left, t=x.bounds.top, r=x.bounds.right, b=x.bounds.bottom, mask=x.mask) for i, x in enumerate(masks)]
    r["sam_masks"] = len(boxes)

    ov = im.convert("RGBA")
    layer = Image.new("RGBA", ov.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rng = np.random.default_rng(1)
    for bx in boxes:
        ras = np.frombuffer(m.decode_mask_to_raster(bx["mask"]), dtype=np.uint8).reshape(bx["mask"].height, bx["mask"].width)
        col = tuple(int(v) for v in rng.integers(60, 255, 3))
        mk = Image.fromarray((ras * 110).astype(np.uint8))
        solid = Image.new("RGBA", mk.size, col + (255,))
        solid.putalpha(mk)
        layer.alpha_composite(solid, (bx["l"], bx["t"]))
        d.rectangle([bx["l"], bx["t"], bx["r"] - 1, bx["b"] - 1], outline=col + (255,), width=2)
        d.text((bx["l"] + 4, bx["t"] + 2), str(bx["id"]), fill=(255, 255, 255, 255))
    ov = Image.alpha_composite(ov, layer)

    def g(b):
        return [round(b["l"] / W * 1000), round(b["t"] / H * 1000), round(b["r"] / W * 1000), round(b["b"] / H * 1000)]

    bl = "; ".join(f"id {b['id']}: {g(b)}" for b in boxes)
    txt1, dt1, usd1, raw1 = c.spark("P3-real", o + "-map", [{"role": "user", "content": [
        {"type": "text", "text": P_MAP.format(boxes=bl)}, u(c.data_url(path))]}], MAP_SCHEMA)
    c.save_raw(f"p3_{tag}_{o}_map", raw1)
    mp = {i["id"]: i["slot"] for i in json.loads(txt1)["items"]}

    content = [{"type": "text", "text": P_JUDGE}]
    for b in boxes:
        crop = im.crop((max(0, b["l"] - 6), max(0, b["t"] - 6), min(W, b["r"] + 6), min(H, b["b"] + 6)))
        content += [{"type": "text", "text": f"id {b['id']}:"}, u(jpg_url(crop))]
    txt2, dt2, usd2, raw2 = c.spark("P3-real", o + "-judge", [{"role": "user", "content": content}], JUDGE_SCHEMA)
    c.save_raw(f"p3_{tag}_{o}_judge", raw2)
    js = {i["id"]: i["state"] for i in json.loads(txt2)["items"]}

    pipe = {}
    for b in boxes:
        s = mp.get(b["id"], "NONE")
        if s != "NONE" and s not in pipe:
            pipe[s] = js.get(b["id"])
    dd = ImageDraw.Draw(ov)
    for b in boxes:
        dd.text((b["l"] + 4, b["t"] + 14), mp.get(b["id"], "?"), fill=(255, 255, 0, 255))
    ov.convert("RGB").save(c.ROOT / "outputs" / "overlays" / f"{o}_{tag}_pipeline.jpg")

    cen = {mp[b["id"]]: ((b["l"] + b["r"]) / 2, (b["t"] + b["b"]) / 2) for b in boxes if mp.get(b["id"], "NONE") != "NONE"}
    distinct14 = set(cen) == set(SLOTS) and len([1 for b in boxes if mp.get(b["id"], "NONE") != "NONE"]) == 14
    mono = False
    if distinct14:
        for ax in (0, 1):
            grp = {}
            for s, cc in cen.items():
                grp.setdefault(DAYS.index(s.split("_")[0]), []).append(cc[ax])
            mono |= monotone(grp)
    r["pipeline"] = dict(correct=sum(pipe.get(s) == lab[s] for s in SLOTS), mapped_distinct_14=distinct14, grid_monotone=mono,
                         mapping=mp, wrong=[(s, lab[s], pipe.get(s)) for s in SLOTS if pipe.get(s) != lab[s]],
                         seconds=sdt + dt1 + dt2, usd=usd1 + usd2 + c.PRICE_SAM)

    # ---- Spark alone
    txt3, dt3, usd3, raw3 = c.spark("P3-real", o + "-alone", [{"role": "user", "content": [
        {"type": "text", "text": P_ALONE}, u(c.data_url(path))]}], ALONE_SCHEMA)
    c.save_raw(f"p3_{tag}_{o}_alone", raw3)
    al = {i["slot"]: i["state"] for i in json.loads(txt3)["items"]}
    r["alone"] = dict(correct=sum(al.get(s) == lab[s] for s in SLOTS), wrong=[(s, lab[s], al.get(s)) for s in SLOTS if al.get(s) != lab[s]],
                      seconds=dt3, usd=usd3)
    res["photos"][o] = r
    print(o, "masks", r["sam_masks"], "pipe", r["pipeline"]["correct"], "map14", distinct14, "mono", mono,
          "alone", r["alone"]["correct"], round(r["pipeline"]["seconds"], 1), "s", flush=True)

(c.ROOT / "outputs" / f"p3_{tag}_results.json").write_text(json.dumps(res, indent=1, default=str))
print("median pipeline s", statistics.median(p["pipeline"]["seconds"] for p in res["photos"].values()))

ph = res["photos"]
n = len(ph)
alone_ok = sum(p["alone"]["correct"] >= 13 for p in ph.values())
sam_ok = sum(p["pipeline"]["mapped_distinct_14"] for p in ph.values())
helps = {k: p["pipeline"]["correct"] - p["alone"]["correct"] for k, p in ph.items() if p["pipeline"]["correct"] - p["alone"]["correct"] >= 2}
res["decision"] = dict(photos=n, spark_alone_ge13=alone_ok, spark_stays_judge=alone_ok >= 7, sam_all14_mapped=sam_ok, sam_overlay_stays=sam_ok >= 7, sam_helps=helps)
(c.ROOT / "outputs" / f"p3_{tag}_results.json").write_text(json.dumps(res, indent=1, default=str))
print(res["decision"])
