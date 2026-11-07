"""Check the configured model provider: reachable, and able to call tools.

Usage: ``uv run python -m reprolab.agent.check_model``. Exit code 0 when tool calling works.
Makes one small real request (except for ``replay``, which only validates the transcript).
"""

from __future__ import annotations

import sys

from reprolab.agent.model_client import ModelUnavailable, build_model_client
from reprolab.agent.openai_compatible import check_tool_support
from reprolab.config.settings import get_settings


def main() -> int:
    # Never write the probe turn into a recording transcript.
    settings = get_settings().model_copy(update={"llm_record_path": None})
    print(f"provider={settings.llm_provider} model={settings.llm_model}")
    try:
        client = build_model_client(settings)
    except ModelUnavailable as exc:
        print(f"FAIL {exc.code}: {exc}")
        return 1
    if settings.llm_provider == "replay":
        print(f"OK replay transcript loaded ({client.model_id}).")
        return 0
    ok, detail = check_tool_support(client)
    print(("OK " if ok else "FAIL ") + detail)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
