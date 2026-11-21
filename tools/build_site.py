"""Build the site from the study files.
Usage: python3 tools/build_site.py OUTDIR [--also DIR] [--benchmarks FILE] [--site FILE]
Reads studies/*.json (and DIR/*.json), benchmarks.json and site.json.
Writes the pages, studies/, index.json, models.json, cameo-all.json, boards/, kit/ and llms.txt into OUTDIR."""
import argparse, copy, glob, importlib.util, json, os, re, shutil, statistics, sys, zipfile
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("--also"); ap.add_argument("--benchmarks", default=os.path.join(root, "benchmarks.json")); ap.add_argument("--site", default=os.path.join(root, "site.json"))
ap.add_argument("--studies", default=os.path.join(root, "studies"), help="the folder of study files, when it is not this repository's")
ap.add_argument("--max-bundle-mb", type=float, default=90, help="leave cameo-all.json out when the studies together are larger than this")
A = ap.parse_args(); out = A.out; sys.argv = sys.argv[:1]
sp = importlib.util.spec_from_file_location("cameo", os.path.join(root, "kit", "cameo.py")); C = importlib.util.module_from_spec(sp); sp.loader.exec_module(C)
BENCH = json.load(open(A.benchmarks)); SITE = json.load(open(A.site)); BY_ID = {b["id"]: b for b in BENCH}
os.makedirs(os.path.join(out, "studies"), exist_ok=True); os.makedirs(os.path.join(out, "boards"), exist_ok=True)
shutil.copy(os.path.join(root, "site", "index.html"), out); shutil.copy(os.path.join(root, "kit", "rules.json"), out)
num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
kn = lambda v: v if C.known(v) else None


def tags_of(I, benches):
    """Keywords for browsing: the depositor's own, then each benchmark's field and task, then the kind of study."""
    out = []
    def add(v):
        for x in (v if isinstance(v, list) else str(v).split(",")) if C.known(v) else []:
            x = str(x).strip().replace("_", " ")
            if x and x.lower() not in [o.lower() for o in out]:
                out.append(x)
    add(I["study"].get("tags"))
    for b in benches:
        add(b.get("domain")); add(b.get("task_type"))
    dom = C.get(I, "dataset.domain")
    add(str(dom).split(":")[0] if isinstance(dom, str) else dom); add(C.get(I, "objective.kind"))   # "genomics: promoter activity ..." is filed under genomics
    return out[:8]


def link_of(w):
    """A safe link: an https address or a DOI. Anything else is dropped."""
    v = (w.get("url") if C.known(w.get("url")) else w.get("doi")) if isinstance(w, dict) else w
    if not C.known(v):
        return None
    v = str(v).strip(); m = re.fullmatch(r"(?:doi:|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/\S+)", v, re.I)
    if m:
        return {"href": "https://doi.org/" + m.group(1), "label": "DOI " + m.group(1)}
    return {"href": v, "label": re.sub(r"^www\.", "", v.split("/")[2])} if re.fullmatch(r"https://\S+", v) else None


def bench_of(ds):
    """Which benchmark a dataset belongs to: the id it declares, else a word in its name."""
    if not isinstance(ds, dict):
        return None
    return BY_ID.get(ds.get("benchmark")) if C.known(ds.get("benchmark")) and ds.get("benchmark") in BY_ID else next((b for b in BENCH if b.get("match") and b["match"] in str(ds.get("name") or "").lower()), None)


def names_of(b):
    """The names a benchmark's metric goes by: its own, then any other name a study used for the same quantity."""
    return [b["metric"]] + [k for k in (b.get("metric_aliases") or []) if isinstance(k, str)]


def examples_text(ex):
    """Example counts that a study gave in words, as one line."""
    if isinstance(ex, str):
        return ex if C.known(ex) else None
    if not isinstance(ex, dict) or not any(isinstance(ex.get(k), str) and C.known(ex.get(k)) for k in ("train", "valid", "test")):
        return None
    word = {"train": "train", "valid": "validation", "test": "test"}
    return " · ".join(("{:,} {}".format(ex[k], word[k]) if num(ex[k]) else "{}: {}".format(word[k], ex[k])) for k in ("train", "valid", "test") if C.known(ex.get(k)))


