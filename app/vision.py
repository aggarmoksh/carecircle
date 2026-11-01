"""Image understanding: classify, discharge extraction (Phase 0 P1 prompt and schema), organiser judging (Spark alone) and SAM overlay."""
import io, json, pathlib
from . import llm

ROOT = pathlib.Path(__file__).resolve().parent.parent
from .prompts import *  # noqa: F401,F403  (TYPES, DOSE_UNITS, FREQS, FOOD, SLOTS14, classify and extract prompts/schemas)

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
