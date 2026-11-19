#!/usr/bin/env python3
"""cameo.py: prepare a study file for deposit in CAMEO.

  init         write a blank study file to fill in
  check        list what blocks publishing, what is suggested, and what is missing to rebuild training
  fix          apply the safe automatic repairs (non-finite numbers, depositor details, format version)
  add-layers   build each model once and store its layer list and parameter count   (needs PyTorch)
  add-speed    measure inference speed for each model on this machine               (needs PyTorch)
  export-run   write one run's model code, resolved settings and training recipe to a folder

Standard library only, except add-layers and add-speed. Nothing here sends data anywhere.
"""
import copy
import argparse, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = json.load(open(os.path.join(HERE, "rules.json"), encoding="utf-8"))
FORMAT = RULES["format_version"]


# ----------------------------------------------------------------------------- small helpers
def fill(template, kw):
    """Fill {name} placeholders only; other braces (JSON examples in the text) are left alone."""
    return re.sub(r"\{(\w+)\}", lambda m: str(kw[m.group(1)]) if m.group(1) in kw else m.group(0), template)


def known(v):
    return v not in (None, "", "not_reported") and v != {} and v != []


def has_known(v):
    """A dict or list counts as filled only if something inside it is known."""
    if isinstance(v, dict):
        return any(has_known(x) for x in v.values())
    if isinstance(v, list):
        return any(has_known(x) for x in v)
    return known(v)


def get(o, path):
    for k in path.split("."):
        if not isinstance(o, dict) or k not in o:
            return None
        o = o[k]
    return o


def put(o, path, v):
    ks = path.split(".")
    for k in ks[:-1]:
        if not isinstance(o.get(k), dict):
            o[k] = {}
        o = o[k]
    o[ks[-1]] = v


TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|-?Infinity|NaN')


def nonfinite(text):
    """Bare Infinity / NaN outside strings: [(line, token)]. JSON does not allow them."""
    return [(text.count("\n", 0, m.start()) + 1, m.group(0)) for m in TOKEN.finditer(text) if not m.group(0).startswith('"')]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(S, path):
    S = to_external(S)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(S, f, ensure_ascii=False, indent=1, allow_nan=False)
        f.write("\n")


def recipes_of(S):
    """Recipes by id. A file without recipes (format 0.1) has one implied recipe: the study's training defaults."""
    R = S.get("recipes")
    if isinstance(R, dict) and R:
        return R, False
    return {"base": {"settings": (S.get("search") or {}).get("training_defaults") or {}}}, True


def recipe_id(trial, recipes):
    r = trial.get("recipe")
    return r if known(r) else next(iter(recipes))


def resolved(trial, recipe):
    """The settings a run trained with: the recipe's, with the run's own on top."""
    out = dict((recipe or {}).get("settings") or {})
    out.update(trial.get("training") or {})
    return out


def is_crossover(t):
    return t.get("operation") == "crossover" or t.get("move") == "composition" or known(t.get("second_parent")) \
        or "crossover)" in " ".join(n.get("text", "") for n in (t.get("notes") or []) if isinstance(n, dict))



# ----------------------------------------------------------------------------- file layout
# On disk a study has four parts: experiment, models, training, runs. The checks below work on an older,
# flatter layout (study, contributor, dataset, recipes, trials ...), so files are converted on the way in and out.
GROUPS = ("depositor", "run_by", "objective", "data", "evaluation", "environment", "search", "conclusions")
HISTORY = ("lineage", "parent_trial", "second_parent", "move", "purpose", "hypothesis", "predicted_effect")
SRC = "custom_ops.model_source.reference_implementation"
HW = (("training_hardware", "training_context"), ("inference_hardware", "speed_context"))
OLD_TOP = ("format_version", "study", "contributor", "objective", "dataset", "evaluation", "environment", "search", "lineages", "summary", "recipes", "models", "trials")


def D_(v):
    return dict(v) if isinstance(v, dict) else {}


def is_new(S):
    return isinstance(S, dict) and isinstance(S.get("experiment"), dict) and "runs" in S


def shown(path):
    for a, b in (("study.question", "experiment.summary"), ("study.", "experiment."), ("contributor.", "experiment.depositor."), ("dataset.", "experiment.data.")):
        if path.startswith(a):
            return b + path[len(a):]
    return path


def to_internal(S):
    if not is_new(S):
        return S
    S = copy.deepcopy(S); E = S["experiment"]
    out = {k: v for k, v in S.items() if k not in ("experiment", "models", "training", "runs")}
    study = {("question" if k == "summary" else k): v for k, v in E.items() if k not in GROUPS}
    con = D_(E.get("depositor"))
    if "run_by" in E:
        con["run_by"] = E["run_by"]
    ev, env, search = D_(E.get("evaluation")), D_(E.get("environment")), D_(E.get("search"))
    for a, b in HW:
        if a in env:
            ev[b] = env.pop(a)
    out.update(study=study, contributor=con, evaluation=ev)
    if env:
        out["environment"] = env
    if "objective" in E:
        out["objective"] = E["objective"]
    if "data" in E:
        out["dataset"] = E["data"]
    if "lineages" in search:
        out["lineages"] = search.pop("lineages")
    if search:
        out["search"] = search
    if "conclusions" in E:
        c = D_(E["conclusions"])
        if "best_run" in c:
            c["best_trial"] = c.pop("best_run")
        out["summary"] = c
    recipes = {}
    for rid, r in D_(S.get("training")).items():
        r = D_(r)
        if "code" in r:
            c = r.pop("code")
            if isinstance(c, dict) and "script" in c:
                c["code"] = c.pop("script")
            r["source"] = c
        recipes[rid] = r
    models = []
    for m in (S.get("models") if isinstance(S.get("models"), list) else []):
        m = D_(m)
        if "code" in m:
            put(m, SRC, m.pop("code"))
        models.append(m)
    trials = []
    for r in (S.get("runs") if isinstance(S.get("runs"), list) else []):
        r = D_(r); t = {k: v for k, v in r.items() if k not in ("training", "settings", "history", "performance")}
        if "training" in r:
            t["recipe"] = r["training"]
        t["training"] = D_(r.get("settings"))
        for k, v in D_(r.get("history")).items():
            if k == "second_parent" and isinstance(v, dict) and "run" in v:
                v["trial"] = v.pop("run")
            t["parent_trial" if k == "parent" else k] = v
        if "performance" in r:
            p = r["performance"]
            if isinstance(p, dict) and "training_minutes" in p:
                p["runtime_minutes"] = p.pop("training_minutes")
            t["result"] = p
        trials.append(t)
    out["recipes"], out["models"], out["trials"] = recipes, models, trials
    return out