def slug_of(name, orcid):
    return str(orcid) if C.known(orcid) else re.sub(r"[^a-z0-9]+", "-", str(name or "unnamed").lower()).strip("-")


def text_of(v, key="how"):
    """A short description that may be stored as text or as an object with the text under one key."""
    if isinstance(v, dict):
        v = next((v[k] for k in (key, "scheme", "description", "kind") if C.known(v.get(k))), None)
    if isinstance(v, list):   # a list of sentences reads as one paragraph
        v = " ".join(str(x).rstrip(".") + "." for x in v if isinstance(x, str) and C.known(x)) or None
    return str(v) if C.known(v) and not isinstance(v, (dict, list)) else None


def prep_of(ds):
    """How one study prepared a dataset: the facts a reader needs before comparing its numbers with another study's."""
    ex = ds.get("examples") if isinstance(ds.get("examples"), dict) else {}
    acc = next((ds.get(k) for k in ("doi", "accession", "url") if C.known(ds.get(k))), None)
    pre = ds.get("preprocessing")
    return {"dataset": kn(ds.get("name")), "accession": str(acc) if acc is not None else None, "link": link_of(acc), "input": kn(ds.get("input")), "output": kn(ds.get("output")),
            "examples": {k: ex[k] for k in ("train", "valid", "test") if num(ex.get(k))}, "examples_text": examples_text(ds.get("examples")), "split": text_of(ds.get("splits")), "split_shared": C.split_shared(ds),
            "preprocessing": text_of(pre), "preprocessing_code": isinstance(pre, dict) and C.known(pre.get("code"))}


