# CAMEO

A public catalog of models, how they were trained, and how they performed.

- `studies/` is the database: one JSON file per study.
- `benchmarks.json` lists the benchmarks. A benchmark is a dataset, a test set and a metric.
- `site/` holds the pages. `tools/build_site.py` builds the site from the study files.
- `kit/` holds the format (`CAMEO_LOOP_SPEC.md`) and the checker (`cameo.py`).

## Add a study

1. Write `study.json` as `kit/CAMEO_LOOP_SPEC.md` describes.
2. Run `python3 kit/cameo.py check study.json` and fix what it says is needed.
3. Open a pull request that adds the file to `studies/`, named `<experiment id>.json`.

The check runs on the pull request. Once it is merged, the site rebuilds itself.

## Build the site on your own machine

    python3 tools/build_site.py _site
    cd _site && python3 -m http.server 8000

Then open http://localhost:8000.
