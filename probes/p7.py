"""P7: lab-report extraction probe. One Spark run per report (L1, L2). Scoring per tests/lab_labels.json _rules (3 fields x 18 tests = 54).
Run: .venv/Scripts/python.exe probes/p7.py   (writes outputs/p7_raw.json first, then outputs/p7_result.json)"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import labs, llm

LAB = json.loads((ROOT / "tests" / "lab_labels.json").read_text(encoding="utf-8"))["reports"]
raw_f = ROOT / "outputs" / "p7_raw.json"

raw = {}
for key in ("L1", "L2"):
    src = next((ROOT / "media" / "labs").glob(key + ".*"))
    p, _ = llm.prep_image(src, key)
    raw[key] = labs.extract(p, key)  # already code-finished: parsed range + code status
    raw_f.write_text(json.dumps(raw, indent=1), encoding="utf-8")

rows, tot, ok_fields, wrong_status, invented_ranges, invented_tests, dropped_tests = [], 0, 0, 0, 0, 0, 0
for key, lab in LAB.items():
    got = {t["test"]: t for t in raw[key]["tests"]}
    want = {t["test"]: t for t in lab["tests"]}
    invented_tests += len(set(got) - set(want))
    dropped_tests += len(set(want) - set(got))
    for name, w in want.items():
        g = got.get(name)
        row = dict(report=key, test=name, want=dict(value=w["value"], unit=w["unit"], low=w["range_low"], high=w["range_high"], status=w["expected_status"]))
        if g is None:
            row["got"] = None
            row["fields_ok"] = 0
            tot += 3
            rows.append(row)
            continue
        f_val = abs(g["value"] - w["value"]) < 1e-9
        f_unit = labs.norm_unit(g["unit"]) == labs.norm_unit(w["unit"])
        f_rng = (g["parsed_low"], g["parsed_high"]) == (w["range_low"], w["range_high"])
        st_ok = g["status"] == w["expected_status"]
        if not st_ok:
            wrong_status += 1
        if w["range_text"] == "" and g["range_text"].strip() != "":
            invented_ranges += 1
        if w["range_text"] != "" and w["range_low"] is None and w["range_high"] is None:
            pass
        row["got"] = dict(value=g["value"], unit=g["unit"], range_text=g["range_text"], low=g["parsed_low"], high=g["parsed_high"], flag=g["printed_flag"], status=g["status"])
        row["fields"] = dict(value=f_val, unit=f_unit, range=f_rng)
        row["status_ok"] = st_ok
        row["fields_ok"] = f_val + f_unit + f_rng
        tot += 3
        ok_fields += row["fields_ok"]
        rows.append(row)
res = dict(fields_exact=ok_fields, fields_total=tot, wrong_statuses=wrong_status, invented_ranges=invented_ranges,
           invented_tests=invented_tests, dropped_tests=dropped_tests,
           dates={k: (raw[k]["report_date"], LAB[k]["report_date"]) for k in raw}, labs={k: (raw[k]["lab"], LAB[k]["lab"]) for k in raw},
           pass_=bool(ok_fields >= 53 and tot == 54 and wrong_status == 0 and invented_ranges == 0 and invented_tests == 0 and dropped_tests == 0), rows=rows)
(ROOT / "outputs" / "p7_result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))
for r in rows:
    if r["fields_ok"] < 3 or not r.get("status_ok", False):
        print("MISS", r["report"], r["test"], "want", r["want"], "got", r["got"])