index = {"site": SITE, "benchmarks": [], "studies": [], "depositors": []}; bundle = []; rows = {b["id"]: [] for b in BENCH}; prep = {b["id"]: [] for b in BENCH}; runs = {b["id"]: [] for b in BENCH}; cover = {b["id"]: [] for b in BENCH}; failed = 0; deps = {}
paths = sorted(glob.glob(os.path.join(A.studies, "*.json"))) + (sorted(glob.glob(os.path.join(A.also, "*.json"))) if A.also else [])
for path in paths:
    text = open(path, encoding="utf-8").read(); rep = C.check_text(text)
    if not rep["ok"]:
        print("SKIPPED %s: %s" % (path, "; ".join(x["message"] for x in rep["blocking"]))); failed += 1; continue
    S = json.loads(text); made_up = bool(S.pop("_made_up", False)); I = C.to_internal(copy.deepcopy(S)); sid = I["study"]["id"]
    json.dump(C.to_external(S), open(os.path.join(out, "studies", sid + ".json"), "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    bundle.append(sid)
    DS = C.datasets_of(I); dsb = {k: bench_of(v) for k, v in DS.items()}; benches = []
    for b in dsb.values():
        if b and b not in benches:
            benches.append(b)
    res = lambda t: t.get("result") if isinstance(t.get("result"), dict) else {}
    recipes, _ = C.recipes_of(I); mby = {m.get("id"): m for m in I["models"]}
    done = [t for t in I["trials"] if res(t).get("status") == "done" and num(res(t).get("score")) and C.kind_of(t) != "reported"]
    reported = [t for t in I["trials"] if res(t).get("status") == "done" and C.kind_of(t) == "reported"]   # numbers copied from a paper; never mixed with the study's own runs
    sign = -1 if C.get(I, "objective.optimize.direction") == "maximize" else 1

    def metric_on(t, b, split):
        """A run's value for a benchmark's metric on one split, and the name the study stored it under.
        It comes from an evaluation on that benchmark's dataset, else from the run's results on the main dataset."""
        r = res(t)
        for e in (r.get("evaluations") if isinstance(r.get("evaluations"), list) else []):
            if isinstance(e, dict) and dsb.get(e.get("dataset") if C.known(e.get("dataset")) else "main") is b and (e.get("split") == split or (split == b["split"] and not C.known(e.get("split")))):
                k = next((k for k in names_of(b) if isinstance(e.get("metrics"), dict) and num(e["metrics"].get(k))), None)
                if k is not None:
                    return e["metrics"][k], "performance.evaluations[].metrics." + k
        own = r.get(split) if dsb.get("main") is b and isinstance(r.get(split), dict) else {}
        k = next((k for k in names_of(b) if num(own.get(k))), None)
        return (own[k], "performance.%s.%s" % (split, k)) if k is not None else (None, None)

    metric_for = lambda t, b: metric_on(t, b, b["split"])[0]
    study_dev = kn(C.D_(C.get(I, "evaluation.training_context")).get("device"))

    def device_of(t):
        """Where a run was trained: the study's stated device, else what the run itself recorded."""
        r = res(t); comp = r.get("compute") if isinstance(r.get("compute"), dict) else {}
        return study_dev or kn(r.get("gpu")) or kn(comp.get("gpu"))

    # runs that differ only in their seed are repeats of one configuration
    groups = {}
    for t in done:
        groups.setdefault((t.get("model"), json.dumps([C.recipe_id(t, recipes), t.get("training") or {}, C.kind_of(t)], sort_keys=True, default=str)), []).append(t)
    best_here = None
    for b in benches:
        for mid, m in mby.items():
            cand = [g for (k, _), g in groups.items() if k == mid and any(metric_for(t, b) is not None for t in g)]
            if not cand:
                continue
            g = min(cand, key=lambda g: statistics.mean(sign * res(t)["score"] for t in g))   # chosen on the study's own objective, never on the test metric
            vals = [v for v in (metric_for(t, b) for t in g) if v is not None]; top = min(g, key=lambda t: sign * res(t)["score"]); r = res(top)
            mins = [res(t).get("runtime_minutes") for t in g if num(res(t).get("runtime_minutes"))]; base = m.get("base_model") if isinstance(m.get("base_model"), dict) else {}
            rows[b["id"]].append({"study": sid, "study_title": I["study"].get("title"), "depositor": C.get(I, "contributor.name"), "made_up": made_up, "star": rep["star"]["level"],
                                  "run": top["id"], "name": m.get("name") or mid, "family": m.get("family"), "kind": C.kind_of(top), "base": kn(base.get("name")), "weights": link_of(top.get("weights")),
                                  "score": r.get("score"), "metric": statistics.mean(vals), "sd": statistics.stdev(vals) if len(vals) > 1 else None, "n": len(vals),
                                  "params": r.get("parameters"), "minutes": statistics.mean(mins) if mins else None, "train_device": device_of(top),
                                  "speed": C.get(m, "inference_speed.seq_per_s"), "speed_device": C.D_(C.get(I, "evaluation.speed_context")).get("device")})
        for t in reported:   # one row per reported result, marked as such, with its source
            v = metric_for(t, b)
            if v is None:
                continue
            m = mby.get(t.get("model")) or {}; src = t.get("reported_in") if isinstance(t.get("reported_in"), dict) else {}
            rows[b["id"]].append({"study": sid, "study_title": I["study"].get("title"), "depositor": C.get(I, "contributor.name"), "made_up": made_up, "star": rep["star"]["level"],
                                  "run": t["id"], "name": m.get("name") or t.get("model"), "family": m.get("family"), "kind": "reported", "base": None, "weights": link_of(t.get("weights")),
                                  "reported": {"citation": kn(src.get("citation")), "where": kn(src.get("where")), "note": kn(src.get("note")), "link": link_of(C.source_link(t))},
                                  "score": None, "metric": v, "sd": None, "n": 1, "params": res(t).get("parameters") if num(res(t).get("parameters")) else None, "minutes": None, "train_device": None,
                                  "speed": None, "speed_device": None})
        fields = {}
        for t in I["trials"]:   # every run, scored or not: a chart across studies plots the ones that have both of its values and counts the rest
            r = res(t); m = mby.get(t.get("model")) or {}; vals = {}
            for sp in ("valid", "test"):
                vals[sp], f = metric_on(t, b, sp)
                if f:
                    fields[sp] = f
            alias = set(names_of(b)); allm = {}
            if dsb.get("main") is b:   # every metric the run recorded, by the name the study gave it; the benchmark's own goes under the benchmark's name
                for sp in ("valid", "test"):
                    own = r.get(sp) if isinstance(r.get(sp), dict) else {}
                    got = {(b["metric"] if k in alias else k): v for k, v in own.items() if num(v)}
                    if vals[sp] is not None:
                        got[b["metric"]] = vals[sp]
                    if got:
                        allm[sp] = got
            runs[b["id"]].append({"study": sid, "run": t["id"], "m": allm, "name": m.get("name") or t.get("model"), "family": kn(m.get("family")), "kind": C.kind_of(t), "status": kn(r.get("status")),
                                  "valid": vals["valid"], "test": vals["test"], "params": r.get("parameters") if num(r.get("parameters")) else m.get("parameters") if num(m.get("parameters")) else None,
                                  "minutes": r.get("runtime_minutes") if num(r.get("runtime_minutes")) else None, "seed": t.get("seed") if num(t.get("seed")) else None})
        cover[b["id"]].append({"study": sid, "study_title": I["study"].get("title"), "runs": len(I["trials"]), "fields": fields})
        for k, ds in DS.items():
            if dsb.get(k) is b:
                prep[b["id"]].append({"study": sid, "study_title": I["study"].get("title"), "depositor": C.get(I, "contributor.name"), "made_up": made_up, "only_reported": bool(reported) and not done, **prep_of(ds)})
        mine = [r["metric"] for r in rows[b["id"]] if r["study"] == sid and r["kind"] != "reported"] or [r["metric"] for r in rows[b["id"]] if r["study"] == sid]
        if best_here is None and mine:
            best_here = (min if b.get("direction") == "minimize" else max)(mine)
    if not benches:
        print("note: %s is on no benchmark in benchmarks.json yet" % os.path.basename(path))
    con = I.get("contributor") if isinstance(I.get("contributor"), dict) else {}; slug = slug_of(con.get("name"), con.get("orcid"))
    bases = sorted({str(m["base_model"]["name"]) for m in I["models"] if isinstance(m.get("base_model"), dict) and C.known(m["base_model"].get("name"))})
    entry = {"id": sid, "title": I["study"].get("title"), "summary": kn(I["study"].get("question")), "depositor": kn(con.get("name")), "depositor_slug": slug, "lab": kn(con.get("lab")),
             "created": I["study"].get("created"), "license": I["study"].get("license"), "benchmark": benches[0]["id"] if benches else None, "benchmark_title": benches[0]["title"] if benches else None,
             "benchmarks": [b["id"] for b in benches], "runs": sum(1 for t in I["trials"] if C.kind_of(t) != "reported"), "models": len(I["models"]), "star": rep["star"]["level"], "made_up": made_up, "tags": tags_of(I, benches),
             "families": sorted({str(m.get("family")).replace("_", " ") for m in I["models"] if C.known(m.get("family"))}), "bases": bases,
             "kinds": sorted({C.kind_of(t) for t in I["trials"]}), "reported": len(reported), "best": best_here}
    index["studies"].append(entry)
    d = deps.setdefault(slug, {"slug": slug, "name": kn(con.get("name")) or "Depositor not named", "lab": None, "institution": None, "orcid": None, "studies": [], "runs": 0, "models": 0})
    d["studies"].append(sid); d["runs"] += entry["runs"]; d["models"] += entry["models"]
    for k in ("lab", "institution", "orcid"):
        d[k] = d[k] or kn(con.get(k))

flat = []
for b in BENCH:
    low = b.get("direction") == "minimize"
    rs = sorted(rows[b["id"]], key=lambda r: r["metric"] if low else -r["metric"])
    json.dump({"benchmark": b, "rows": rs, "prep": prep[b["id"]], "runs": runs[b["id"]], "studies": cover[b["id"]]}, open(os.path.join(out, "boards", b["id"] + ".json"), "w"), separators=(",", ":"), ensure_ascii=False)
    st = [s for s in index["studies"] if b["id"] in s["benchmarks"]]
    if st:
        top = next((r for r in rs if r["kind"] != "reported"), rs[0] if rs else None)   # the headline number is a run someone deposited, when there is one
        index["benchmarks"].append({**b, "studies": len(st), "models": len(rs), "reported": sum(1 for r in rs if r["kind"] == "reported"), "best": top["metric"] if top else None,
                                    "best_by": top["depositor"] if top else None, "best_reported": bool(top) and top["kind"] == "reported"})
    flat += [{**r, "benchmark": b["id"], "benchmark_title": b["title"], "metric_label": b["metric_label"]} for r in rs]
json.dump(flat, open(os.path.join(out, "models.json"), "w"), separators=(",", ":"), ensure_ascii=False)   # every model on every leaderboard, for the search across studies
index["studies"].sort(key=lambda s: str(s.get("created") or ""), reverse=True)
index["depositors"] = sorted(deps.values(), key=lambda d: d["name"].lower())
index["totals"] = {"studies": len(index["studies"]), "benchmarks": len(index["benchmarks"]), "models": sum(s["models"] for s in index["studies"]), "runs": sum(s["runs"] for s in index["studies"])}
# every study in one file, for a merged download. It is written piece by piece so that the build never holds two copies of the database.
# GitHub refuses files over 100 MB. Past 90 MB the file is left out, and the page merges the study files in the browser instead.
size = sum(os.path.getsize(os.path.join(out, "studies", sid + ".json")) for sid in bundle); allp = os.path.join(out, "cameo-all.json")
if bundle and size < A.max_bundle_mb * 1e6:
    with open(allp, "w", encoding="utf-8") as f:
        f.write('{"cameo_bundle":"%s","from":%s,"studies":[' % (C.FORMAT, json.dumps(str(SITE.get("url") or ""))))
        for i, sid in enumerate(bundle):
            f.write(("," if i else "") + open(os.path.join(out, "studies", sid + ".json"), encoding="utf-8").read())
        f.write("]}")
    index["site"] = {**SITE, "bundle": "cameo-all.json"}
elif os.path.exists(allp):
    os.remove(allp)
json.dump(index, open(os.path.join(out, "index.json"), "w"), indent=1, ensure_ascii=False)

# what a training loop or an agent needs to write entries, served beside the site
KIT = ["CAMEO_LOOP_SPEC.md", "cameo.py", "rules.json", "example_minimal.json", "DEPOSIT.md", "depositor.example.json"]
os.makedirs(os.path.join(out, "kit"), exist_ok=True)
with zipfile.ZipFile(os.path.join(out, "kit", "cameo-agent-kit.zip"), "w", zipfile.ZIP_DEFLATED) as z:
    for name in KIT:
        src = os.path.join(root, "kit", name); shutil.copy(src, os.path.join(out, "kit", name))
        zi = zipfile.ZipInfo("cameo-agent-kit/" + name, date_time=(2026, 1, 1, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED; zi.external_attr = 0o644 << 16   # a fixed date, so the zip only changes when its files do
        z.writestr(zi, open(src, "rb").read())
base = (str(SITE.get("url")).rstrip("/") + "/") if C.known(SITE.get("url")) else ""
open(os.path.join(out, "llms.txt"), "w", encoding="utf-8").write("""# CAMEO

> Catalog of Architecture Metadata and Experimental Outcomes: an open database of the models that studies train, including the ones that never reach the paper. Each entry is one JSON file that holds the models, how they were trained and how they performed.

## Write an entry

- [Instructions for a training loop or an agent](%(b)skit/CAMEO_LOOP_SPEC.md): the entry format, the rules, and a full example
- [Checker](%(b)skit/cameo.py): run `python3 cameo.py check study.json`; it needs rules.json beside it
- [Rules](%(b)skit/rules.json): the checks, the open licenses and what each star means
- [Example entry](%(b)skit/example_minimal.json): a complete entry that passes every check
- [All of these as one zip](%(b)skit/cameo-agent-kit.zip)

## Read the database

- [index.json](%(b)sindex.json): every study, benchmark and depositor
- [models.json](%(b)smodels.json): every model on every leaderboard, one row each
- `%(b)sboards/<benchmark id>.json`: one leaderboard, and how each study on it prepared the data. Its `runs` list has one row for every run of every study on the benchmark, with the benchmark's metric on the validation and test splits under one name, the parameter count and the status. Each row's `m` holds every other metric the run recorded, under the name its study gave it. Key a run by `study` and `run` together: run ids repeat between studies. `studies[].fields` says where each study's file stores the metric
- `%(b)sstudies/<study id>.json`: one whole entry, in the format the instructions describe
- [cameo-all.json](%(b)scameo-all.json): every entry in one file, as `{"studies": [...]}`. Use it to start a new search from what has been tried

Benchmark and study ids are listed in index.json. Results marked `"kind": "reported"` were copied from a paper, not run by the depositor.
""" % {"b": base})
print("built %d studies, %d benchmarks, %d models on leaderboards, %d skipped" % (len(index["studies"]), len(index["benchmarks"]), len(flat), failed))
