"""Rebuild p2_run1_results.json from saved raw responses + spend log (the original run crashed while writing results; no API calls here)."""
import sys, json, statistics
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import common as c
L = json.loads((c.ROOT / "labels.json").read_text(encoding="utf-8"))
ev = json.load(open(c.ROOT / "outputs" / "spend.json"))
res = {"asr_model": "muse-voice-transcribe-1.0", "native_accepted": False,
       "native_error": "400: audio part must be mono 16-bit PCM WAV at 16 or 24 kHz", "converted": "ffmpeg -ac 1 -ar 16000 -c:a pcm_s16le",
       "language_param": "none set (auto-detected; API documents no language parameter)", "spark_reasoning_effort": "low", "temperature": 0, "notes": {}}
for k, lab in L["voice"].items():
    a = json.load(open(c.ROOT / "outputs/raw" / f"p2_run1_{k}_asr.json"))
    p = json.load(open(c.ROOT / "outputs/raw" / f"p2_run1_{k}_parse.json"))
    got = json.loads(p["choices"][0]["message"]["content"])
    exp = {f: lab[f] for f in ("actor", "slot", "action")}
    asr = next(e for e in ev if e["probe"] == "P2" and e["item"] == k and e["kind"] == "asr")
    sp = next(e for e in ev if e["probe"] == "P2" and e["item"] == k and e["kind"] == "spark")
    res["notes"][k] = dict(language=lab["language"], script=lab["script"], transcript=a["transcript"], expected=exp, got=got, correct=got == exp,
                           seconds=asr["seconds"] + sp["seconds"], asr_s=asr["seconds"], parse_s=sp["seconds"], audio_s=asr["audio_seconds"], usd=asr["usd"] + sp["usd"])
n = res["notes"]
res["correct"] = sum(v["correct"] for v in n.values()); res["hi_pa_mixed"] = sum(v["correct"] for v in n.values() if v["language"] != "en")
res["median_s"] = statistics.median(v["seconds"] for v in n.values()); res["usd"] = sum(v["usd"] for v in n.values())
(c.ROOT / "outputs" / "p2_run1_results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
print(res["correct"], "/12; non-en", res["hi_pa_mixed"], "/4; median", round(res["median_s"], 1), "usd", round(res["usd"], 4))
for k, v in n.items(): print(k, v["language"], v["correct"], round(v["seconds"], 1), "|", v["script"][:50].encode("ascii", "replace").decode(), "=>", v["transcript"][:60].encode("ascii", "replace").decode())
