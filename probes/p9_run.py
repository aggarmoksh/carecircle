"""P9: one run over tests/p9_labels.json (names only go to the search). Writes outputs/p9_results.json and outputs/p9_table.md. Stops at $1.00 of P9 spend."""
import json, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import llm, medcheck
L = json.loads((ROOT / "tests" / "p9_labels.json").read_text(encoding="utf-8"))
p9 = lambda: sum(e["usd"] for e in json.loads(llm.SPEND.read_text()) if e.get("probe") == "P9")
rows = []
for exp, names in (("found", L["expected_found"]), ("not found", L["expected_not_found"]), ("strength not found", L["expected_strength_not_found"])):
    for n in names:
        if p9() > 1.0:
            rows.append(dict(name=n, expected=exp, result="not run (P9 spend limit)", domain="", why="")); continue
        try:
            st, j = medcheck.search(n)
            ans = medcheck.answer_of(j)
            ok, host, why = medcheck.verify(n, ans)
        except Exception as e:
            ans, ok, host, why = None, False, "", type(e).__name__
        rows.append(dict(name=n, expected=exp, result="found" if ok else "not found", domain=host if ok else "", why=why, model=ans))
        print(n, "->", rows[-1]["result"], host if ok else why, flush=True)
f = [r for r in rows if r["expected"] == "found"]; fk = [r for r in rows if r["expected"] == "not found"]; ws = [r for r in rows if r["expected"] == "strength not found"]
res = dict(found_ok=sum(r["result"] == "found" for r in f), found_total=len(f), fakes_found=sum(r["result"] == "found" for r in fk), wrong_strength_found=sum(r["result"] == "found" for r in ws), spend=round(p9(), 3))
res["pass"] = res["found_ok"] >= 15 and res["fakes_found"] == 0 and res["wrong_strength_found"] == 0
(ROOT / "outputs" / "p9_results.json").write_text(json.dumps(dict(summary=res, rows=rows), indent=1, ensure_ascii=False), encoding="utf-8")
t = ["| Name | Expected | Result | Source domain | Note |", "|---|---|---|---|---|"] + [f"| {r['name']} | {r['expected']} | {r['result']} | {r['domain'] or '-'} | {r['why']} |" for r in rows]
(ROOT / "outputs" / "p9_table.md").write_text("\n".join(t), encoding="utf-8")
print(res)
