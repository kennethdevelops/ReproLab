# Security

Threat model and controls follow spec §12. Status column reflects what is implemented and tested now, not intent.

| Control | Status |
|---|---|
| Secrets only in `.env` (git-ignored); `.env.example` placeholders | Done |
| `/api/v1/settings` never returns secrets | Done, unit-tested |
| Error envelope hides stack traces and request bodies | Done, unit-tested |
| Untrusted `X-Request-ID` values replaced | Done, unit-tested |
| Demo fixture reset requires `DEMO_ADMIN_TOKEN` (constant-time compare) | Done, manually probed (403 without token) |
| Demo server static path traversal | SPA fallback served; manually probed |
| Ground truth outside indexed paths, never mounted into workers | Done by layout; automated test arrives with the indexer (M3) |
| Browser origin allowlist on every request and redirect (Playwright route interception) | Done; unit + browser tests |
| `file:`/`data:`/`javascript:`/credentials-in-URL rejected; link-local/metadata addresses always rejected; private resolution rejected when `allow_internal_ips=False` | Done; unit tests (DNS stubbed) |
| Typed browser tools only; no `evaluate()`; Pydantic validation of every tool call; unknown tools rejected | Done; unit + browser tests |
| Downloads disabled, service workers blocked, popups closed, fresh context per run | Done (config); not separately tested |
| Start request cannot set origins, limits, model or prompt (`extra="forbid"`) | Done; integration tests |
| Redaction of API keys, bearer tokens, JWTs, emails, sensitive headers/keys in steps, events, console/network logs | Done; unit tests. Screenshots and traces are not redacted (synthetic data only in demo) |
| Artifact download by opaque ID, path containment check, `nosniff` | Done; integration test |
| Prompt-injection fixtures in repo content | Done: retrieved source is fenced, the fence cannot be closed from inside, and source never counts as evidence (`tests/security/test_retrieval_tool.py`). Page-DOM injection fixture not built |
| Restricted JSON test spec, isolated Node runner | Done: allowlisted actions/locators/assertions, no code accepted, spec text emitted only as JSON string literals, targets fixed by env, sandbox network only (`test-runner/tests`) |
| Public demo rate limits and cost caps | M8 |

## Known gap: container egress

`worker-investigation` needs outbound HTTPS to the model provider, so it sits on the `edge` network as well as `sandbox`. Chromium in that container could therefore reach the internet at the network layer; the application-level allowlist (route interception on every request) is the control today. Before any public deployment (M8/M9) the plan is an egress proxy that allows only the model provider's API host, with Chromium given no proxy route at all.
