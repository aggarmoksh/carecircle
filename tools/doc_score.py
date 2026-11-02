"""Score private extractions against the user's private names labels. Prints COUNTS ONLY; never prints a name, a value or any text from either file.
Usage:
  python tools/doc_score.py --check LABELS_JSON                       structure only: how many documents and entries were parsed (key names are shown only if they are generic words)
  python tools/doc_score.py EXTRACTION_DIR LABELS_JSON [OUT_JSON]     per-document counts; OUT_JSON (outside the repo) gets the same counts
EXTRACTION_DIR holds meta_extraction_<n>.json written by tools/doc_extract.py (document n = label key containing n).
Scoring is by medicine NAME only. Per document: label names found (a clear line whose name, name_as_printed or generic_if_printed matches after
normalisation), unsure-flagged (matched only by a line marked unsure, or an unmatched unsure line: a member would have to retype it), dropped (no line),
confidently wrong (a clear line that matches no label name but is close to one: a misreading), invented (a clear line unrelated to every label name).
Non-medicine lines (steam, gargle, chewing gum, food advice) are ignored on both sides; label entries marked unknown are excluded.
Matching rule (fixed before any run): lowercase, drop form/dose words and digits, keep letters; equal, or one contains the other (4+ letters).
A clear unmatched line is 'confidently wrong' when its difflib ratio to some label name is >= 0.6, otherwise 'invented'."""
import difflib, json, pathlib, re, sys

FORM = r"\b(tab|tabs|tablet|tablets|cap|caps|capsule|capsules|syp|syrup|inj|injection|drops|gel|cream|oint|ointment|sr|er|xr|mg|ml|mcg|iu|forte|plus|dsr|od|bd|tds|qid|hs)\b"
NONMED = re.compile(r"\b(steam\w*|gargl\w*|chewing|gum|diet|food|avoid|inhal\w*|exercise|fluids?)\b", re.I)
NAME_KEYS = re.compile(r"name|brand|generic|medicine|drug|printed|med", re.I)
LIST_KEYS = ("medicines", "meds", "names", "lines", "items", "labels", "entries")
SAFE_KEYS = {"documents", "docs", "images", "files", "medicines", "meds", "names", "lines", "items", "labels", "entries", "name", "brand", "generic", "unknown",
             "kind", "type", "written_by_user", "timestamp", "is_medicine", "note", "notes", "printed", "handwritten", "doc", "id", "file"}


def norm(s):
    s = re.sub(FORM, " ", str(s).lower())
    return re.sub(r"[^a-z]", "", s)


def variants(strings):
    out = set()
    for s in strings:
        for part in re.split(r"[/(),+;]|\band\b", str(s)):
            n = norm(part)
            if len(n) >= 3:
                out.add(n)
    return out


def match(a, b):
    return any(x == y or (min(len(x), len(y)) >= 4 and (x in y or y in x)) for x in a for y in b)


def label_entries(doc):
    """-> list of sets of normalised name variants, one per label medicine (unknown / non-medicine entries excluded)."""
    lst = doc
    if isinstance(doc, dict):
        lst = next((doc[k] for k in LIST_KEYS if k in doc), None)
        if lst is None:
            lst = [v for v in doc.values() if isinstance(v, (list, dict))]
            lst = lst[0] if lst and isinstance(lst[0], list) else list(doc.items()) if all(isinstance(v, (dict, str)) for v in doc.values()) else []
    out = []
    for e in lst or []:
        if isinstance(e, tuple):
            e = e[1] if isinstance(e[1], dict) else {"name": e[0]}
        strs, skip = [], False
        if isinstance(e, str):
            strs = [e]
        elif isinstance(e, dict):
            for k, v in e.items():
                if re.search(r"unknown", str(k), re.I) and v is True:
                    skip = True
                if k.lower() in ("kind", "type") and re.search(r"non.?med|not.?med", str(v), re.I):
                    skip = True
                if k.lower() == "is_medicine" and v is False:
                    skip = True
                if NAME_KEYS.search(k) and isinstance(v, str):
                    strs.append(v)
                elif NAME_KEYS.search(k) and isinstance(v, list):
                    strs += [x for x in v if isinstance(x, str)]
        if skip or any(str(s).strip().lower() in ("unknown", "?", "") for s in strs) or not strs or NONMED.search(" ".join(strs)):
            continue
        v = variants(strs)
        if v:
            out.append(v)
    return out


