"""Voice notes: convert to 16 kHz mono WAV with ffmpeg (the API rejects native WhatsApp ogg), then transcribe."""
import json, pathlib, subprocess, time, wave
import httpx
from . import llm

ROOT = pathlib.Path(__file__).resolve().parent.parent


def transcribe(src, item):
    src = pathlib.Path(src)
    tmp = ROOT / "data" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    wav = tmp / f"{item}.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-map_metadata", "-1", str(wav)], check=True)
    with wave.open(str(wav)) as w:
        secs = w.getnframes() / w.getframerate()
    llm.guard("muse-voice-transcribe-1.0", 0.01)
    t0 = time.time()
    r = httpx.post(llm.BASE + "/asr/transcribe", headers={"Authorization": "Bearer " + llm.key()}, timeout=120,
                   files={"request": (None, json.dumps({"model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}), "application/json"),
                          "audio": (wav.name, wav.read_bytes(), "audio/wav")})
    llm.log_spend("phase1", f"asr-{item}", secs / 3600 * 0.18, kind="asr", seconds=time.time() - t0, audio_seconds=secs, http=r.status_code)
    r.raise_for_status()
    wav.unlink(missing_ok=True)
    return r.json()["transcript"]