def to_external(S):
    if is_new(S) or not (isinstance(S, dict) and isinstance(S.get("study"), dict)):
        return S
    S = copy.deepcopy(S); recipes, implied = recipes_of(S)
    E = {("summary" if k == "question" else k): v for k, v in S["study"].items()}
    con = D_(S.get("contributor")); run_by = con.pop("run_by", None)
    E["depositor"] = con
    if run_by is not None:
        E["run_by"] = run_by
    if "objective" in S:
        E["objective"] = S["objective"]
    if "dataset" in S:
        E["data"] = S["dataset"]
    ev, env, search = D_(S.get("evaluation")), D_(S.get("environment")), D_(S.get("search"))
    for a, b in HW:
        if b in ev:
            env[a] = ev.pop(b)
    E["evaluation"], E["environment"] = ev, env
    if implied:
        search.pop("training_defaults", None)
    if "lineages" in S:
        search["lineages"] = S["lineages"]
    if search:
        E["search"] = search
    if "summary" in S:
        c = D_(S["summary"])
        if "best_trial" in c:
            c["best_run"] = c.pop("best_trial")
        E["conclusions"] = c
    training = {}
    for rid, r in recipes.items():
        r = D_(r)
        if "source" in r:
            c = r.pop("source")
            if isinstance(c, dict) and "code" in c:
                c["script"] = c.pop("code")
            r["code"] = c
        training[rid] = r
    models = []
    for m in (S.get("models") if isinstance(S.get("models"), list) else []):
        m = D_(m); src = get(m, SRC)
        if src is not None:
            ms = m["custom_ops"]["model_source"]; del ms["reference_implementation"]
            if not ms:
                del m["custom_ops"]["model_source"]
            if not m["custom_ops"]:
                del m["custom_ops"]
            m["code"] = src
        models.append(m)
    runs = []
    for t in (S.get("trials") if isinstance(S.get("trials"), list) else []):
        t = D_(t); r = {k: t[k] for k in ("id", "model", "model_args") if k in t}
        r["training"] = recipe_id(t, recipes)
        if "seed" in t:
            r["seed"] = t["seed"]
        r["settings"] = D_(t.get("training"))
        h = {}
        for k in HISTORY:
            if k in t:
                v = t[k]
                if k == "second_parent" and isinstance(v, dict) and "trial" in v:
                    v["run"] = v.pop("trial")
                h["parent" if k == "parent_trial" else k] = v
        r["history"] = h
        if "result" in t:
            p = t["result"]
            if isinstance(p, dict) and "runtime_minutes" in p:
                p["training_minutes"] = p.pop("runtime_minutes")
            r["performance"] = p
        for k, v in t.items():
            if k not in r and k not in HISTORY + ("recipe", "training", "result"):
                r[k] = v
        runs.append(r)
    out = {"format_version": S.get("format_version", FORMAT), "experiment": E, "models": models, "training": training, "runs": runs}
    out.update({k: v for k, v in S.items() if k not in OLD_TOP})
    return out


# ----------------------------------------------------------------------------- check
def recipe_missing(rec, trials):
    """Details still needed to re-implement training for the runs that use this recipe (the training code aside)."""
    D, miss = RULES["recipe_details"], []

    def need(kind, **kw):
        miss.append({"id": kind + (":" + kw["name"] if "name" in kw else ""), "message": fill(D[kind]["message"], kw), "fix": fill(D[kind]["fix"], kw)})

    used = [resolved(t, rec) for t in trials]
    for name in RULES["core_settings"]:
        if any(not known(u.get(name)) for u in used):
            need("setting", name=name)
    loss = rec.get("loss") if isinstance(rec.get("loss"), dict) else {}
    if not known(loss.get("kind")) and any(not known(u.get("loss")) for u in used):
        need("loss-kind")
    if not has_known(loss.get("terms")):
        need("loss-terms")
    if not known(loss.get("reduction")):
        need("loss-reduction")
    schedules = rec.get("schedules") if isinstance(rec.get("schedules"), dict) else {}
    for name in sorted({str(u.get("schedule")) for u in used if known(u.get("schedule"))}):
        if name != "constant" and not has_known(schedules.get(name)):
            need("schedule", name=name)
    es = rec.get("early_stopping")
    if es is not False:
        es = es if isinstance(es, dict) else {}
        if not (known(es.get("metric")) and known(es.get("split"))):
            need("stopping-metric")
        if not (known(es.get("patience")) or known(es.get("patience_setting")) or (used and all(known(u.get("patience")) for u in used))):
            need("stopping-patience")
    if not known(rec.get("checkpoint")):
        need("checkpoint")
    if not isinstance(rec.get("shuffle"), bool):
        need("shuffle")
    if not known(rec.get("augmentation")):
        need("augmentation")
    if not known(rec.get("init")):
        need("init")
    defs = rec.get("definitions") if isinstance(rec.get("definitions"), dict) else {}
    for name in RULES["defined_settings"]:
        if any(u.get(name) is True for u in used) and not known(defs.get(name)):
            need("definition", name=name)
    return miss


