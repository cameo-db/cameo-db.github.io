# CAMEO entry format: instructions for a model-search loop

Send this file to any loop that trains models: an architecture search, a tuning sweep, a benchmark run. It says what the loop must write so that its results can be entered into CAMEO, a public database of models, how they were trained, and how they performed.

The loop writes one file per experiment, `study.json`. It has four parts.

| Part | Holds | How many |
|---|---|---|
| `experiment` | what was studied, by whom, on what data, in what environment | one |
| `models` | each architecture: its code, and its inference speed | one per architecture |
| `training` | each training recipe: settings, loss, schedule, script | one per distinct procedure |
| `runs` | each training run: which model, which recipe, which seed, where the run came from, and its performance | one per run |

A run is the link. It names a model and a recipe by id, and its performance sits inside it, because a score belongs to one model trained one way with one seed.

The file is complete when a reader can rebuild each model, train it the same way, and compare its results with other studies, from the file alone. Datasets and trained weights stay outside the file.

A partial file is still accepted. CAMEO works out a tag from the file itself: Reproducible, Partly reproducible, or Results only. Write what you have, and never fill a gap with a guess.

## Record as you go

These cannot be recovered afterwards. Capture them when each run happens.

- The model file and the training script, exactly as run, as text.
- The settings the run resolved to, and its seed.
- The parent run or runs, and why the run was tried.
- Metrics, parameter count and wall-clock training time.
- Failed runs too. One entry per run, with its status.

## `experiment`

| Field | Holds |
|---|---|
| `id`, `title`, `summary` | a short slug, a title, one or two sentences |
| `license`, `created`, `code_url`, `publication` | `MIT` unless the depositor chose another; the date; links |
| `depositor` | `name`, `orcid`, `lab`, `institution`, `contact` |
| `run_by` | who or what ran it: `kind`, `tool`, `model` |
| `objective` | `goal`, and `optimize`: `{metric, split, direction}` |
| `data` | `name`, `accession`, `input`, `output`, `examples` (train, valid, test counts), `preprocessing`, `splits` |
| `data.splits` | `how` the split was made, plus the `code` that builds it or the split `files` (name → `{url, sha256}`) |
| `evaluation` | `primary_metric`, `direction`, `selection_split`, `test_policy`, `noise_floor`, and `metrics`: name → how it is computed |
| `environment` | `python`, `framework`, `packages` (name → version), `training_hardware`, `inference_hardware` |
| `search` | `method`, `budget`, and `lineages`: lines of work by id, each with `name`, `family`, `parents` |
| `conclusions` | `best_run`, `findings`, `open_questions` |

## `models[]`

| Field | Holds |
|---|---|
| `id`, `name`, `family` | a stable id, a short name, the kind of model |
| `parent` | the model it was derived from, or `null` |
| `inputs`, `outputs` | name → `{kind, shape}` |
| `code` | the whole model file as text. It defines `build_model()`, which returns the network |
| `inference_speed` | `{"seq_per_s": n}`: examples per second. See Performance |
| `layers` | optional layer list, for drawing the model |

## `training{}`

One recipe per id. A recipe is everything about training that is not a per-run setting. Runs that differ only in settings share one. A different loss, script or stopping rule is a different recipe. If the loop edits its training script, each distinct script is its own recipe.

| Field | Holds |
|---|---|
| `settings` | defaults for `optimizer`, `lr`, `batch_size`, `epochs` and any others |
| `loss` | `kind`, `terms` (`[{output, weight}]`), `reduction` |
| `schedules` | name → parameters, for each schedule a run can select |
| `early_stopping` | `{metric, split, patience}`, or `false` |
| `checkpoint` | `best_validation` or `last`: which weights were scored |
| `shuffle` | `true` or `false` |
| `augmentation` | a list of steps with parameters, or `"none"` |
| `init` | `"random"`, or where the starting weights came from |
| `definitions` | what any non-obvious switch does |
| `code` | `entry_point`, `command`, `script` (the training script as text), and `files` (name → text) for any of the loop's own modules the script imports |

Take these values from the objects the script built (optimizer, scheduler, loader, loss), not from a description typed beside it. When a value is a per-run setting, name the setting: `{"output": "y", "weight_setting": "y_weight"}` or `"patience_setting": "patience"`.

## `runs[]`

| Field | Holds |
|---|---|
| `id`, `model`, `training`, `seed` | a stable id, a model id, a recipe id, the seed |
| `settings` | only the settings this run set differently from its recipe |
| `history` | `lineage`, `parent` (a run id or `null`), `second_parent` for a crossover (`{"run": id}` or `{"lineage": id}`), `move`, `hypothesis`, `predicted_effect` |
| `performance` | see below |

`move` is `baseline`, `settings_move`, `structural_change`, `new_approach`, `composition`, or the loop's own word.

### Performance

| Field | Holds |
|---|---|
| `status` | `done`, `failed`, `invalid`, `stopped_early` or `not_run` |
| `score` | the number the experiment optimised |
| `valid`, `test` | metric name → value |
| `diverged` | metrics that were infinite or not a number, such as `["test.mse"]`. Their value is `null` |
| `parameters` | trainable parameter count |
| `training_minutes` | wall-clock minutes from the start of training to its end, validation passes included |
| `best_epoch`, `epochs_run` | the epoch that was scored; how many ran |

