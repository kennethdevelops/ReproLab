# Ground truth (evaluation only)

**Never index this directory, never mount it into the investigation worker, never include it in model context.**

`fixtures.v1.json` records, for each defect fixture, where the defect lives, the oracle that decides it, and the fixture variants. The repository indexer only reads an explicit include list (`demo-target/src`, `demo-target/server`, `demo-target/docs`, `demo-target/tests`), so this directory and `demo-target/fixtures/` are outside its reach; security tests assert this.
