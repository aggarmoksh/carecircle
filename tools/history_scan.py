"""Scan the whole git history for things that must not be published. Prints COUNTS AND PATHS ONLY: never a matched value, a key, a token, a number or an email address.
Patterns that are secrets (the exact values in .env, their first characters) are built at run time from .env and written to a temporary file that is deleted at once.
Usage: python tools/history_scan.py [--repo PATH]"""
import collections, json, os, pathlib, re, subprocess, sys, tempfile
from dotenv import dotenv_values

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = pathlib.Path(sys.argv[sys.argv.index("--repo") + 1]) if "--repo" in sys.argv else ROOT


def git(*a, check=True):
    r = subprocess.run(["git", "-c", "core.quotepath=false", *a], cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout


REVS = git("rev-list", "--all").split()
BATCH = 12


def grep_paths(args):
    """git grep over every commit -> {path: set(commits)} (paths only; matched text is never read into the report)."""
    hits = collections.defaultdict(set)
    for i in range(0, len(REVS), BATCH):
        revs = REVS[i:i + BATCH]
        out = subprocess.run(["git", "-c", "core.quotepath=false", "grep", "-I", "-l", *args, *revs], cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        for line in out.splitlines():
            rev, _, path = line.partition(":")
            hits[path].add(rev[:7])
    return hits


def show(name, hits, extra=""):
    n_files, n_commits = len(hits), len(set().union(*hits.values())) if hits else 0
    print(f"{name}: {n_files} path(s) in {n_commits} commit(s){extra}")
    for p in sorted(hits)[:40]:
        print("    ", p, f"({len(hits[p])} commit(s))")
    if len(hits) > 40:
        print(f"     ... and {len(hits) - 40} more path(s)")
    return hits


def msg_count(patfile=None, regex=None):
    n = 0
    for body in git("log", "--all", "--format=%B%x00").split("\x00"):
        if (patfile and any(p in body for p in patfile)) or (regex and re.search(regex, body)):
            n += 1
    return n


def main():
    print(f"repo: {REPO.name}; commits scanned: {len(REVS)}")
    env = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v}
    exact = {k: v for k, v in env.items() if len(v) >= 6 and k not in ("WA_RECIPIENTS",)}
    # 1. exact .env values (and, for key-like values, the first 12 characters)
    pats = set(exact.values())
    prefixes = {v[:12] for k, v in exact.items() if re.search(r"KEY|TOKEN|SECRET|SID", k) and len(v) >= 16}
    nums = [x.strip() for x in env.get("WA_RECIPIENTS", "").split(",") if x.strip()]
    digits = {re.sub(r"\D", "", n) for n in nums}
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".pat", dir=tempfile.gettempdir()) as f:
        f.write("\n".join(sorted(pats | prefixes | {n for n in nums} | {d for d in digits if len(d) >= 8})) + "\n")
        patfile = f.name
    try:
        print("\n[1] exact .env values, key prefixes and the recipient numbers (as written and digits-only)")
        h = show("  in file contents", grep_paths(["-F", "-f", patfile]))
        vals = [l for l in pathlib.Path(patfile).read_text(encoding="utf-8").splitlines() if l]
        print(f"  in commit messages: {msg_count(patfile=vals)} commit(s)")
        # which .env variable families matched (names only, never values)
        fam = collections.Counter()
        for k, v in exact.items():
            if grep_paths_cached(v):
                fam[k] += 1
        print("  variables whose value appears somewhere in history:", sorted(fam) or "none")
    finally:
        os.unlink(patfile)
    # 2. Twilio and generic key shapes
    print("\n[2] Twilio identifiers and key shapes")
    for name, rx in (("Twilio account/API SID (AC/SK + 32 hex)", r"\b(AC|SK)[0-9a-f]{32}\b"), ("Twilio message SID (SM/MM + 32 hex)", r"\b(SM|MM)[0-9a-f]{32}\b"),
                     ("sk- style key", r"\bsk-[A-Za-z0-9_-]{16,}"), ("AWS key id", r"\bAKIA[0-9A-Z]{16}\b"), ("GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
                     ("Bearer token literal", r"Bearer [A-Za-z0-9._-]{20,}"), ("long hex secret (40+)", r"\b[0-9a-f]{40,}\b")):
        show("  " + name, grep_paths(["-E", "-e", rx]))
    # 3. phone-number patterns
    print("\n[3] phone-number patterns")
    show("  E.164 (+ then 10-15 digits)", grep_paths(["-E", "-e", r"\+[0-9]{10,15}\b"]))
    show("  whatsapp: address with digits", grep_paths(["-E", "-e", r"whatsapp:\+?[0-9]{8,}"]))
    # 4. tunnel hostnames
    print("\n[4] tunnel hostnames")
    show("  *.trycloudflare.com", grep_paths(["-E", "-e", r"[a-z0-9-]+\.trycloudflare\.com"]))
    show("  other ngrok / localtunnel hostnames", grep_paths(["-E", "-e", r"[a-z0-9-]+\.(ngrok(-free)?\.(app|io)|loca\.lt)"]))
    # 5. the word "private"
    print('\n[5] the word "private"')
    names = sorted({p for p in git("log", "--all", "--name-only", "--format=").splitlines() if p})
    pp = [p for p in names if "private" in p.lower()]
    print(f"  paths containing it (all history): {len(pp)}")
    for p in pp:
        print("     ", p)
    show("  file contents mentioning a private folder path", grep_paths(["-i", "-E", "-e", r"private[\\/]"]))
    show('  file contents containing the word "private" (any use)', grep_paths(["-i", "-w", "-e", "private"]))
    # 6. author and committer emails (counts only)
    print("\n[6] commit author and committer emails (addresses are not printed)")
    ae = collections.Counter(git("log", "--all", "--format=%ae").split())
    ce = collections.Counter(git("log", "--all", "--format=%ce").split())
    tr = collections.Counter(re.findall(r"^(?:Co-Authored-By|Signed-off-by):.*<([^>]+)>", git("log", "--all", "--format=%B"), re.M | re.I))

    def kind(e):
        return "noreply" if "noreply" in e else ("free-mail provider" if re.search(r"@(gmail|outlook|hotmail|yahoo|icloud|proton|live)\.", e, re.I) else "other domain")
    print("  distinct author emails:", len(ae), dict(collections.Counter(kind(e) for e in ae)), "; commits by them:", sum(ae.values()))
    print("  distinct committer emails:", len(ce), dict(collections.Counter(kind(e) for e in ce)), "; commits by them:", sum(ce.values()))
    print("  distinct trailer emails (Co-Authored-By etc.):", len(tr), dict(collections.Counter(kind(e) for e in tr)), "; trailers:", sum(tr.values()))
    env_mail = [v for k, v in env.items() if "@" in v]
    # 7. files that should never have been tracked
    print("\n[7] tracked-in-history paths by risk class")
    classes = {"env files": r"(^|/)\.env($|\.)(?!example)", "mcp config": r"\.mcp\.json$", "databases": r"\.(db|sqlite|sqlite3|db-wal|db-shm)$", "images": r"\.(jpe?g|png|heic|webp)$",
               "audio/video": r"\.(ogg|opus|m4a|mp3|wav|mp4|mkv)$", "pdf/docx": r"\.(pdf|docx)$", "outputs/ or data/ or media/": r"^(outputs|data|media|photos|prescriptions|videos|raw)/"}
    for label, rx in classes.items():
        m = [p for p in names if re.search(rx, p)]
        print(f"  {label}: {len(m)} path(s)")
        for p in m[:15]:
            print("     ", p)
    # 8. biggest blobs in history (path + size only)
    print("\n[8] largest blobs in history (> 500 KB)")
    big = []
    out = git("rev-list", "--objects", "--all")
    objs = {}
    for line in out.splitlines():
        sha, _, path = line.partition(" ")
        if path:
            objs[sha] = path
    if objs:
        r = subprocess.run(["git", "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"], cwd=REPO, input="\n".join(objs), capture_output=True, text=True)
        for line in r.stdout.splitlines():
            sha, typ, size = line.split()
            if typ == "blob" and int(size) > 500_000:
                big.append((int(size), objs[sha]))
    for size, p in sorted(big, reverse=True)[:15]:
        print(f"     {size // 1024} KB  {p}")
    if not big:
        print("     none")


_cache = {}


def grep_paths_cached(value):
    if value not in _cache:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".pat") as f:
            f.write(value + "\n")
        try:
            _cache[value] = bool(grep_paths(["-F", "-f", f.name]))
        finally:
            os.unlink(f.name)
    return _cache[value]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
