# CAMEO entry format: instructions for a model-search loop

Send this file to any loop that trains models, in any field: an architecture search, a tuning sweep, a benchmark run. It says what the loop must write so that its results can be entered into CAMEO, a public database of models, how they were trained, and how they performed.

The loop writes one file per experiment, `study.json`. It has four parts.

| Part | Holds | How many |
|---|---|---|
| `experiment` | what was studied, by whom, on what data, in what environment | one |
| `models` | each architecture: its code, and its inference speed | one per architecture |
| `training` | each training recipe: settings, loss, schedule, script | one per distinct procedure |
| `runs` | each training run: which model, which recipe, which seed, where the run came from, and its performance | one per run |

A run is the link. It names a model and a recipe by id, and its performance sits inside it, because a score belongs to one model trained one way with one seed.

The file is complete when a reader can rebuild each model, train it the same way, and compare its results with other studies, from the file alone. Datasets and trained weights stay outside the file. The file links to them.

A partial file is still accepted. CAMEO gives each entry a star, worked out from the file itself:

- **Gold**: all four parts are complete.
- **Silver**: model code, a link to the dataset, and for every run its training settings and seed, or a link to the weights it scored.
- **Bronze**: model code, results and a link to the dataset.
- **No star**: no link to the dataset, no model code, or only results reported elsewhere.

Write what you have, and never fill a gap with a guess.

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
| `tags` | optional keywords: the field, the kind of data, the kind of study |
| `license`, `created` | `MIT` unless the depositor chose another; the date |
| `code_url`, `publication`, `weights_url` | optional links, each an https address or a DOI: the code, the paper, the trained weights |
| `depositor` | `name`, `orcid`, `lab`, `institution`, `contact` |
| `run_by` | who or what ran it: `kind`, `tool`, `model` |
| `objective` | `goal`, and `optimize`: `{metric, split, direction}` |
| `data` | `name`, `accession`, `input`, `output`, `examples` (train, valid, test counts), `preprocessing`, `splits` |
| `data.accession` | the dataset's DOI. If it has none, its accession or an https link. No star without it |
| `data.benchmark` | optional: the id of the CAMEO benchmark this dataset belongs to |
| `data.preprocessing` | text, or `{how, code}` with the preprocessing code as text |
| `datasets` | optional further datasets by id, with the same fields as `data`: for example other benchmarks the models are scored on. `data` itself has the id `main` |
| `data.splits` | `how` the split was made, plus the `code` that builds it or the split `files` (name → `{url, sha256}`) |
| `evaluation` | `primary_metric`, `direction`, `selection_split`, `test_policy`, `noise_floor`, and `metrics`: name → how it is computed, or `{definition, direction}` when it is not obvious whether higher is better |
| `environment` | `python`, `framework`, `packages` (name → version), `training_hardware`, `inference_hardware` |
| `search` | `method`, `budget`, and `lineages`: lines of work by id, each with `name`, `family`, `parents` |
| `conclusions` | `best_run`, `findings`, `open_questions` |

Say exactly how the data was prepared. Two studies on one dataset can only be compared when a reader can see that both used the same test set and the same preprocessing. CAMEO shows `examples`, `splits` and `preprocessing` for every study on a benchmark, side by side.

## `models[]`

| Field | Holds |
|---|---|
| `id`, `name`, `family` | a stable id, a short name, the kind of model |
| `parent` | the model it was derived from, or `null` |
| `inputs`, `outputs` | name → `{kind, shape}` |
| `code` | the whole model file as text. It defines `build_model()`, which returns the network. If the model does not take one float tensor, it also defines `example_inputs(batch)`, which returns what to call the model with |
| `inference_speed` | `{"examples_per_s": n}`. See Performance |
| `layers` | optional layer list, for drawing the model |
| `base_model` | for a model built on published weights: `{name, link, revision}`, where `link` is an https address or a DOI |
| `adaptation` | how the base model was adapted, such as `LoRA, rank 8`, `full fine-tune` or `none` |

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
| `kind` | `train` (from scratch, the default), `finetune` (from existing weights), `evaluate` (no training: existing weights were scored) or `reported` (a number copied from a paper; nothing was run) |
| `reported_in` | for a `reported` run only: `{citation, doi}` or `{citation, url}`, with optional `where` and `note` |
| `data` | the id of the dataset it trained on, when that is not `main` |
| `settings` | only the settings this run set differently from its recipe |
| `weights` | optional link to the trained weights: `{"url": ...}` or `{"doi": ...}`, with `sha256` if you have it |
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
| `evaluations` | results on further datasets: `[{dataset, split, metrics}]`. A run with no training puts all its results here |

Training time and inference speed depend on the hardware, so each is recorded with its device: the GPU or CPU model, such as `NVIDIA A100`.

- `experiment.environment.training_hardware`: `{device, count, precision}`.
- `models[].inference_speed.examples_per_s`: a forward pass in evaluation mode, without gradients, at a fixed batch size, after a warm-up, taking the fastest of several timed passes.
- `experiment.environment.inference_hardware`: `{device, threads, batch, precision}` for that measurement.
- If a run trained on different hardware from the rest, give it its own under `performance.hardware`.

## Fine-tuned models, and models that were only evaluated

Not every run trains from scratch. Say which kind each run is, and link the weights involved.

- **Fine-tuned**: set `kind` to `finetune`, and give the model its `base_model`. The recipe is recorded as for any training.
- **Evaluated only**: set `kind` to `evaluate`. The run has no recipe, settings, seed or training time. Link the weights that were scored, under `weights`, or under the model's `base_model.link` if a published model was scored as it is.
- **Several datasets**: list the extra ones under `experiment.datasets`, and put each result under the run's `evaluations`.
- **Several seeds**: write one run per seed. CAMEO shows their mean and spread.

