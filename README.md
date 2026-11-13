# Forecasting Release-Level Refactoring from Code, History and Discourse: Replication Package

This repository holds everything needed to rebuild the dataset and the model of the study *A
Language Model That Reads Code, History and Discourse*, Chapter 5 of Binamra Aryal's MS thesis at
The University of Texas at Arlington. The study asks whether a pretrained transformer that reads a
Java file's code, its commit history and the issues and pull requests linked to it can forecast
whether developers refactor the file before the next release.

The data lives on Zenodo, and the code that builds and uses it lives here.

| What | Where |
|---|---|
| Mined inputs: release grids, Quarry's outputs and a git bundle of each repo | Zenodo, [10.5281/zenodo.24182007](https://doi.org/10.5281/zenodo.24182007) |
| The dataset: 462,120 rows with their code, history and discourse texts | Zenodo, [10.5281/zenodo.24117444](https://doi.org/10.5281/zenodo.24117444) (version 2.1) |
| Quarry, the mining tool | [QUARRY](https://github.com/Binamra00/quarry.git) |
| Release mining, the release-tree scripts, Notebooks 0–4 and the final run's results | this repository |

## Contents

```
release_mining/
  rel_tag_mining_v4.ipynb        the release grid and the commit universe of each repo
scripts/
  build_intervals.py             helpers that build_release_tree.py imports
  build_release_tree.py          the release tree: each release's parent and the commits between them
notebooks/
  notebook_0_production.ipynb    which .java files are production code
  notebook_1_CBERT.ipynb         one labelled row per production file per release
  notebook_2_CBERT.ipynb         the commits, issues and pull requests that belong to each row
  notebook_3_dataset_CBERT.ipynb the texts, the split and the published dataset (one repo per run)
  notebook_4_model_CBERT_3.ipynb the model: fine-tuning, forecasts and each view's contribution
results/
  run3/run3_executed.ipynb       Notebook 4 as it ran for the reported results, with every output
  run3/run3.log                  the run's log
  run3/outputs/                  the reported results (listed below)
  preliminary/                   two earlier runs of Notebook 4, not reported (see below)
```

The notebooks keep the outputs of the runs that built the published dataset, so each one also
documents its own run.

## What you need

- **Git** on your `PATH`.
- **Python 3.11 or newer.** Notebooks 0–3 run on a laptop: `pip install -r requirements.txt`.
- **For Notebook 4, a GPU with bfloat16 support and about 20 GB of memory**, such as an A100, an
  RTX PRO 6000 or an L4. The reported run used one A100 with 80 GB and peaked at 16.7 GB. Install
  `requirements-model.txt` on that machine.
- **Disk space:** about 3 GB for the mined inputs and clones, and about 15 GB for Notebook 4.

Every notebook finds its working folder the same way: `QUARRY_HOME` if it is set, otherwise
`workspace_data/` one level above the notebook. Run the notebooks from `notebooks/`, and they share
`workspace_data/` at the root of this repository.

## Path A: rebuild the dataset from the mined inputs

This is the usual way to replicate the dataset. It downloads what was mined and needs no mining tool.

```
git clone https://github.com/Binamra00/refactoring-forecast-replication.git
cd refactoring-forecast-replication
pip install -r requirements.txt
cd notebooks
jupyter lab
```

Then run the notebooks in order.

1. **Notebook 0.** Its first cell downloads the mined inputs from Zenodo (about 2.5 GB). It checks
   every file against its SHA-256 and restores each git bundle as a clone in
   `workspace_data/repos/<repo>/`. The notebook then decides which files are production code and
   writes `production_scope.json` and `production_files_<repo>.csv`.
2. **Notebook 1** writes the labels, `outputs/notebook_1_cbert/`.
3. **Notebook 2** writes each row's evidence lists, `outputs/notebook_2_cbert/`.
4. **Notebook 3** builds one repo per run. Run its cell 0 once and restart the kernel. Then, for
   each of the five repos, pick the repo in cell 1 and run cells 1a to 8. Cell 9 then prints the
   numbers for all five.

Notebooks 1–3 open with the same download cell, so a workspace that already has the inputs
downloads nothing.

**Checking the result.** Each repo's `outputs/notebook_3_cbert/<repo>/manifest_<repo>.json` lists
every file's line count and SHA-256. The line counts and the report numbers should match the
manifests in the published dataset. The SHA-256 values match too when pandas and pyarrow are the
versions the manifest records.

## Path B: train and test the model

`notebooks/notebook_4_model_CBERT_3.ipynb` downloads the dataset from Zenodo (10.5281/zenodo.24117444)
and checks it, then tokenises the texts, fine-tunes the model, scores the three parts and explains
each view's contribution with Shapley values. On Google Colab it keeps its files on Google Drive.
Elsewhere it keeps them in `notebook_4_model_cbert_3/` beside the notebook.

The reported run took 15.5 hours on one A100 (7 epochs of about 130 minutes, plus scoring). To run
it without keeping a browser open, use papermill:

```
pip install -r requirements-model.txt papermill
papermill notebook_4_model_CBERT_3.ipynb run_executed.ipynb --log-output > run.log 2>&1
```

A run that stops part-way resumes from its last finished epoch when you start it again.

### The reported results (`results/run3/outputs/`)

| File | Holds |
|---|---|
| `results.csv` | precision, recall, F1, ROC-AUC, AP, loss and the confusion matrix, per part and per repo |
| `epochs.csv`, `runs.jsonl` | every epoch's scores on the training sample and the validation rows |
| `run_times.csv` | minutes per stage and peak GPU memory |
| `run_config.json` | every setting, the GPU and the package versions |
| `forecasts.parquet` | each row's probability and flag |
| `view_shap.csv`, `view_shap_test.parquet` | each view's Shapley value, summarised and per test row |
| `text_lengths.csv` | the length of every kind of text, in tokens |
| `curves.png`, `confusion.png` | the scores per epoch and the confusion matrices |

On the test releases the model reaches an AP of 0.079 (base rate 3.2%) and a ROC-AUC of 0.713. Code
contributes most to separating refactored files from the rest.

### The preliminary runs

`results/preliminary/` holds two earlier runs of Notebook 4. They used version 1.0 of the dataset,
which kept only the files the CK metrics tool measured, and trained with fewer rows per step. They
shaped the settings of the final run. The thesis reports the final run only.

## Path C: mine everything again

To mine the repos yourself instead of downloading the mined inputs:

1. **Release grid.** Run `release_mining/rel_tag_mining_v4.ipynb`. It writes the grid and the commit
   universe to `workspace_data/versions/`. It clones the repos as they are today, so HEAD and the
   newest releases differ from the study's grid (frozen on 15 July 2026).
2. **Mining.** Run Quarry's ledger, RefactoringMiner, diff, channel and linkage stages on each repo,
   with the commit universe from step 1. Quarry's README gives the commands. Point `QUARRY_HOME` at
   this repository's `workspace_data/` so Quarry and the notebooks share one workspace.
3. **Release tree.** From the root of this repository:
   ```
   python scripts/build_release_tree.py workspace_data --write-intervals commons-lang checkstyle dubbo junit-framework questdb
   ```
4. **The dataset.** Run Notebooks 0–3 as in Path A. Their download cell finds your files and
   downloads nothing.

## Path C: mine everything again

To mine the repos yourself instead of downloading the mined inputs. Quarry and this repository
must share one workspace: in Quarry's `.env`, set `QUARRY_HOME` to the `workspace_data/` folder
at the root of this repository (for example `QUARRY_HOME=E:\refactoring-forecast-replication\workspace_data`).

1. **Release grid.** Run `release_mining/rel_tag_mining_v4.ipynb`. For each repo it writes
   `rel_hist_<repo>.json`, `<repo>_release_manifest.json` and `adapter_universe_<repo>.json` to
   `workspace_data/versions/`, where Quarry looks for them. It clones the repos as they are
   today, so HEAD differs from the study's grid (frozen on 15 July 2026); our rerun on
   12 November 2026 kept the same 542 releases at the same commits.
2. **Mining.** Install [Quarry](https://github.com/Binamra00/quarry) and run, for each repo
   (Git Bash):
   ```bash
   for u in apache/commons-lang checkstyle/checkstyle apache/dubbo junit-team/junit-framework questdb/questdb; do
     P=${u#*/}
     quarry --repo https://github.com/$u.git --stage meta
     quarry --repo $P --stage ledger  --universe adapter_universe_$P.json --batch 0
     quarry --repo $P --stage refm    --universe adapter_universe_$P.json --batch 0
     quarry --repo $P --stage diff    --universe adapter_universe_$P.json --batch 0
     quarry --repo $P --stage channel --platform git    --channel commits --universe adapter_universe_$P.json --batch 0
     quarry --repo $P --stage channel --platform github --channel all --batch 0
     quarry --repo $P --stage link
   done
   ```
   The GitHub channels need `GITHUB_TOKEN` in Quarry's `.env` and take the longest. Every
   command can be stopped and run again; it continues where it stopped.
3. **Release tree.** From the root of this repository:
   ```
   python scripts/build_release_tree.py workspace_data --write-intervals commons-lang checkstyle dubbo junit-framework questdb
   ```
4. **The dataset.** Run Notebooks 0–3 as in Path A. Their download cell finds your files and
   downloads nothing.

## Known limitations

- **Commits hidden by history simplification.** Quarry's RefactoringMiner, diff and commit-message
  stages list commits with `git log <universe> -- '*.java'`. Git's history simplification skips
  89 commits that the ledger lists (4 in commons-lang, 1 in checkstyle, 65 in dubbo, 19 in
  junit-framework). Their history texts keep only the commit message, and any refactoring in them is
  missing from the labels.
- **Closed items only.** Quarry mined closed issues and pull requests only. Commons-Lang tracks its
  issues in Jira, so its rows have no issue texts.
- **The trained weights are not here.** They take 1.4 GB.

## Citation

See `CITATION.cff`. Please cite the dataset and the mined inputs by their DOIs.

## License

The code in this repository is under the MIT License (`LICENSE`). The data on Zenodo is under
CC BY 4.0. The mined code, commits and texts remain under their projects' licenses.
