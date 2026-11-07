# ADR-0004: Bring your own model

- **Status:** Accepted
- **Date:** 2026-11-07
- **Supersedes:** the chat-model provider part of ADR-0002 (embeddings unchanged)

## Context

The owner has no paid API credit, and anyone cloning the repository should be able to run the agent with whatever model they have: a hosted API, a local server, or nothing at all.

## Decision

- `LLM_PROVIDER` selects one of three adapters behind the existing `ModelClient` interface:
  - `anthropic`: official SDK, unchanged from ADR-0002.
  - `openai_compatible`: one `httpx` client for any `/v1/chat/completions` server with function calling (Ollama, LM Studio, vLLM, OpenAI, Gemini, Groq, OpenRouter). Configured by `LLM_BASE_URL`, `LLM_MODEL`, optional `LLM_API_KEY`. No new SDK dependency.
  - `replay`: replays a transcript recorded with `LLM_RECORD_PATH` from an earlier live run. Its model id is `replay:<recorded model>`, cost is 0 and the report states it is a replay. Replay runs never count as model-quality results.
- The agent keeps its history in Anthropic content-block form. The OpenAI-compatible adapter translates history and tools on each call and translates responses back. Invalid tool-call JSON is passed to server-side validation, which returns an error to the model.
- `strict` function schemas are opt-in (`LLM_STRICT_TOOLS`) because many local servers reject or ignore them. Server-side Pydantic validation still applies to every call.
- `python -m reprolab.agent.check_model` makes one probe request and fails unless the model returns a tool call.
- Prices: built-in table plus optional `LLM_PRICES_FILE`. A model without a price runs under token, step and time budgets only; its cost shows as "not estimated". The cost cap cannot protect an unpriced paid model, which the `.env.example` comment states.

## Consequences

- Small local models may run but investigate poorly; published results must name the model used.
- Provider-specific features (prompt caching, effort, refusal fallback) apply only to `anthropic`.