```json
"models": [{"id": "plm-lora", "name": "protein_650M_lora_r8", "family": "protein language model",
            "base_model": {"name": "Example protein model 650M", "link": "https://example.org/models/protein-650m", "revision": "v1"},
            "adaptation": "LoRA, rank 8", "code": "<the model file, as text>"}],
"runs": [{"id": "zero-shot", "model": "plm", "kind": "evaluate",
          "performance": {"status": "done", "score": 0.41, "parameters": 652000000,
            "evaluations": [{"dataset": "main", "split": "test", "metrics": {"spearman": 0.41}},
                            {"dataset": "assay2", "split": "test", "metrics": {"spearman": 0.37}}]}},
         {"id": "lora-s0", "model": "plm-lora", "kind": "finetune", "training": "lora", "seed": 0,
          "weights": {"doi": "10.5555/example-weights"},
          "performance": {"status": "done", "score": 0.63, "valid": {"spearman": 0.63}, "parameters": 655000000,
            "training_minutes": 62, "evaluations": [{"dataset": "main", "split": "test", "metrics": {"spearman": 0.61}}]}}]
```

## Results reported elsewhere

A baseline from a paper can sit beside your own runs. CAMEO marks it Reported, links it to its source, and gives it no star.

- Set `kind` to `reported`, and say where the number comes from in `reported_in`: a `citation`, and a `doi` or an https `url`. Add `where` for the table or figure.
- The run has no recipe, settings, seed or training time, and its model needs no `code`.
- Put the numbers under `test` or `evaluations`. Add `parameters` if the source states it.
- Copy only numbers the source states for this dataset and metric. Never read one off a figure or estimate it.
- If the source split or processed the data differently from you, say how in `reported_in.note`.

```json
"models": [{"id": "prior-cnn", "name": "prior_cnn", "family": "cnn", "parent": null}],
"runs": [{"id": "reported-cnn", "model": "prior-cnn", "kind": "reported",
          "reported_in": {"citation": "Example et al. 2025", "doi": "10.5555/example-paper", "where": "Table 2",
                          "note": "random split; this study splits by sequence identity"},
          "performance": {"status": "done", "parameters": 4200000, "test": {"spearman": 0.48}}}]
```

## Rules

- Never invent a value. Write `"not_reported"` for what the loop does not know.
- Numbers are numbers. `Infinity` and `NaN` are not allowed: write `null` and list the metric in `diverged`.
- Keep ids stable. Never renumber.
- `format_version` is `"0.4"`.

## Example

Copy the shape. Never copy the values.

```json
{
 "format_version": "0.4",
 "experiment": {
  "id": "study-example", "title": "Example: one small network", "license": "MIT", "created": "2026-01-01", "tags": ["example"],
  "summary": "Shows the shape of a sufficient file. Nothing here is real.",
  "depositor": {"name": "Example Depositor"},
  "run_by": {"kind": "agent", "tool": "example-loop"},
  "objective": {"goal": "Lowest validation MSE.", "optimize": {"metric": "mse", "split": "valid", "direction": "minimize"}},
  "data": {"name": "Example dataset", "accession": "10.5555/example-dataset", "input": "a vector of 32 numbers",
           "output": "one number", "examples": {"train": 1000, "valid": 200, "test": 200}, "preprocessing": "standardised per feature",
           "splits": {"how": "random, seed 0", "code": "<the code that builds the split, as text>"}},
  "evaluation": {"primary_metric": "mse", "direction": "minimize", "selection_split": "valid",
                 "metrics": {"mse": "mean squared error over examples", "pearson": "Pearson r over examples"}},
  "environment": {"python": "3.11", "framework": "PyTorch 2.4", "packages": {"numpy": "1.26"},
                  "training_hardware": {"device": "NVIDIA A100", "count": 1, "precision": "fp32"},
                  "inference_hardware": {"device": "NVIDIA A100", "batch": 64, "precision": "fp32"}},
  "conclusions": {"best_run": "run-001", "findings": [], "open_questions": []}
 },
 "models": [{
  "id": "model-1", "name": "small_mlp", "family": "mlp", "parent": null,
  "inputs": {"x": {"kind": "feature vector", "shape": [32]}}, "outputs": {"y": {"kind": "one number"}},
  "code": "<the model file, as text; it defines build_model()>",
  "inference_speed": {"examples_per_s": 5000.0}}],
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
- `data.accession` has the dataset's DOI, accession or link.
- Every model has its `code`.
- Every run names a model that exists. A run that trained also names a recipe and has a `seed`. A run that only scored weights links to them. A reported result links to its source.
- Every recipe has its `script`, and the fields above are filled.
- Every finished run of your own has `score`, metrics, `parameters` and `training_minutes`.
- Every model with a finished run has `inference_speed`.
- `environment` has versions, and the device for training and for inference. `data.splits` has code or files, and `data.preprocessing` says what was done.

The CAMEO kit checks all of this. It is two files, `cameo.py` and `rules.json`, kept in one folder. Both are at https://cameo-db.github.io/kit/.

```
python3 cameo.py check study.json
```

A complete file gives these lines. Add `--json` to get every gap with a `fix`. A file with a "no" is still accepted, with a lower star.

```
Sufficient? experiment: yes · model: yes · training: yes · performance: yes
Star: Gold
RESULT: ready to stage.
```

Then prove it once. Take one run, train it again from the file alone (its model `code`, its recipe's `script`, its settings, the same data and seed), and compare with the recorded score. They should agree within the noise floor. Record the result under `experiment.evaluation.rebuild_test`: `{run, recorded_score, rebuilt_score}`.

## Not PyTorch?

Everything above applies. Store the model and training code in your framework and name it under `environment.framework`.
