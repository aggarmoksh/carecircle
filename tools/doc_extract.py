"""Private extraction tool for real documents the user wants read but never stored in the repo.
Usage:  python tools/doc_extract.py IMAGE_PATH OUTPUT_FOLDER [--lab]
  - opens only IMAGE_PATH (read) and writes only OUTPUT_FOLDER/<image name>.json
  - runs the Phase 0 P1 discharge extraction, or the P7 lab-report extraction with --lab (status computed by code from the printed range)
  - never writes to the repo, the database, the spend file or any log; the image is resized in memory, never saved
  - needs MODEL_API_KEY in the environment (it does not read .env or any other file)
  - prints nothing but the output path"""
import base64, io, json, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import prompts, labcore  # pure modules: constants and range logic, no file reads, no logging


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    lab = "--lab" in argv
    if len(args) != 2:
        sys.exit(2)
    src, out_dir = pathlib.Path(args[0]), pathlib.Path(args[1]).resolve()
    if ROOT in (out_dir, *out_dir.parents):
        sys.exit("output folder must be outside the repo")
    key = os.environ.get("MODEL_API_KEY", "")
    if not key:
        sys.exit("MODEL_API_KEY not set in the environment")
    from PIL import Image, ImageOps
    from openai import OpenAI
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    im.thumbnail((1600, 1600))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)  # in memory; no EXIF is carried over
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    prompt, schema = (prompts.LAB_PROMPT, prompts.LAB_SCHEMA) if lab else (prompts.EXTRACT_PROMPT, prompts.EXTRACT_SCHEMA)
    r = OpenAI(base_url="https://api.meta.ai/v1", api_key=key).chat.completions.create(
        model="muse-spark-1.3", reasoning_effort="low", temperature=0,
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]}],
        response_format={"type": "json_schema", "json_schema": {"name": schema["name"], "strict": True, "schema": schema["schema"]}})
    data = json.loads(r.choices[0].message.content)
    if lab:
        data = labcore.finish(data)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (src.stem + (".lab" if lab else ".meds") + ".json")
    out.write_text(json.dumps(dict(kind="lab_report" if lab else "discharge_sheet", extraction=data,
                                   usage=dict(prompt_tokens=r.usage.prompt_tokens, completion_tokens=r.usage.completion_tokens)), indent=1, ensure_ascii=False), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main(sys.argv[1:])