def has_code(rec):
    return known(get(rec, "source.code"))


def rebuild_level(rec, miss):
    return "exact" if has_code(rec) else ("partial" if miss else "faithful")


def check_text(text):
    C = RULES["checks"]
    rep = {"ok": False, "blocking": [], "suggested": [], "checked": [], "reproduce": {}}

    def add(cid, **kw):
        c = C[cid]
        item = {"id": cid, "message": fill(c["message"], kw), "fix": fill(c["fix"], kw)}
        if "path" in c:
            item["path"] = c["path"]
        rep["blocking" if c["level"] == "block" else "suggested"].append(item)

    nf = nonfinite(text)
    if nf:
        add("json-nonfinite", n=len(nf), line=nf[0][0])
    try:
        S = json.loads(text, parse_constant=lambda c: None)
    except ValueError as e:
        add("json-invalid", detail=str(e))
        return rep
    S = to_internal(S)
    if not (isinstance(S, dict) and isinstance(S.get("study"), dict) and isinstance(S.get("models"), list) and isinstance(S.get("trials"), list)):
        add("shape")
        return rep
    models, trials = S["models"], S["trials"]
    if str(S.get("format_version")) != FORMAT:
        add("format", found=S.get("format_version"), want=FORMAT)

    # entry details
    for f in RULES["fields"]:
        v = get(S, f["path"])
        item = {"id": f["id"], "path": shown(f["path"]), "fix": f["fix"]}
        if not known(v):
            item["message"] = "Add " + f["todo"]
            rep["blocking" if f["level"] == "block" else "suggested"].append(item)
        elif f.get("kind") == "license":
            if v not in RULES["licenses"]:
                item["message"] = f["label"] + ": " + f["bad_msg"]
                rep["blocking"].append(item)
        elif f.get("pattern") and not re.fullmatch(f["pattern"], str(v)):
            item["message"] = f["label"] + ": " + f["pattern_msg"]
            rep["blocking"].append(item)
    if not known(get(S, "contributor.name")):
        add("depositor-name")
    if not known(get(S, "dataset.name")):
        add("dataset-name")

    # structure
    ids = [m.get("id") for m in models] + [t.get("id") for t in trials]
    dup = sorted({str(i) for i in ids if ids.count(i) > 1})
    if dup:
        add("duplicate-id", n=len(dup), ids=", ".join(dup[:5]))
    mids, tids = {m.get("id") for m in models}, {t.get("id") for t in trials}
    n = sum(1 for t in trials if t.get("model") not in mids)
    if n:
        add("dangling-model", n=n)
    n = sum(1 for t in trials if known(t.get("parent_trial")) and t["parent_trial"] not in tids)
    if n:
        add("dangling-parent", n=n)
    recipes, implied = recipes_of(S)
    n = sum(1 for t in trials if known(t.get("recipe")) and t["recipe"] not in recipes)
    if n:
        add("dangling-recipe", n=n)
    res = lambda t: t.get("result") if isinstance(t.get("result"), dict) else {}
    scored = [t for t in trials if isinstance(res(t).get("score"), (int, float)) and not isinstance(res(t).get("score"), bool)]
    if not scored:
        add("no-scored")
    n = sum(1 for t in trials if res(t).get("status") == "done" and t not in scored)
    if n:
        add("done-no-score", n=n)
    n = sum(1 for t in trials if res(t).get("status") not in RULES["statuses"])
    if n:
        add("bad-status", n=n, allowed=", ".join(RULES["statuses"]))
    lin0 = S.get("lineages") if isinstance(S.get("lineages"), dict) else {}
    sp_ok = lambda sp: isinstance(sp, dict) and ((known(sp.get("trial")) and sp["trial"] in tids) or (known(sp.get("lineage")) and (sp["lineage"] in lin0 or any(t.get("lineage") == sp["lineage"] for t in trials))))
    n = sum(1 for t in trials if known(t.get("second_parent")) and not sp_ok(t["second_parent"]))
    if n:
        add("dangling-second-parent", n=n)
    n = sum(1 for m in models if known(m.get("parent")) and m["parent"] not in mids)
    if n:
        add("dangling-model-parent", n=n)
    if lin0:
        n = sum(1 for t in trials if known(t.get("lineage")) and t["lineage"] not in lin0)
        if n:
            add("dangling-lineage", n=n)

    # worth adding: enough to rebuild the model and to compare performance
    done_t = [t for t in trials if res(t).get("status") == "done"]
    done_models = {t.get("model") for t in done_t}
    has_speed = lambda m: known(get(m, "inference_speed.seq_per_s"))
    n_code = sum(1 for m in models if known(get(m, "custom_ops.model_source.reference_implementation")))
    if len(models) - n_code:
        add("model-source", n=len(models) - n_code)
    n_par = sum(1 for t in done_t if not known(res(t).get("parameters")))
    if n_par:
        add("parameters", n=n_par)
    n_time = sum(1 for t in done_t if not known(res(t).get("runtime_minutes")))
    if n_time:
        add("runtime", n=n_time)
    n_met = sum(1 for t in done_t if not (has_known(res(t).get("valid")) or has_known(res(t).get("test"))))
    if n_met:
        add("metrics", n=n_met)
    n_seed = sum(1 for t in done_t if not known(t.get("seed")))
    if n_seed:
        add("seed", n=n_seed)
    has_env = has_known(S.get("environment"))
    if not has_env:
        add("environment")
    sp = get(S, "dataset.splits")
    has_split = isinstance(sp, dict) and (known(sp.get("code")) or has_known(sp.get("files")))
    if not has_split:
        add("data-split")
    hw_train, hw_speed = known(D_(get(S, "evaluation.training_context")).get("device")), known(D_(get(S, "evaluation.speed_context")).get("device"))
    if not hw_train:
        add("training-context")
    n_speed = sum(1 for m in models if m.get("id") in done_models and not has_speed(m))
    any_speed = any(has_speed(m) for m in models)
    if not any_speed:
        add("speed")
    elif n_speed:
        add("speed-some", n=n_speed)
    if any_speed and not hw_speed:
        add("speed-context")
    if not any(known(m.get("layers")) for m in models):
        add("layers")
    lin = S.get("lineages") if isinstance(S.get("lineages"), dict) else {}
    two = lambda t: known(t.get("second_parent")) or len((lin.get(t.get("lineage")) or {}).get("parents") or []) > 1
    if any(is_crossover(t) and not two(t) for t in trials):
        add("crossover")

    # can each run be rebuilt?
    rr = {}
    for rid, rec in recipes.items():
        mine = [t for t in trials if (recipe_id(t, recipes) == rid)]
        rec = rec if isinstance(rec, dict) else {}
        miss = recipe_missing(rec, mine)
        level = rebuild_level(rec, miss)
        rr[rid] = {"runs": len(mine), "implied_from_training_defaults": implied, "level": level, "level_means": RULES["levels"][level],
                   "training_code_stored": has_code(rec), "missing": miss}
        if miss and mine:
            add("recipe", recipe=rid, runs=len(mine), n=len(miss))
        if mine and not has_code(rec):
            add("recipe-source", recipe=rid, runs=len(mine))
    rep["sufficient"] = {
        "experiment": {"ok": known(get(S, "contributor.name")) and known(get(S, "dataset.name")) and has_split and has_env,
                       "data_split_shared": has_split, "software_versions": has_env},
        "model": {"ok": bool(models) and n_code == len(models), "models": len(models), "with_code": n_code},
        "training": {"ok": bool(rr) and not n_seed and all(r["level"] != "partial" for r in rr.values() if r["runs"]), "runs_missing_seed": n_seed, "recipes": {k: r["level"] for k, r in rr.items() if r["runs"]}},
        "performance": {"ok": bool(done_t) and not (n_par or n_time or n_met or n_speed) and hw_train and hw_speed, "finished_runs": len(done_t), "missing_parameters": n_par,
                        "missing_training_time": n_time, "missing_metrics": n_met, "models_missing_speed": n_speed, "training_hardware": hw_train, "speed_hardware": hw_speed}}
    miss_parts = [k for k in ("experiment", "model", "training") if not rep["sufficient"][k]["ok"]]
    tag = "reproducible" if not miss_parts else ("results-only" if n_code == 0 else "partial")
    rep["reproducibility"] = {"tag": tag, "label": RULES["tags"][tag]["label"], "missing": miss_parts}
    rep["reproduce"] = {"models": {"total": len(models), "with_source": sum(1 for m in models if known(get(m, "custom_ops.model_source.reference_implementation"))),
                                   "with_layers": sum(1 for m in models if known(m.get("layers")))}, "recipes": rr}
    nd = sum(1 for t in trials if res(t).get("diverged"))
    if nd:
        rep["checked"].append("%d run%s a metric recorded as diverged" % (nd, " has" if nd == 1 else "s have"))
    rep["checked"].append("%d runs, %d models, %d with a score" % (len(trials), len(models), len(scored)))
    rep["ok"] = not rep["blocking"]
    return rep


