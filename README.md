# CAMEO

A public database of the models that studies train: what each model was, how it was trained, and how it performed.

A paper usually reports one model. The study behind it often trained hundreds, and those models are then lost. CAMEO keeps them, so that they can be compared across studies, downloaded, and used to start new searches.

- `studies/` is the database: one JSON file per study.
- `benchmarks.json` lists the benchmarks. A benchmark is a dataset, a split to score on and a metric.
- `site/` holds the page. `tools/build_site.py` builds the site from the study files.
- `kit/` holds the instructions for training loops and agents (`CAMEO_LOOP_SPEC.md`) and the checker (`cameo.py`).
- `site.json` holds the site's address, its label, who maintains it and where to write to them, and, once it has one, its DOI.

## Add a study

1. Give `kit/CAMEO_LOOP_SPEC.md` to your training loop or agent. It writes `study.json`.
2. Run `python3 kit/cameo.py check study.json` and fix what it says is needed.
3. Open a pull request that adds the file to `studies/`, named `<experiment id>.json`.

The check runs on the pull request. Once it is merged, the site rebuilds itself.

Include baselines when the study has them. The run a search started from has `history.move` set to `"baseline"`. A result reported in a paper is a run with `"kind": "reported"` and a link to the source; the site marks it Reported.

`python3 kit/cameo.py add-layers study.json` builds each model from its code and stores its layer list and which layer feeds which. The site draws the model from these. It needs PyTorch. If the model code reads a value that the training script set, pass it with `--define NAME=VALUE`, for example `--define IN_LEN=2114`. If the entry does not give the input shape, pass `--input-shape 4,600`.

## Add a benchmark

A study joins a benchmark when its dataset name contains the benchmark's `match` text. To add one, add an entry to `benchmarks.json`:

- `metric` and `split` say what the leaderboard ranks on. The value is read from each run's `performance.<split>.<metric>`.
- `metric_aliases` lists other names that studies used for the same quantity.
- `note` is one line shown under the description. Use it when the ranking is on validation data.

## Build the site on your own machine

    python3 tools/build_site.py _site
    cd _site && python3 -m http.server 8000

Then open http://localhost:8000.

## What the build writes

Everything the site shows is also a plain file that anyone, or any agent, can read:

- `index.json`: every study, benchmark and depositor.
- `boards/<benchmark>.json`: one leaderboard, and how each study on it prepared the data.
- `models.json`: every model on every leaderboard.
- `studies/<id>.json`: one whole entry.
- `cameo-all.json`: every entry in one file, as `{"studies": [...]}`. It is left out once it would pass 90 MB, because GitHub refuses files over 100 MB; the site then merges the study files in the browser.
- `kit/`: the instructions file, the checker, an example entry, and all of them as `cameo-agent-kit.zip`.
- `llms.txt`: a short list of the above, for agents.

## Give the database a DOI

Zenodo archives each GitHub release and gives it a DOI. This is set up once.

1. Sign in at zenodo.org with the GitHub account that administers this organization.
2. On Zenodo, open the profile menu, choose GitHub, and press Sync now. Switch on this repository.
   If it is not listed, GitHub has not let Zenodo see the organization. On GitHub, open Settings, Applications, Authorized OAuth Apps, Zenodo, and grant access to the organization. Then press Sync now again.
3. On GitHub, create a release. Zenodo archives it and gives it a DOI.
4. Zenodo shows two DOIs: one for this release, and one that always points to the newest. Put the second in `site.json` as `"doi"`, and add it to `CITATION.cff` as `doi:`.

Make a new release whenever you want a citable snapshot, for example after a batch of new studies. `CITATION.cff` supplies the title and authors. It names "CAMEO contributors" as the author, and each study is credited to its depositor on the site.

## Licenses

The code and the site are under the MIT license. Each study file carries its own open license, under `experiment.license`.
