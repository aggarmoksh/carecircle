"""Image understanding: classify, discharge extraction (Phase 0 P1 prompt and schema), organiser judging (Spark alone) and SAM overlay."""
import io, json, pathlib
from . import llm

ROOT = pathlib.Path(__file__).resolve().parent.parent
TYPES = ["discharge_sheet", "prescription", "pill_organiser", "lab_report", "other"]
DOSE_UNITS = ["mg", "mcg", "g", "mL", "units", "tablet", "puff", "drop"]
FREQS = ["once_daily", "twice_daily", "three_times_daily", "four_times_daily", "every_n_hours", "at_bedtime", "as_needed", "weekly"]
FOOD = ["yes", "no", "unspecified"]
SLOTS14 = [f"{d}_{p}" for d in "MON TUE WED THU FRI SAT SUN".split() for p in ("AM", "PM")]

CLASSIFY_SCHEMA = {"name": "image_type", "schema": {"type": "object", "additionalProperties": False, "required": ["type", "confidence"],
                   "properties": {"type": {"type": "string", "enum": TYPES}, "confidence": {"type": "number"}}}}
CLASSIFY_PROMPT = ("Classify this image sent to a family care app. Choose one type: discharge_sheet (a hospital discharge summary or medicine list), "
                   "prescription, pill_organiser (a weekly pill box with compartments), lab_report (test results), other. "
                   "Give a confidence from 0 to 1. Do not read out or interpret any content.")

EXTRACT_SCHEMA = {"name": "discharge_sheet", "schema": {
    "type": "object", "additionalProperties": False, "required": ["meds"],
    "properties": {"meds": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["name", "dose_amount", "dose_unit", "frequency", "times", "with_food", "notes"],
        "properties": {"name": {"type": "string"}, "dose_amount": {"type": "number"}, "dose_unit": {"type": "string", "enum": DOSE_UNITS},
                       "frequency": {"type": "string", "enum": FREQS}, "times": {"type": "array", "items": {"type": "string"}},
                       "with_food": {"type": "string", "enum": FOOD}, "notes": {"type": "string"}}}}}}}
EXTRACT_PROMPT = (
    "This is a photo of a fictional discharge sheet. Extract every medicine listed on it as structured data. "
    "Rules: name = generic drug name exactly as printed, lowercase. dose_amount = number only. "
    "times = clock times in HH:MM 24h ONLY if the sheet prints clock times; otherwise an empty list. Never invent or infer times. "
    "with_food: yes = with or after food; no = before food or empty stomach; unspecified = the sheet says nothing. "
    "A medicine that is crossed out or marked STOP is not listed. notes = any extra instruction text as printed. "
    "Copy what is printed; give no medical advice and add nothing that is not on the sheet.")

ORG_SCHEMA = {"name": "organiser", "schema": {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {
    "items": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["slot", "state"], "properties": {
        "slot": {"type": "string", "enum": SLOTS14}, "state": {"type": "string", "enum": ["full", "empty"]}}}}}}}
ORG_PROMPT = ("The photo shows a 7-day pill organiser with printed day labels (MON..SUN) and AM/PM labels, 14 compartments in total. "
              "For each of the 14 slots, written DAY_SLOT (e.g. MON_AM), say whether the compartment is 'full' (contains pills) or "
              "'empty' (no pills visible). Judge only whether it is empty; do not count pills.")


def _msg(prompt, path):
    return [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": llm.data_url(path)}}]}]


def prep(src, name):
    return llm.prep_image(src, name)


def classify(path, item):
    r, dt, usd = llm.spark_json("phase1", f"classify-{item}", _msg(CLASSIFY_PROMPT, path), CLASSIFY_SCHEMA)
    return r["type"], float(r["confidence"])


def extract(path, item):
    r, dt, usd = llm.spark_json("phase1", f"extract-{item}", _msg(EXTRACT_PROMPT, path), EXTRACT_SCHEMA)
    return r["meds"]


def organiser_states(path, item):
    r, dt, usd = llm.spark_json("phase1", f"organiser-{item}", _msg(ORG_PROMPT, path), ORG_SCHEMA)
    return {i["slot"]: i["state"] for i in r["items"]}


def sam_overlay(path, item, out_path):
    """Run SAM 3.1 on the organiser photo; store the overlay only when it returns exactly 14 masks. Returns (n_masks, saved_path|None)."""
    import numpy as np
    import meta_sam_parser as m
    from PIL import Image, ImageDraw
    resp, _ = llm.sam("phase1", f"sam-{item}", path)
    resp.raise_for_status()
    txt = resp.json()["output"][0]["content"][0]["text"] if resp.json().get("output") else ""
    p = m.image_segmentation_format().create_parser()
    p.push(txt)
    masks = [x for x in p.finish(m.CompletedOutcome()).result.records if x.kind == "mask"]
    if len(masks) != 14:
        return len(masks), None
    im = Image.open(path).convert("RGBA")
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    rng = np.random.default_rng(1)
    for x in masks:
        b = x.bounds
        ras = np.frombuffer(m.decode_mask_to_raster(x.mask), dtype=np.uint8).reshape(x.mask.height, x.mask.width)
        col = tuple(int(v) for v in rng.integers(60, 255, 3))
        mk = Image.fromarray((ras * 110).astype(np.uint8))
        solid = Image.new("RGBA", mk.size, col + (255,))
        solid.putalpha(mk)
        layer.alpha_composite(solid, (b.left, b.top))
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(im, layer).convert("RGB").save(out_path, "JPEG", quality=85)
    return 14, str(out_path)