def cmd_check(a):
    rep = check_text(read(a.file))
    if a.json:
        print(json.dumps(rep, indent=1, ensure_ascii=False))
    else:
        for title, key, mark in (("Needed before publishing", "blocking", "!"), ("Worth adding", "suggested", "+")):
            print("%s: %d" % (title, len(rep[key])))
            for it in rep[key]:
                print("  %s %s%s\n      fix: %s" % (mark, it["message"], ("  [" + it["path"] + "]") if "path" in it else "", it["fix"].replace("FILE", a.file)))
        su = rep.get("sufficient")
        if su:
            print("Sufficient? " + " · ".join("%s: %s" % (k, "yes" if su[k]["ok"] else "no") for k in ("experiment", "model", "training", "performance")))
            rp = rep["reproducibility"]
            print("Tag: %s%s" % (rp["label"], (" (missing: %s)" % ", ".join(rp["missing"])) if rp["missing"] else ""))
        mo = rep["reproduce"].get("models")
        if mo:
            print("Rebuild: %d of %d models have their code stored." % (mo["with_source"], mo["total"]))
        for rid, r in (rep["reproduce"].get("recipes") or {}).items():
            print("Rebuild: recipe \"%s\" (%d runs) is %s. %s" % (rid, r["runs"], r["level"], r["level_means"]))
            for m in r["missing"]:
                print("  - missing: %s\n      fix: %s" % (m["message"], m["fix"]))
        for c in rep["checked"]:
            print("ok: " + c)
        print("RESULT: " + ("ready to stage. Nothing blocks publishing. (This checks the file's form and what is missing, not whether its values are right.)" if rep["ok"] else "not ready. Fix the items marked ! and run check again."))
    return 0 if rep["ok"] else 1