Training time and inference speed depend on the hardware, so each is recorded with its device: the GPU or CPU model, such as `NVIDIA A100`.

- `experiment.environment.training_hardware`: `{device, count, precision}`.
- `models[].inference_speed.seq_per_s`: a forward pass in evaluation mode, without gradients, at a fixed batch size, after a warm-up, taking the fastest of several timed passes.
- `experiment.environment.inference_hardware`: `{device, threads, batch, precision}` for that measurement.
- If a run trained on different hardware from the rest, give it its own under `performance.hardware`.

## Rules

- Never invent a value. Write `"not_reported"` for what the loop does not know.
- Numbers are numbers. `Infinity` and `NaN` are not allowed: write `null` and list the metric in `diverged`.
- Keep ids stable. Never renumber.
- `format_version` is `"0.3"`.

## Example

Copy the shape. Never copy the values.

```json
{
 "format_version": "0.3",
 "experiment": {
  "id": "study-example", "title": "Example: one small CNN", "license": "MIT", "created": "2026-01-01",
  "summary": "Shows the shape of a sufficient file. Nothing here is real.",
  "depositor": {"name": "Example Depositor"},
  "run_by": {"kind": "agent", "tool": "example-loop"},
  "objective": {"goal": "Lowest validation MSE.", "optimize": {"metric": "mse", "split": "valid", "direction": "minimize"}},
  "data": {"name": "Example sequences", "accession": "not_reported", "input": "100 bp DNA, one-hot (4, 100)",
           "output": "one activity value", "examples": {"train": 1000, "valid": 200, "test": 200}, "preprocessing": "one-hot A,C,G,T",
           "splits": {"how": "random, seed 0", "code": "<the code that builds the split, as text>"}},
  "evaluation": {"primary_metric": "mse", "direction": "minimize", "selection_split": "valid",
                 "metrics": {"mse": "mean squared error over examples", "pearson": "Pearson r over examples"}},
  "environment": {"python": "3.11", "framework": "PyTorch 2.4", "packages": {"numpy": "1.26"},
                  "training_hardware": {"device": "NVIDIA A100", "count": 1, "precision": "fp32"},
                  "inference_hardware": {"device": "NVIDIA A100", "batch": 64, "precision": "fp32"}},
  "conclusions": {"best_run": "run-001", "findings": [], "open_questions": []}
 },
 "models": [{
  "id": "model-1", "name": "small_cnn", "family": "cnn", "parent": null,
  "inputs": {"x": {"kind": "one-hot DNA", "shape": [4, 100]}}, "outputs": {"y": {"kind": "activity"}},
  "code": "<the model file, as text; it defines build_model()>",
  "inference_speed": {"seq_per_s": 5000.0}}],
 "training": {"base": {
  "name": "Adam with early stopping",
  "settings": {"optimizer": "adam", "lr": 0.001, "batch_size": 64, "epochs": 20, "patience": 3, "schedule": "constant"},
  "loss": {"kind": "mse", "terms": [{"output": "y", "weight": 1.0}], "reduction": "mean over examples"},
  "early_stopping": {"metric": "mse", "split": "valid", "patience_setting": "patience"},
  "checkpoint": "best_validation", "shuffle": true, "augmentation": "none", "init": "random",
  "code": {"entry_point": "train", "command": "python train.py", "script": "<the training script, as text>"}}},
 "runs": [{
  "id": "run-001", "model": "model-1", "training": "base", "seed": 0, "settings": {"lr": 0.002},
  "history": {"lineage": "L1", "parent": null, "move": "baseline", "hypothesis": "A starting point."},
  "performance": {"status": "done", "score": 0.52, "valid": {"mse": 0.52, "pearson": 0.71},
                  "test": {"mse": 0.55, "pearson": 0.69}, "best_epoch": 9, "epochs_run": 12,
                  "parameters": 12345, "training_minutes": 1.4}}]
}
```

## Check your output

Before you hand the file over, confirm each of these.

- It is valid JSON with the four parts.
- Every model has its `code`.
- Every run names a model and a recipe that exist, and has a `seed`.
- Every recipe has its `script`, and the fields above are filled.
- Every finished run has `score`, metrics, `parameters` and `training_minutes`.
- Every model with a finished run has `inference_speed`.
- `environment` has versions, and the device for training and for inference. `data.splits` has code or files.

If you have the CAMEO kit, it checks all of this:

```
python3 cameo.py check study.json
```

A complete file gives these two lines. Add `--json` to get every gap with a `fix`. A file with a "no" is still accepted, and is tagged partly reproducible.

```
Sufficient? experiment: yes · model: yes · training: yes · performance: yes
RESULT: ready to stage.
```

Then prove it once. Take one run, train it again from the file alone (its model `code`, its recipe's `script`, its settings, the same data and seed), and compare with the recorded score. They should agree within the noise floor. Record the result under `experiment.evaluation.rebuild_test`: `{run, recorded_score, rebuilt_score}`.

## Not PyTorch?

Everything above applies. Store the model and training code in your framework and name it under `environment.framework`.
