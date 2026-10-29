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
| Browser origin allowlist on every request and redirect | M2 |
| `file:`/`data:`/`javascript:`, metadata and private IPs rejected | M2 |
| Typed browser tools only; no `evaluate()` for the model | M2 |
| Prompt-injection fixtures in repo content and page DOM | M4 |
| Restricted JSON test spec, isolated Node runner | M5 |
| Public demo rate limits and cost caps | M8 |

## Known gap: container egress

`worker-investigation` needs outbound HTTPS to the model provider, so it sits on the `edge` network as well as `sandbox`. Chromium in that container could therefore reach the internet at the network layer; the application-level allowlist (route interception on every request) is the control today. Before any public deployment (M8/M9) the plan is an egress proxy that allows only the model provider's API host, with Chromium given no proxy route at all.
