# Depositing a study in CAMEO: instructions for an agent

You are preparing one file, `study.json`, from a project that has already been run. A person will open it in the CAMEO site, review it and publish it. You do not publish.

The format is in `CAMEO_LOOP_SPEC.md`. Read it first. This file is the procedure.

## The loop

1. `python3 cameo.py init --profile depositor.json -o study.json`
2. Fill the file from the project's files. See "Where values come from".
3. `python3 cameo.py check study.json --json`
4. Fix every item under `blocking`. Each has a `fix` that says what to do. Run `check` again until `"ok": true`.
5. `python3 cameo.py fix study.json --profile depositor.json` applies the repairs that are safe to automate.
6. `python3 cameo.py add-layers study.json` if PyTorch is installed. It builds each model and stores its layer list.
7. `python3 cameo.py add-speed study.json` only on the machine whose speed the depositor wants reported. Otherwise skip it and say so.
8. Work down `suggested` and `reproduce.recipes.<id>.missing` as far as the project's files allow.
9. Tell the person what you filled, and what you left as `not_reported` and why.

`check` looks at the file's form and at what is missing. It cannot tell whether a value is right, so compare a few scores and settings against their source files yourself.

## Rules

- **Never invent.** If the files do not say, write `"not_reported"`. A gap is fine. A guess is not.
- A value counts as stated only if a file in the project states it. What the framework does by default, or what is usual, does not count.
- You may write `experiment.title`, `experiment.summary` and model names yourself. They are descriptions, not facts.
- License: use the one in `depositor.json`. If it names none, keep the default, MIT, and say so in your report. Pick no other yourself.
- Record what each run actually used. Take settings from the run's own config or log.
- One entry per training run, including runs that failed.
- A number the project quotes from a paper is a `reported` run with its source. Never enter it as a run the project made.
- Keep the project's ids if it has them.

## Where values come from

| Value | Look in |
|---|---|
| Depositor name, ORCID, lab, contact, license | `depositor.json`. Do not search elsewhere for these |
| Dataset, splits, metric, how models were chosen | The project README, the task description, the data-loading code |
| Software versions, hardware | A lock file, an environment file, the run logs |
| Model code | Each run's model file |
| Settings a run trained with | That run's config or log |
| Loss, schedule, stopping rule, checkpoint, shuffling, augmentation, starting weights | The training script first. Otherwise any file that states them. Otherwise `not_reported` |
| Scores, parameter count, training time | Each run's result file. Copy every digit |
| Baselines quoted from papers | The project's write-up, with the paper it cites. Copy the number as the paper states it |
| Parents, lines of work, crossovers | The search log |
| Ideas and predictions behind a run | The search log or proposal notes |

## What done looks like

- `python3 cameo.py check study.json` ends with `RESULT: ready to stage`, and its `Sufficient?` line says yes wherever the project's files allow.
- Every `suggested` item is either done or named in your report with the reason it could not be done.
- A spot check passes: `python3 cameo.py export-run study.json <a run id> -o rebuild` writes the model code, the settings and the recipe, and `rebuild/REBUILD.md` lists only gaps the project's files truly leave open.

Then hand `study.json` to the person. They drop it on the CAMEO site, see it staged, and publish.