# ----------------------------------------------------------------------------- fix
def cmd_fix(a):
    text, out, done = read(a.file), a.output or a.file, []
    MARK = "__cameo_nonfinite__"
    S = to_internal(json.loads(text, parse_constant=lambda c: MARK))
    n = 0
    for t in S.get("trials") or []:
        r = t.get("result")
        if not isinstance(r, dict):
            continue
        div = list(r.get("diverged") or [])
        for split in ("valid", "test"):
            for k, v in list((r.get(split) or {}).items()):
                if v == MARK:
                    r[split][k] = None; n += 1
                    if split + "." + k not in div:
                        div.append(split + "." + k)
        if r.get("score") == MARK:
            r["score"] = None; n += 1; div.append("score")
        if div:
            r["diverged"] = div

    def scrub(o):   # any other non-finite number becomes null
        nonlocal n
        if isinstance(o, dict):
            for k, v in o.items():
                if v == MARK:
                    o[k] = None; n += 1
                else:
                    scrub(v)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                if v == MARK:
                    o[i] = None; n += 1
                else:
                    scrub(v)
    scrub(S)
    if n:
        done.append("%d non-finite number(s) set to null and recorded under performance.diverged" % n)
    if a.profile:
        P = json.loads(read(a.profile))
        for src, dst in (("name", "contributor.name"), ("orcid", "contributor.orcid"), ("lab", "contributor.lab"), ("institution", "contributor.institution"),
                         ("contact", "contributor.contact"), ("license", "study.license")):
            if known(P.get(src)) and not known(get(S, dst)):
                put(S, dst, P[src]); done.append("%s taken from the depositor profile" % shown(dst))
    if isinstance(S.get("study"), dict) and not known(S["study"].get("license")):
        S["study"]["license"] = RULES["license_default"]; done.append("experiment.license set to the default, %s. The depositor can change it." % RULES["license_default"])
    if str(S.get("format_version")) != FORMAT:
        S["format_version"] = FORMAT; done.append("format_version set to " + FORMAT)
    write(S, out)
    print("\n".join("fixed: " + d for d in done) if done else "nothing to fix")
    print("wrote " + out)
    return 0


# ----------------------------------------------------------------------------- init
def cmd_init(a):
    nr = "not_reported"
    S = {
        "format_version": FORMAT,
        "study": {"id": nr, "title": nr, "question": nr, "license": RULES["license_default"], "created": time.strftime("%Y-%m-%d"), "code_url": nr, "publication": nr, "notes": []},
        "contributor": {"name": nr, "orcid": nr, "lab": nr, "institution": nr, "contact": nr, "run_by": {"kind": nr, "tool": nr, "model": nr, "supervised_by": nr}},
        "objective": {"goal": nr, "kind": nr, "optimize": {"metric": nr, "split": nr, "direction": "minimize"}},
        "dataset": {"name": nr, "accession": nr, "input": nr, "output": nr, "examples": {"train": None, "valid": None, "test": None}, "splits": {"how": nr, "code": nr}, "preprocessing": nr},
        "evaluation": {"primary_metric": nr, "direction": "minimize", "selection_split": nr, "other_metrics": [], "test_policy": nr, "seeds": [], "noise_floor": None, "noise_floor_method": nr,
                       "training_context": {"device": nr, "count": nr, "precision": nr}},
        "environment": {"python": nr, "framework": nr, "packages": {}},
        "search": {"method": nr, "budget": {}, "training_space": nr},
        "recipes": {"base": {
            "name": nr, "settings": {},
            "loss": {"kind": nr, "terms": [], "reduction": nr},
            "schedules": {}, "early_stopping": nr, "checkpoint": nr, "shuffle": nr, "augmentation": nr, "init": nr, "definitions": {},
            "source": {"entry_point": nr, "command": nr, "code": nr}}},
        "lineages": {},
        "models": [{"id": "model-1", "name": nr, "family": nr, "parent": None, "hypothesis": nr,
                    "inputs": {"x": {"kind": nr, "shape": nr}}, "outputs": {"y": {"kind": nr}},
                    "custom_ops": {"model_source": {"description": nr, "reference_implementation": nr}}}],
        "trials": [{"id": "trial-001", "model": "model-1", "recipe": "base", "training": {}, "seed": None, "lineage": nr, "parent_trial": None,
                    "move": nr, "hypothesis": nr, "predicted_effect": nr,
                    "result": {"status": nr, "score": None, "valid": {}, "test": {}, "best_epoch": None, "epochs_run": None, "parameters": None, "runtime_minutes": None}, "notes": []}],
        "summary": {"findings": [], "open_questions": []},
    }
    if a.profile:
        P = json.loads(read(a.profile))
        for src, dst in (("name", "contributor.name"), ("orcid", "contributor.orcid"), ("lab", "contributor.lab"), ("institution", "contributor.institution"), ("contact", "contributor.contact"), ("license", "study.license")):
            if known(P.get(src)):
                put(S, dst, P[src])
    write(S, a.output)
    print("wrote " + a.output + ". Replace the example model and trial, then run: cameo.py check " + a.output)
    return 0


