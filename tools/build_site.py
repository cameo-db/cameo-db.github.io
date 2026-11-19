"""Build the site from the study files. Usage: python3 tools/build_site.py OUTDIR
Reads studies/*.json and benchmarks.json. Writes the pages, studies/, index.json and boards/ into OUTDIR."""
import copy, glob, importlib.util, json, os, shutil, sys
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); out = sys.argv[1]; sys.argv = sys.argv[:1]
sp = importlib.util.spec_from_file_location("cameo", os.path.join(root, "kit", "cameo.py")); C = importlib.util.module_from_spec(sp); sp.loader.exec_module(C)
BENCH = json.load(open(os.path.join(root, "benchmarks.json")))
os.makedirs(os.path.join(out, "studies"), exist_ok=True); os.makedirs(os.path.join(out, "boards"), exist_ok=True)
shutil.copy(os.path.join(root, "site", "index.html"), out); shutil.copy(os.path.join(root, "kit", "rules.json"), out)
index = {"benchmarks": [], "studies": []}; rows = {b["id"]: [] for b in BENCH}; failed = 0
for path in sorted(glob.glob(os.path.join(root, "studies", "*.json"))):
    text = open(path, encoding="utf-8").read(); rep = C.check_text(text)
    if not rep["ok"]:
        print("SKIPPED %s: %s" % (path, "; ".join(x["message"] for x in rep["blocking"]))); failed += 1; continue
    S = json.loads(text); I = C.to_internal(copy.deepcopy(S)); sid = I["study"]["id"]
    b = next((b for b in BENCH if b["match"] in (C.get(I, "dataset.name") or "").lower()), None)
    if not b:
        print("SKIPPED %s: its dataset matches no entry in benchmarks.json" % path); failed += 1; continue
    json.dump(C.to_external(S), open(os.path.join(out, "studies", sid + ".json"), "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    res = lambda t: t.get("result") if isinstance(t.get("result"), dict) else {}
    done = [t for t in I["trials"] if res(t).get("status") == "done" and isinstance(res(t).get("score"), (int, float))]
    sign = -1 if C.get(I, "objective.optimize.direction") == "maximize" else 1; mine = []
    for m in I["models"]:
        ts = [t for t in done if t.get("model") == m.get("id")]
        if not ts:
            continue
        t = min(ts, key=lambda t: sign * res(t)["score"]); r = res(t)   # chosen on the study's own objective, never on the test metric
        mine.append({"study": sid, "study_title": I["study"].get("title"), "depositor": C.get(I, "contributor.name"), "made_up": False, "tag": rep["reproducibility"]["tag"],
                     "run": t["id"], "name": m.get("name") or m.get("id"), "family": m.get("family"), "score": r.get("score"), "metric": (r.get(b["split"]) or {}).get(b["metric"]),
                     "params": r.get("parameters"), "minutes": r.get("runtime_minutes"), "train_device": C.D_(C.get(I, "evaluation.training_context")).get("device"),
                     "speed": C.get(m, "inference_speed.seq_per_s"), "speed_device": C.D_(C.get(I, "evaluation.speed_context")).get("device")})
    rows[b["id"]] += mine; kn = lambda v: v if C.known(v) else None
    index["studies"].append({"id": sid, "title": I["study"].get("title"), "summary": kn(I["study"].get("question")), "depositor": C.get(I, "contributor.name"), "lab": kn(C.get(I, "contributor.lab")),
                             "created": I["study"].get("created"), "license": I["study"].get("license"), "benchmark": b["id"], "benchmark_title": b["title"], "runs": len(I["trials"]),
                             "models": len(I["models"]), "tag": rep["reproducibility"]["tag"], "made_up": False, "best": max((r["metric"] for r in mine if r["metric"] is not None), default=None)})
sgn = lambda b: -1 if b.get("direction") != "minimize" else 1
for b in BENCH:
    rs = sorted(rows[b["id"]], key=lambda r: (r["metric"] is None, sgn(b) * (r["metric"] or 0)))
    json.dump({"benchmark": {k: b[k] for k in b if k != "match"}, "rows": rs}, open(os.path.join(out, "boards", b["id"] + ".json"), "w"), separators=(",", ":"), ensure_ascii=False)
    n = len([s for s in index["studies"] if s["benchmark"] == b["id"]])
    if n:
        index["benchmarks"].append({**{k: b[k] for k in b if k != "match"}, "studies": n, "models": len(rs), "best": rs[0]["metric"] if rs else None, "best_by": rs[0]["depositor"] if rs else None})
json.dump(index, open(os.path.join(out, "index.json"), "w"), indent=1, ensure_ascii=False)
print("built %d studies, %d benchmarks, %d skipped" % (len(index["studies"]), len(index["benchmarks"]), failed))
