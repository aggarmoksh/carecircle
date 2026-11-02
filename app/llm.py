import os, json, time, base64, re, pathlib
from dotenv import load_dotenv
from PIL import Image, ImageOps
from openai import OpenAI

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
BASE = "https://api.meta.ai/v1"
CAP = 7.00
PRICE_IN, PRICE_OUT, PRICE_SAM = 1.25 / 1e6, 4.25 / 1e6, 2.50 / 1000
SPEND = ROOT / "outputs" / "spend.json"
FORBIDDEN = "contributor"

def key():
    k = os.environ.get("MODEL_API_KEY", "")
    if not k:
        raise SystemExit("MODEL_API_KEY missing")
    return k

def client():
    return OpenAI(base_url=BASE, api_key=key())

def spent():
    return sum(e["usd"] for e in json.loads(SPEND.read_text())) if SPEND.exists() else 0.0

def log_spend(probe, item, usd, **kw):
    ev = json.loads(SPEND.read_text()) if SPEND.exists() else []
    ev.append(dict(probe=probe, item=item, usd=usd, **kw))
    SPEND.write_text(json.dumps(ev, indent=1))

def guard(model, est_usd=0.05):
    assert FORBIDDEN not in model
    if spent() + est_usd > CAP:
        raise SystemExit("budget cap would be exceeded")

def prep_image(src, name):
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    im.thumbnail((1600, 1600))
    out = ROOT / "outputs" / "prepped" / f"{name}.jpg"
    im.save(out, "JPEG", quality=90)  # no exif passed => stripped
    return out, im.size

def data_url(path):
    return "data:image/jpeg;base64," + base64.b64encode(pathlib.Path(path).read_bytes()).decode()

def redact(o):
    s = json.dumps(o)
    s = re.sub(r'"Authorization":\s*"[^"]*"', '"Authorization": "REDACTED"', s)
    k = os.environ.get("MODEL_API_KEY", "")
    if k:
        s = s.replace(k, "REDACTED")
    return json.loads(s)

def save_raw(name, obj):
    (ROOT / "outputs" / "raw" / f"{name}.json").write_text(json.dumps(redact(obj), indent=1, default=str))

def spark_json(probe, item, messages, schema, effort="low"):
    import json as _j
    txt, dt, usd, raw = spark(probe, item, messages, schema, effort)
    return _j.loads(txt), dt, usd


def spark(probe, item, messages, schema=None, effort="low", temperature=0):
    guard("muse-spark-1.3")
    c = client()
    kw = dict(model="muse-spark-1.3", messages=messages, reasoning_effort=effort)
    if temperature is not None:
        kw["temperature"] = temperature
    if schema:
        kw["response_format"] = {"type": "json_schema", "json_schema": {"name": schema["name"], "strict": True, "schema": schema["schema"]}}
    t = time.time()
    r = c.chat.completions.create(**kw)
    dt = time.time() - t
    u = r.usage
    usd = u.prompt_tokens * PRICE_IN + u.completion_tokens * PRICE_OUT
    log_spend(probe, item, usd, kind="spark", seconds=dt, pt=u.prompt_tokens, ct=u.completion_tokens)
    return r.choices[0].message.content, dt, usd, r.model_dump()

def sam(probe, item, img_path, prompt="pill organizer compartment", encoding="one_bit"):
    guard("sam-3.1", 0.01)
    import httpx
    body = {"model": "sam-3.1", "stream": False,
            "metadata": {"mask_encoding": encoding, "include_confidence": "true"},
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": data_url(img_path)}]}]}
    t = time.time()
    r = httpx.post(f"{BASE}/responses", json=body, headers={"Authorization": f"Bearer {key()}"}, timeout=120)
    dt = time.time() - t
    log_spend(probe, item, PRICE_SAM, kind="sam", seconds=dt, http=r.status_code)
    return r, dt