# ----------------------------------------------------------------------------- PyTorch steps
PRE = "import math\nimport torch\nimport torch.nn as nn\nimport torch.nn.functional as F\n"


def need_torch():
    try:
        import torch  # noqa: F401
        return True
    except Exception:
        print("This step needs PyTorch, which is not installed here. It is a suggestion, not a requirement: skip it, or run it where the models were trained.")
        return False


def source_of(m):
    return get(m, "custom_ops.model_source.reference_implementation")


def input_shape(m, override):
    if override:
        return [int(x) for x in override.split(",")]
    s = get(m, "inputs.x.shape") or next((v.get("shape") for v in (m.get("inputs") or {}).values() if isinstance(v, dict)), None)
    if isinstance(s, list):
        return [int(x) for x in s if isinstance(x, int)]
    nums = [int(x) for x in re.findall(r"\d+", str(s or ""))]
    return nums or None


def make_input(shape, batch):
    import torch, torch.nn.functional as F
    if len(shape) == 2 and shape[0] <= 8:        # a few channels by length: treat as one-hot sequence
        return F.one_hot(torch.randint(0, shape[0], (batch, shape[1])), shape[0]).float().transpose(1, 2).contiguous()
    return torch.randn(batch, *shape)


def build_model(src):
    import torch
    pre = PRE
    try:
        import numpy  # noqa: F401
        pre += "import numpy as np\n"
    except Exception:
        pass
    ns = {}
    exec(compile(pre + src, "<model_source>", "exec"), ns)
    torch.manual_seed(0)
    net = ns["build_model"]()
    net.eval()
    return net


def describe(m):
    import torch.nn as nn
    tup = lambda v: (v[0] if len(set(v)) == 1 else "x".join(str(i) for i in v)) if isinstance(v, (tuple, list)) else v
    c = type(m).__name__
    if isinstance(m, (nn.Conv1d, nn.ConvTranspose1d, nn.Conv2d)):
        d = ["k%s" % tup(m.kernel_size)]
        if tup(m.stride) != 1: d.append("stride %s" % tup(m.stride))
        if tup(m.dilation) != 1: d.append("dilation %s" % tup(m.dilation))
        if m.groups != 1: d.append("groups %d" % m.groups)
        d.append("pad %s" % (m.padding if isinstance(m.padding, str) else tup(m.padding)))
        if m.bias is None: d.append("no bias")
        return "%d → %d" % (m.in_channels, m.out_channels), ", ".join(d), "weights"
    if isinstance(m, nn.Linear):
        return "%d → %d" % (m.in_features, m.out_features), "" if m.bias is not None else "no bias", "weights"
    if isinstance(m, (nn.BatchNorm1d, nn.BatchNorm2d)):
        return "%d" % m.num_features, "eps %g, mom %g" % (m.eps, m.momentum if m.momentum is not None else float("nan")), "norm"
    if isinstance(m, nn.LayerNorm):
        return "%s" % tup(list(m.normalized_shape)), "eps %g" % m.eps, "norm"
    if isinstance(m, nn.GroupNorm):
        return "%d groups of %d" % (m.num_groups, m.num_channels), "eps %g" % m.eps, "norm"
    if isinstance(m, (nn.Dropout, nn.Dropout1d, nn.Dropout2d)):
        return "p %g" % m.p, "", "light"
    if isinstance(m, (nn.MaxPool1d, nn.AvgPool1d)):
        return "window %s" % tup(m.kernel_size), ("stride %s" % tup(m.stride)) if tup(m.stride) != tup(m.kernel_size) else "", "shape"
    if isinstance(m, (nn.AdaptiveAvgPool1d, nn.AdaptiveMaxPool1d)):
        return "to length %s" % tup(m.output_size), "", "shape"
    if isinstance(m, (nn.GRU, nn.LSTM, nn.RNN)):
        d = ["%d layer%s" % (m.num_layers, "s" if m.num_layers > 1 else "")] + (["bidirectional"] if m.bidirectional else [])
        return "%d → %d" % (m.input_size, m.hidden_size), ", ".join(d), "weights"
    if isinstance(m, nn.MultiheadAttention):
        return "dim %d" % m.embed_dim, "%d heads" % m.num_heads, "weights"
    if isinstance(m, nn.Embedding):
        return "%d × %d" % (m.num_embeddings, m.embedding_dim), "", "weights"
    if isinstance(m, (nn.Flatten, nn.Unflatten)):
        return "", "", "shape"
    if c in ("ReLU", "GELU", "SiLU", "Sigmoid", "Tanh", "Softplus", "ELU", "LeakyReLU", "Mish", "Identity", "Softmax", "PReLU"):
        return "", "", "light"
    r = m.extra_repr()
    return "", (r[:70] + "…") if len(r) > 70 else r, "custom"


