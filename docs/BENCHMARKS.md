# Running the benchmarks

The method and published results are in [EVALUATION.md](EVALUATION.md). This page covers how to run them.

Both harnesses write into `benchmarks/results/<kind>/` with a UTC timestamp and the model or embedder in the file name. Commit result files unchanged. If a run is wrong, rerun it rather than editing the output.

## Defect oracles

These check that the benchmark's expected answers hold: each oracle must fail on the buggy build and pass on the fixed one.

```bash
cd demo-target
npm ci && npx playwright install chromium
npm run build
npm run verify-oracles -- --runs 2
```

Expected: 12/12 as expected (3 oracles × 2 builds × 2 runs).

## Retrieval evaluation

Needs PostgreSQL with pgvector. The database name must contain `test` or `eval`, because the harness creates its own project and snapshot. No model provider is needed.

```bash
cd backend
DATABASE_URL=postgresql+psycopg://reprolab:reprolab@localhost:5432/reprolab_eval \
  uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://reprolab:reprolab@localhost:5432/reprolab_eval \
  uv run python -m reprolab.evaluation.retrieval_eval
```

It indexes the demo store's tree with the configured embedder (`EMBEDDING_MODEL`, default `BAAI/bge-small-en-v1.5`), runs each case's bug report through lexical, vector and hybrid search, and writes `retrieval-<stamp>-<embedder>.{json,csv}`. With the same embedder and commit, the numbers should match the published ones.

## Agent benchmark

Needs:

- PostgreSQL with pgvector. The database name must contain `test` or `eval`.
- Both demo store builds running, with the same `DEMO_ADMIN_TOKEN` as in `.env`. The harness resets the store before each run.
- Optionally the test runner (`TEST_RUNNER_URL`), to validate regression tests.
- A model in `.env` that passes `check_model`.
- For the `hybrid` arm, the embedder. The harness indexes the demo store itself.

```bash
# terminal 1 and 2: the store
cd demo-target && npm run build
DEMO_ADMIN_TOKEN=<token> node server/index.mjs --mode buggy --port 4173
DEMO_ADMIN_TOKEN=<token> node server/index.mjs --mode fixed --port 4174

# terminal 3: optional test runner
cd test-runner && BUGGY_URL=http://127.0.0.1:4173 FIXED_URL=http://127.0.0.1:4174 DEMO_ADMIN_TOKEN=<token> npm start

# terminal 4
cd backend
uv run python -m reprolab.agent.check_model
DATABASE_URL=postgresql+psycopg://reprolab:reprolab@localhost:5432/reprolab_eval \
TEST_RUNNER_URL=http://127.0.0.1:4300 \
  uv run python -m reprolab.evaluation.agent_bench \
    --buggy-url http://127.0.0.1:4173 --fixed-url http://127.0.0.1:4174 \
    --cases D01 D02 D05 --arms none hybrid --runs 2
```

Options:

| Flag | Default | |
|---|---|---|
| `--cases` | `D01 D02 D05` | Case ids from `benchmarks/cases/cases.v1.json` |
| `--arms` | `none hybrid` | Any of `none`, `lexical`, `vector`, `hybrid` |
| `--runs` | `2` | Repeats per case × build × arm |
| `--out` | `benchmarks/results/agent` | Output directory |

Output:

- `agent-<stamp>-<model>.partial.jsonl` gets one row as each run finishes, so an interrupted pass keeps its completed rows.
- When the pass completes, it writes `agent-<stamp>-<model>.json` (summary per arm, budgets, commit, model id, rows) and a matching `.csv`, then deletes the partial file.

### Free tiers and rate limits

A run that hits a provider rate limit ends `blocked` or `inconclusive` with `PROVIDER_RATE_LIMITED` in `status_reason`. Those rows measure the quota, not the agent, and must not be published as results. On a tier with a daily token cap, run a subset per day (`--cases D01 --runs 1`) and publish only complete passes in which no row was rate-limited. `*.partial.jsonl` files stay out of the repository.

Budgets apply during benchmarking as usual. Lowering `MAX_INPUT_TOKENS_PER_RUN` saves quota, but it changes the conditions, and results run with a lower value are not comparable with the defaults. The budgets in effect are recorded in the result file.

### Replay

To demo the pipeline without a live model, record a run and replay it:

```bash
LLM_RECORD_PATH=../benchmarks/transcripts/d01.json    # during a live run
LLM_PROVIDER=replay LLM_REPLAY_PATH=../benchmarks/transcripts/d01.json
```

Replay rows carry `replay:<model>` as the model id and `"is_replay": true`. They are never model results.
