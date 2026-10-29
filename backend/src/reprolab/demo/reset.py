"""Reset demo-target fixture state. Operator command: ``python -m reprolab.demo.reset``.

Not exposed through the public API; requires DEMO_ADMIN_TOKEN.
"""

from __future__ import annotations

import httpx

from reprolab.config.settings import Settings, get_settings


def reset_demo_targets(settings: Settings | None = None) -> dict[str, int]:
    settings = settings or get_settings()
    if settings.demo_admin_token is None:
        raise RuntimeError("DEMO_ADMIN_TOKEN is not configured; refusing to reset.")
    token = settings.demo_admin_token.get_secret_value()
    results: dict[str, int] = {}
    for origin in (settings.demo_allowed_origin, settings.demo_fixed_origin):
        response = httpx.post(
            f"{origin}/__admin/reset", headers={"X-Admin-Token": token}, timeout=10
        )
        response.raise_for_status()
        results[origin] = response.status_code
    return results


if __name__ == "__main__":
    for origin, status in reset_demo_targets().items():
        print(f"reset {origin}: {status}")
