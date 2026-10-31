import sys, json, time, subprocess, wave, statistics, httpx
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import common as c

L = json.loads((c.ROOT / "labels.json").read_text(encoding="utf-8"))
V = L["_vocab"]
tag = sys.argv[1] if len(sys.argv) > 1 else "run1"
d1 = L["sheets"][L["sample_schedule_from"]]["meds"]
SLOTS = [f"{m['name']}_{t}" for m in d1 for t in m["times"]]
MEMBERS = {k: f"{v['name']} ({v['relationship']})" for k, v in L["members"].items()}
SCHEMA = {"name": "confirmation", "schema": {"type": "object", "additionalProperties": False,
          "required": ["actor", "slot", "action"], "properties": {
              "actor": {"type": "string", "enum": V["actor_values"]},
              "slot": {"type": "string", "enum": SLOTS},
              "action": {"type": "string", "enum": V["action"]}}}}
PROMPT = (
    "You log dose confirmations for a family care circle. Coordination only: give no medical advice. "
    "Circle members: {members}; 'patient' is the person being cared for, called Nanaji. "
    "Medication schedule slots (medicine_time): {slots}. "
    "The note below was transcribed from a voice message (it may be English, Hindi, Punjabi or a mix). "
    "The sender of the note is {sender}. Return who gave the dose (actor), which slot it is about, and the action. "
    "actor = m1..m5 for the circle member who gave the dose, or 'patient' if he took it himself. For skipped or unsure, "
    "actor is the member the note names, otherwise the sender. action = given, skipped, or unsure. "
    "Note: \"{transcript}\"")

res = {"asr_model": "muse-voice-transcribe-1.0", "native_accepted": False, "native_error": "400: audio part must be mono 16-bit PCM WAV at 16 or 24 kHz",
       "converted": "ffmpeg -ac 1 -ar 16000 -c:a pcm_s16le", "language_param": "none set (auto-detected; the API documents no language parameter)",
       "spark_reasoning_effort": "low", "temperature": 0, "notes": {}}
(c.ROOT / "outputs" / "wav").mkdir(exist_ok=True)
for k, lab in L["voice"].items():
    src = next((c.ROOT / "media" / "voice").glob(k + ".*"))
    wav = c.ROOT / "outputs" / "wav" / f"{k}.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-map_metadata", "-1", str(wav)], check=True)
    with wave.open(str(wav)) as w:
        secs = w.getnframes() / w.getframerate()
    c.guard("muse-voice-transcribe-1.0", 0.01)
    t0 = time.time()
    r = httpx.post(c.BASE + "/asr/transcribe", headers={"Authorization": "Bearer " + c.key()}, timeout=120,
                   files={"request": (None, json.dumps({"model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}), "application/json"),
                          "audio": (wav.name, wav.read_bytes(), "audio/wav")})
    tdt = time.time() - t0
    usd_asr = secs / 3600 * 0.18
    c.log_spend("P2", k, usd_asr, kind="asr", seconds=tdt, audio_seconds=secs, http=r.status_code)
    r.raise_for_status()
    j = r.json()
    c.save_raw(f"p2_{tag}_{k}_asr", j)
    transcript = j["transcript"]
    msgs = [{"role": "user", "content": PROMPT.format(members="; ".join(f"{a} = {b}" for a, b in MEMBERS.items()),
                                                      slots=", ".join(SLOTS), sender=lab["sender"], transcript=transcript)}]
    txt, pdt, usd_p, raw = c.spark("P2", k, msgs, SCHEMA)
    c.save_raw(f"p2_{tag}_{k}_parse", raw)
    got = json.loads(txt)
    exp = {f: lab[f] for f in ("actor", "slot", "action")}
    res["notes"][k] = dict(language=lab["language"], script=lab["script"], transcript=transcript, expected=exp, got=got,
                           correct=got == exp, seconds=tdt + pdt, asr_s=tdt, parse_s=pdt, audio_s=secs, usd=usd_asr + usd_p)
    print(k, lab["language"], "OK" if got == exp else f"MISS exp={exp} got={got}", round(tdt + pdt, 1), "s", flush=True)

n = res["notes"]
res["correct"] = sum(v["correct"] for v in n.values())
res["hi_pa_mixed"] = sum(v["correct"] for v in n.values() if v["language"] != "en")
res["median_s"] = statistics.median(v["seconds"] for v in n.values())
res["usd"] = sum(v["usd"] for v in n.values())
(c.ROOT / "outputs" / f"p2_{tag}_results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
print(res["correct"], "/12; non-en", res["hi_pa_mixed"], "/", sum(v["language"] != "en" for v in n.values()), "median s", round(res["median_s"], 1))