def load_labels(path):
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    root = next((raw[k] for k in ("documents", "docs", "images", "files") if isinstance(raw.get(k), (dict, list))), raw)
    docs = {}
    if isinstance(root, list):
        for i, d in enumerate(root, 1):
            n = d.get("doc") or d.get("id") or i if isinstance(d, dict) else i
            docs[int(re.search(r"\d+", str(n)).group())] = d
    else:
        for k, v in root.items():
            m = re.search(r"\d+", str(k))
            if m and isinstance(v, (dict, list)):
                docs[int(m.group())] = v
    return raw, docs


def check(path):
    raw, docs = load_labels(path)
    show = lambda ks: [k if k in SAFE_KEYS else "<other>" for k in ks]
    print("top-level keys:", show(raw.keys()) if isinstance(raw, dict) else "list")
    for n in sorted(docs):
        d = docs[n]
        keys = show(d.keys()) if isinstance(d, dict) else "list"
        raw_list = d.get("names") if isinstance(d, dict) else None
        kinds = sorted({type(e).__name__ for e in raw_list}) if isinstance(raw_list, list) else None
        print(f"doc {n}: type={type(d).__name__} keys={keys} raw entries={len(raw_list) if isinstance(raw_list, list) else None} entry types={kinds} medicine entries parsed={len(label_entries(d))}")


def score(ex_dir, labels):
    _, docs = load_labels(labels)
    res = {}
    for n in sorted(docs):
        f = pathlib.Path(ex_dir) / f"meta_extraction_{n}.json"
        if not f.exists():
            res[n] = dict(error="extraction missing")
            continue
        lines = json.loads(f.read_text(encoding="utf-8"))["extraction"]["meds"]
        labs = label_entries(docs[n])
        clear_hit, unsure_hit = set(), set()
        unmatched = []
        ignored = 0
        for l in lines:
            vs = variants([l.get("name", ""), l.get("name_as_printed", ""), l.get("generic_if_printed", "")])
            if NONMED.search(" ".join([l.get("name", ""), l.get("name_as_printed", "")])):
                ignored += 1
                continue
            hit = [i for i, lv in enumerate(labs) if match(vs, lv)]
            if hit:
                (unsure_hit if l["legibility"] == "unsure" else clear_hit).update(hit)
            else:
                unmatched.append((vs, l["legibility"]))
        found = len(clear_hit)
        unsure_flagged = len(unsure_hit - clear_hit)
        dropped = len(labs) - found - unsure_flagged
        unmatched_labs = [lv for i, lv in enumerate(labs) if i not in clear_hit]
        wrong = invented = unsure_extra = 0
        for vs, leg in unmatched:
            if leg == "unsure":
                unsure_extra += 1
            elif any(difflib.SequenceMatcher(None, a, b).ratio() >= 0.6 for a in vs for lv in unmatched_labs for b in lv):
                wrong += 1
            else:
                invented += 1
        res[n] = dict(label_medicines=len(labs), extracted_lines=len(lines), found=found, unsure_flagged=unsure_flagged, dropped=dropped,
                      confidently_wrong=wrong, invented=invented, unsure_unmatched_lines=unsure_extra, non_medicine_ignored=ignored)
    return res


def main(argv):
    if argv and argv[0] == "--check" and len(argv) == 2:
        return check(argv[1])
    if len(argv) not in (2, 3):
        sys.exit("usage: doc_score.py --check LABELS | EXTRACTION_DIR LABELS [OUT_JSON]")
    res = score(argv[0], argv[1])
    for n, r in res.items():
        print(f"doc {n}:", ", ".join(f"{k}={v}" for k, v in r.items()))
    printed = sum(res.get(n, {}).get("confidently_wrong", 0) for n in (1, 3))
    hand = sum(res.get(n, {}).get("confidently_wrong", 0) for n in (2, 4))
    print(f"target: printed docs (1, 3) confidently wrong = {printed} (need 0); handwritten docs (2, 4) confidently wrong = {hand} (need <= 1)")
    if len(argv) == 3:
        out = pathlib.Path(argv[2]).resolve()
        repo = pathlib.Path(__file__).resolve().parent.parent
        if repo in (out, *out.parents):
            sys.exit("OUT_JSON must be outside the repo")
        out.write_text(json.dumps(dict(per_document=res, printed_confidently_wrong=printed, handwritten_confidently_wrong=hand), indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
