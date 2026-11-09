# Evaluation

Two things are measured separately: whether retrieval finds the code behind a bug report, and whether the agent reproduces bugs that exist without inventing ones that don't. Every number here comes from a raw result file in `benchmarks/results/`. Each file records the repository commit, the date and the model or embedder. Nothing is edited by hand. How to rerun them: [BENCHMARKS.md](BENCHMARKS.md).

## Cases

`benchmarks/cases/cases.v1.json` holds the public bug reports, written the way a user would report them:

| Case | Defect | Oracle |
|---|---|---|
| D01 | Applied coupon is lost when the checkout page is reloaded | `D01-coupon-persists` |
| D02 | Cart subtotal goes stale after changing a quantity | `D02-subtotal-updates` |
| D05 | Category filter is dropped when paginating | `D05-filter-survives-pagination` |

`benchmarks/ground-truth/fixtures.v1.json` records, for each case, the defect file, the other relevant files, the root cause and the oracle. Only the evaluators read it. The indexer's include list keeps it out of every snapshot, and the investigation worker never mounts it.

Each defect has an oracle, a Playwright test of the correct behaviour. `verify-oracles` checks that each oracle fails on the buggy build and passes on the fixed one, so the expected answer for every case is checked by machine, not just asserted.

## Retrieval: lexical vs vector vs hybrid

**Method**

- **Corpus:** the demo store's indexable tree (`demo-target/src`, `server`, `docs`, `tests`): 27 documents, 72 chunks.
- **Queries:** the three bug reports, verbatim.
- **Strategies:** PostgreSQL full-text search, pgvector cosine similarity, and both fused with reciprocal rank fusion.
- **Metrics:** file level. Hits are deduplicated by path. Recall@k is computed over each case's relevant files (3 for D01 and D02, 2 for D05). MRR uses the rank of the file that contains the defect.
- **Embedder:** `BAAI/bge-small-en-v1.5` (fastembed).

**Results.** Raw files: `benchmarks/results/retrieval/retrieval-20261107T233944Z-BAAI_bge-small-en-v1.5.{json,csv}`.

| Strategy | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR |
|---|---|---|---|---|---|
| lexical | 0.278 | 0.444 | 0.667 | 1.000 | 0.289 |
| vector  | 0.389 | 0.722 | 0.722 | 1.000 | 0.556 |
| hybrid  | 0.278 | 0.667 | 0.778 | 1.000 | 0.417 |

**Reading**

- Three queries are anecdotes, not statistics. One case moving by one rank changes mean MRR by about 0.1.
- Recall@10 is 1.0 everywhere because the corpus is tiny: ten files are a third of the repository. Recall@3 and Recall@5 are the useful columns.
- Vector search wins on D01 and D02, whose reports paraphrase the code. Lexical search wins on D05, where the report shares words with the code ("page", "filter").
- Hybrid is never the worst strategy and has the best Recall@5, but it is not the best on MRR. A design document (`demo-target/docs/ARCHITECTURE.md`) ranks first for D01 under lexical and hybrid. Down-weighting documentation for defect localisation is the obvious next experiment.

## Agent benchmark

**Method**

For each case, the harness runs the agent against:

- the **buggy** build, where the expected status is `reproduced`
- the **fixed** build, where the expected status is `not_reproduced`, so any `reproduced` is a false positive

It does this with each RAG arm (`none`, `hybrid` by default) and repeats each combination `--runs` times. A full default pass is 3 cases × 2 builds × 2 arms × 2 runs = 24 investigations. The model, budgets, prompt and store data stay the same; the store is reset through its admin endpoint before every run.

Each run goes through the same code as a normal investigation: API, job, real Chromium, budgets, verification and test validation. Only the Celery hop is replaced by an inline call. The status scored is the one the verification code decides, not the one the model claims; the model's claim is recorded separately as `claimed_status`.

Recorded per run: status, expected status, the model's claimed status, regression-test status, model calls, browser steps, input/output tokens, estimated cost and wall time. Per arm: accuracy, reproductions on buggy, false reproductions on fixed, validated regression tests and mean model calls.

**Results: pending.**

The benchmark is running on Groq's free tier with `openai/gpt-oss-120b`. That tier allows 200k tokens per day, and one investigation can use tens of thousands of input tokens, so a full pass takes several days. Runs that ended in `PROVIDER_RATE_LIMITED` measure the quota, not the agent. They are kept out of the published results, and the results will appear here once every row is a real run.

Verified so far: `openai/gpt-oss-120b` reproduced D01 on the buggy store, and the verification code accepted the reproduction. That is a single run. It shows the pipeline works end to end with a real model, and it is not a quality measurement.

The harness itself is tested end to end with a scripted stub model (`backend/tests/browser/test_benchmarks.py`). That test checks the wiring, not any model.

## What these numbers will not show

- Three cases from one small synthetic store. Results will not transfer to large or unfamiliar codebases.
- One model per published run. Results must always be read with the model id next to them.
- Replay runs (`replay:<model>`) re-execute a recorded transcript. They are useful for demos and regression checks and are never reported as model results.
