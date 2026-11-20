# CAMEO

A public catalog of machine-learning experiments: models, how they were trained, and how they performed.

- `studies/` is the database: one JSON file per study.
- `benchmarks.json` lists the benchmarks. A benchmark is a dataset, a test set and a metric.
- `site/` holds the page. `tools/build_site.py` builds the site from the study files.
- `kit/` holds the instructions for training loops and agents (`CAMEO_LOOP_SPEC.md`) and the checker (`cameo.py`).
- `site.json` holds the site's address, its label and, once it has one, its DOI.

## Add a study

1. Give `kit/CAMEO_LOOP_SPEC.md` to your training loop or agent. It writes `study.json`.
2. Run `python3 kit/cameo.py check study.json` and fix what it says is needed.
3. Open a pull request that adds the file to `studies/`, named `<experiment id>.json`.

The check runs on the pull request. Once it is merged, the site rebuilds itself.

A study can also list results reported in a paper, as runs with `"kind": "reported"` and a link to the source. The site marks them Reported.

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
- `kit/`: the instructions file, the checker, an example entry, and all of them as `cameo-agent-kit.zip`.
- `llms.txt`: a short list of the above, for agents.

## Give the catalog a DOI

Zenodo archives each GitHub release and gives it a DOI. This is set up once.

1. Sign in at zenodo.org with the GitHub account that administers this organization.
2. On Zenodo, open the profile menu, choose GitHub, and press Sync now. Switch on this repository.
   If it is not listed, GitHub has not let Zenodo see the organization. On GitHub, open Settings, Applications, Authorized OAuth Apps, Zenodo, and grant access to the organization. Then press Sync now again.
3. On GitHub, create a release. Zenodo archives it and gives it a DOI.
4. Zenodo shows two DOIs: one for this release, and one that always points to the newest. Put the second in `site.json` as `"doi"`, and add it to `CITATION.cff` as `doi:`.

Make a new release whenever you want a citable snapshot, for example after a batch of new studies. `CITATION.cff` supplies the title and authors, so edit the authors there first.

## Licenses

The code and the site are under the MIT license. Each study file carries its own open license, under `experiment.license`.