def trace(net, x):
    """Layer list from one forward pass: order, output shapes, parameter counts; repeated blocks stored once."""
    import torch
    names, calls, counter = {m: n for n, m in net.named_modules()}, {}, [0]

    def shape_of(o):
        if isinstance(o, torch.Tensor):
            return list(o.shape[1:])
        if isinstance(o, (tuple, list)):
            for i in o:
                s = shape_of(i)
                if s is not None:
                    return s
        return None

    def hook(mod, inp, out):
        n = names.get(mod)
        if n is None:
            return
        rec = calls.setdefault(n, {"order": counter[0], "n": 0, "out": None})
        rec["n"] += 1; rec["out"] = shape_of(out); counter[0] += 1

    hs = [m.register_forward_hook(hook) for m in net.modules()]
    with torch.no_grad():
        y = net(x)
    for h in hs:
        h.remove()

    def node(name, mod):
        label, detail, kind = describe(mod)
        kids = [node((name + "." + cn) if name else cn, cm) for cn, cm in mod.named_children()]
        rec = calls.get(name, {})
        d = {"name": name.split(".")[-1] if name else "", "cls": type(mod).__name__, "label": label, "detail": detail, "kind": "group" if kids else kind,
             "out": rec.get("out"), "calls": rec.get("n", 0), "order": rec.get("order"),
             "params": sum(p.numel() for p in mod.parameters()), "own": sum(p.numel() for p in mod.parameters(recurse=False))}
        if kids:
            d["children"] = kids
        return d

    def finalize(n):
        kids = n.get("children")
        if kids:
            for k in kids:
                finalize(k)
            called = [k for k in kids if k["order"] is not None]
            if n["order"] is None and called:
                n["order"] = min(k["order"] for k in called); n["out"] = max(called, key=lambda k: k["order"])["out"]
            kids.sort(key=lambda k: (k["order"] is None, k["order"] if k["order"] is not None else 0))
        n["used"] = n["order"] is not None

    def sig(n):
        return json.dumps([n["cls"], n["label"], n["detail"], n["out"], n["calls"], n["used"], [[sig(k), k.get("count", 1)] for k in n.get("children", [])]])

    def collapse(n):
        out = []
        for k in n.get("children") or []:
            collapse(k)
            if out and sig(out[-1]) == sig(k):
                out[-1]["count"] = out[-1].get("count", 1) + 1
            else:
                out.append(k)
        if out:
            n["children"] = out

    def strip(n):
        n.pop("order", None)
        if n.get("count", 1) == 1:
            n.pop("count", None)
        for k in n.get("children", []):
            strip(k)

    tree = node("", net)
    finalize(tree); collapse(tree); strip(tree)
    tree["out"] = shape_of(y)
    return tree, sum(p.numel() for p in net.parameters())


def cmd_add_layers(a):
    if not need_torch():
        return 0
    S, out = to_internal(json.loads(read(a.file))), a.output or a.file
    rec = {}
    for t in S["trials"]:
        p = (t.get("result") or {}).get("parameters")
        if isinstance(p, int):
            rec.setdefault(t["model"], set()).add(p)
    ok = bad = same = diff = norec = 0
    for m in S["models"]:
        src, shape = source_of(m), input_shape(m, a.input_shape)
        if not known(src) or not shape:
            bad += 1; print("skipped %s: %s" % (m.get("id"), "no source code in the file" if not known(src) else "no input shape (use --input-shape)")); continue
        try:
            tree, n = trace(build_model(src), make_input(shape, 2))
            m["layers"], m["parameters"] = tree, n; ok += 1
            if m["id"] in rec:
                if n in rec[m["id"]]: same += 1
                else: diff += 1; print("note: %s has %d parameters; its runs recorded %s" % (m["id"], n, sorted(rec[m["id"]])))
            else:
                norec += 1
        except Exception as e:
            bad += 1; print("could not build %s: %s: %s" % (m.get("id"), type(e).__name__, str(e)[:160]))
    write(S, out)
    print("layer lists added for %d of %d models; %d could not be built. Parameter counts match the runs for %d, differ for %d; %d have no recorded count to compare (their runs gave no result)." % (ok, len(S["models"]), bad, same, diff, norec))
    print("note: a layer list shows layers only. Two models that differ in steps written inside forward() (augmentation, initialisation) get the same list.")
    print("wrote " + out)
    return 0


def cmd_add_speed(a):
    if not need_torch():
        return 0
    import platform, torch
    S, out = to_internal(json.loads(read(a.file))), a.output or a.file
    dev = ("cuda" if torch.cuda.is_available() else "cpu") if a.device == "auto" else a.device
    if dev == "cuda":
        name = torch.cuda.get_device_name(0)
    else:
        name = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), platform.processor() or "CPU") if os.path.exists("/proc/cpuinfo") else (platform.processor() or "CPU")
    ok = bad = 0
    for m in S["models"]:
        src, shape = source_of(m), input_shape(m, a.input_shape)
        if not known(src) or not shape:
            bad += 1; continue
        try:
            net, x = build_model(src).to(dev), make_input(shape, a.batch).to(dev)
            sync = (lambda: torch.cuda.synchronize()) if dev == "cuda" else (lambda: None)
            with torch.no_grad():
                net(x[:8]); net(x); sync()
                times = []
                while len(times) < 6 and (sum(times) < 1.5 or len(times) < 2):
                    t0 = time.perf_counter(); net(x); sync(); times.append(time.perf_counter() - t0)
            m["inference_speed"] = {"seq_per_s": round(a.batch / min(times), 1)}; ok += 1
        except Exception as e:
            bad += 1; print("could not time %s: %s: %s" % (m.get("id"), type(e).__name__, str(e)[:160]))
    S.setdefault("evaluation", {})["speed_context"] = {"device": name, "threads": torch.get_num_threads() if dev == "cpu" else None, "batch": a.batch, "precision": "float32",
                                                      "framework": "PyTorch " + torch.__version__, "passes": "one forward pass per example, eval mode, fastest of 2 to 6 timed passes"}
    write(S, out)
    print("inference speed measured for %d of %d models on %s (batch %d); %d skipped." % (ok, len(S["models"]), name, a.batch, bad))
    print("wrote " + out)
    return 0


