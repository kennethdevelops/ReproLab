# Evaluation

All numbers here come from raw result files in `benchmarks/results/`, each committed with the repository commit, the date, and the model or embedder used. Nothing is hand-edited.

## Retrieval (lexical vs vector vs hybrid)

- **Corpus:** the demo store's indexable tree (`demo-target/src`, `server`, `docs`, `tests`): 27 documents, 72 chunks.
- **Queries:** the three public bug reports (`benchmarks/cases/cases.v1.json`), verbatim.
- **Labels:** `benchmarks/ground-truth/fixtures.v1.json`. These are read only by the evaluator and never indexed.
- **Metrics:** file level. Hits are deduplicated by path. Recall@k is computed over each case's 3 relevant files (D05 has 2). MRR is the rank of the first file that contains the defect.
- **Command:** `uv run python -m reprolab.evaluation.retrieval_eval` (embedder `BAAI/bge-small-en-v1.5`).
- **Raw results:** `benchmarks/results/retrieval/retrieval-20261107T233944Z-BAAI_bge-small-en-v1.5.{json,csv}`.

| Strategy | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR |
|---|---|---|---|---|---|
| lexical | 0.278 | 0.444 | 0.667 | 1.000 | 0.289 |
| vector  | 0.389 | 0.722 | 0.722 | 1.000 | 0.556 |
| hybrid  | 0.278 | 0.667 | 0.778 | 1.000 | 0.417 |

Reading:

- With three queries, these are anecdotes, not statistics. One case moving by one rank changes the mean MRR by about 0.1.
- Recall@10 is 1.0 for every strategy because the corpus is tiny: ten files cover a third of the repository. Recall@3 and Recall@5 are the informative columns.
- Vector search wins on the paraphrased reports D01 and D02. Lexical search wins on D05, where the report shares words with the code ("page", "filter"). Hybrid (RRF) is never the worst strategy and has the best Recall@5, but it is not best on MRR. A design doc (`docs/ARCHITECTURE.md`) ranks first for D01 in lexical and hybrid mode. Down-weighting documentation for defect localisation is an obvious next experiment.

## Agent benchmark

The harness is `uv run python -m reprolab.evaluation.agent_bench --buggy-url … --fixed-url … --runs 2`. For each case it runs the buggy and fixed store × the RAG arms (`none`, `hybrid`) × the runs, through the real API, browser, verification and test validation. It records the status against the expected status, false reproductions on the fixed store, validated regression tests, model calls, tokens and estimated cost.

**No model results are published yet.** The harness is tested end to end with a scripted stub model (`tests/browser/test_benchmarks.py`). That proves the wiring, not model quality. Results from a real model will be added here with the model id, and replay runs will be labelled as such.