# ----------------------------------------------------------------------------- export one run
def cmd_export_run(a):
    S = to_internal(json.loads(read(a.file), parse_constant=lambda c: None))
    t = next((x for x in S["trials"] if x.get("id") == a.trial), None)
    if not t:
        print("no run with id " + a.trial); return 2
    m = next((x for x in S["models"] if x.get("id") == t.get("model")), None) or {}
    recipes, implied = recipes_of(S)
    rid = recipe_id(t, recipes); rec = recipes.get(rid) or {}
    os.makedirs(a.output, exist_ok=True)
    src, w = source_of(m), lambda name, text: open(os.path.join(a.output, name), "w", encoding="utf-8").write(text)
    made = []
    if known(src):
        w("model.py", ("" if "import torch" in src else PRE + "\n\n") + src + "\n"); made.append("model.py: the model exactly as stored; build_model() returns it")
    settings = resolved(t, rec)
    origin = {k: ("this run" if k in (t.get("training") or {}) else "recipe") for k in settings}
    w("settings.json", json.dumps({"run": t.get("id"), "model": t.get("model"), "recipe": rid, "seed": t.get("seed"), "settings": settings, "set_by": origin}, indent=1) + "\n")
    made.append("settings.json: every setting the run trained with, and whether the run or the recipe set it")
    w("recipe.json", json.dumps({k: v for k, v in rec.items() if k != "source"}, indent=1, ensure_ascii=False) + "\n"); made.append("recipe.json: the training recipe (loss, schedule, stopping, checkpoint)")
    code = get(rec, "source.code")
    if known(code):
        w("train.py", code + "\n"); made.append("train.py: the training code exactly as stored")
        for name, text in (get(rec, "source.files") or {}).items():   # the loop's own modules the script imports
            if isinstance(text, str):
                w(os.path.basename(name), text + "\n"); made.append(os.path.basename(name) + ": a module the training script imports")
    miss = recipe_missing(rec, [t]); level = rebuild_level(rec, miss)
    data = S.get("dataset") or {}
    lines = ["# Rebuilding run %s" % t.get("id"), "", "Model: %s (%s)." % (m.get("name"), t.get("model")), "", "## What is here", ""] + ["- " + x for x in made] + ["",
        "## Data", "", "- Dataset: %s" % data.get("name"), "- Accession: %s" % data.get("accession"), "- Input: %s" % data.get("input"), "- Output: %s" % data.get("output"),
        "- Splits: %s" % data.get("splits"), "- Preprocessing: %s" % data.get("preprocessing"), "",
        "## Recorded result to compare against", "", "- Status: %s%s" % (get(t, "result.status"), "" if get(t, "result.status") == "done" else " (this run gave no result, so there is nothing to compare against)"),
        "- Score: %s" % get(t, "result.score"), "- Validation: %s" % json.dumps(get(t, "result.valid")), "- Test: %s" % json.dumps(get(t, "result.test")),
        "- Recorded as diverged: %s" % (", ".join(get(t, "result.diverged") or []) or "none"),
        "- Best epoch: %s of %s run" % (get(t, "result.best_epoch"), get(t, "result.epochs_run")), "- Parameters: %s" % get(t, "result.parameters"), ""]
    if not known(src):
        lines += ["## Model code is missing", "", "The file has no source code for this model, so it cannot be rebuilt from this export.", ""]
    lines += ["## How far this goes", "", "- Model: %s" % ("can be rebuilt from model.py." if known(src) else "cannot be rebuilt; its code is not in the file."),
              "- Training: %s. %s" % (level, RULES["levels"][level]), ""]
    if miss:
        lines += ["## Training details the file does not give", ""] + ["- " + x["message"] for x in miss] + ["",
                  "Do not guess these silently. If you choose a value, write down that you chose it." if level == "partial" else "train.py settles these, but they are not recorded as fields.", ""]
    w("REBUILD.md", "\n".join(lines))
    print("wrote %s: %s, REBUILD.md" % (a.output, ", ".join(x.split(":")[0] for x in made)))
    print("training: %s. %s%s" % (level, RULES["levels"][level], (" %d detail(s) missing; see REBUILD.md" % len(miss)) if miss else ""))
    return 0


# ----------------------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(prog="cameo.py", description="Prepare a study file for deposit in CAMEO.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", help="write a blank study file"); s.add_argument("-o", "--output", default="study.json"); s.add_argument("--profile"); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("check", help="what blocks publishing, what is suggested, what is missing to rebuild training"); s.add_argument("file"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("fix", help="safe automatic repairs"); s.add_argument("file"); s.add_argument("--profile"); s.add_argument("-o", "--output"); s.set_defaults(fn=cmd_fix)
    s = sub.add_parser("add-layers", help="store each model's layer list (needs PyTorch)"); s.add_argument("file"); s.add_argument("--input-shape"); s.add_argument("-o", "--output"); s.set_defaults(fn=cmd_add_layers)
    s = sub.add_parser("add-speed", help="measure inference speed (needs PyTorch)"); s.add_argument("file"); s.add_argument("--batch", type=int, default=64)
    s.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"]); s.add_argument("--input-shape"); s.add_argument("-o", "--output"); s.set_defaults(fn=cmd_add_speed)
    s = sub.add_parser("export-run", help="write one run's model, settings and recipe to a folder"); s.add_argument("file"); s.add_argument("trial"); s.add_argument("-o", "--output", default="rebuild"); s.set_defaults(fn=cmd_export_run)
    a = p.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
