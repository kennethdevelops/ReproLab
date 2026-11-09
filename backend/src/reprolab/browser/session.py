"""Restricted Playwright browser session for one investigation.

The model never touches Playwright directly: it can only invoke the typed actions in
``actions.py``. Every network request (navigation, redirect, sub-resource, fetch) passes through a
route handler that applies the OriginPolicy, so a redirect or injected link to another origin is
aborted inside the browser.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, Route, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator as PwLocator
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from pydantic import BaseModel

from reprolab.browser import actions as a
from reprolab.browser.policy import OriginPolicy, PolicyViolation
from reprolab.observability.redaction import redact_text, truncate

log = logging.getLogger(__name__)

ACTION_TIMEOUT_MS = 5_000
NAVIGATION_TIMEOUT_MS = 15_000
MAX_TEXT_CHARS = 4_000
MAX_SNAPSHOT_CHARS = 6_000
MAX_LOG_ENTRIES = 50


@dataclass
class ActionResult:
    ok: bool
    summary: str
    output: str = ""
    error_code: str | None = None
    screenshot: bytes | None = None
    screenshot_label: str | None = None
    url_after: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrowserSession:
    policy: OriginPolicy
    base_origin: str
    trace_path: Path
    viewport: dict[str, int]
    headless: bool = True
    _pw: Playwright | None = None
    _browser: Browser | None = None
    _context: BrowserContext | None = None
    _page: Page | None = None
    console_errors: list[str] = field(default_factory=list)
    network_errors: list[str] = field(default_factory=list)
    blocked_requests: list[str] = field(default_factory=list)
    browser_version: str = ""

    def __enter__(self) -> BrowserSession:
        self._pw = sync_playwright().start()
        # Chromium sandbox stays enabled (Playwright default); no --no-sandbox.
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self.browser_version = self._browser.version
        self._context = self._browser.new_context(
            viewport={"width": self.viewport["width"], "height": self.viewport["height"]},
            accept_downloads=False,
            service_workers="block",
            java_script_enabled=True,
        )
        self._context.set_default_timeout(ACTION_TIMEOUT_MS)
        self._context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
        self._context.route("**/*", self._guard_request)
        self._context.tracing.start(screenshots=True, snapshots=True, sources=False)
        self._page = self._context.new_page()
        self._page.on("console", self._on_console)
        self._page.on("pageerror", lambda exc: self._push(self.console_errors, f"pageerror: {exc}"))
        self._page.on("response", self._on_response)
        self._page.on("requestfailed", self._on_request_failed)
        self._page.on("popup", lambda popup: popup.close())
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        try:
            if self._context is not None:
                self.trace_path.parent.mkdir(parents=True, exist_ok=True)
                self._context.tracing.stop(path=str(self.trace_path))
                self._context.close()
        except PlaywrightError as exc:
            log.warning("trace_stop_failed", extra={"error": str(exc)})
        finally:
            if self._browser is not None:
                self._browser.close()
            if self._pw is not None:
                self._pw.stop()
            self._context = self._browser = self._pw = self._page = None

    # --- Event handlers -------------------------------------------------------------------

    def _guard_request(self, route: Route) -> None:
        url = route.request.url
        try:
            self.policy.check_url(url)
        except PolicyViolation as exc:
            self._push(self.blocked_requests, f"{exc.code}: {truncate(url, 200)}")
            route.abort("blockedbyclient")
            return
        route.continue_()

    def _on_console(self, msg: Any) -> None:
        if msg.type in ("error", "warning"):
            self._push(self.console_errors, f"{msg.type}: {msg.text}")

    def _on_response(self, response: Any) -> None:
        if response.status >= 400:
            req = response.request
            self._push(
                self.network_errors, f"{req.method} {_path_only(req.url)} -> {response.status}"
            )

    def _on_request_failed(self, request: Any) -> None:
        failure = request.failure or "failed"
        if "blockedbyclient" not in failure.lower():
            self._push(
                self.network_errors, f"{request.method} {_path_only(request.url)} -> {failure}"
            )

    @staticmethod
    def _push(bucket: list[str], entry: str) -> None:
        if len(bucket) < MAX_LOG_ENTRIES:
            bucket.append(truncate(redact_text(entry), 500))

    # --- Actions ----------------------------------------------------------------------------

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("browser session is not open")
        return self._page

    def current_url(self) -> str:
        return self.page.url

    def screenshot(self) -> bytes:
        return self.page.screenshot(full_page=False, type="png")

    def run(self, name: str, args: BaseModel) -> ActionResult:
        handler: Callable[[Any], ActionResult] | None = getattr(self, f"_do_{name}", None)
        if handler is None or name not in a.BROWSER_ACTIONS:
            return ActionResult(
                False, f"Unsupported action {name}", error_code="UNSUPPORTED_ACTION"
            )
        started = time.monotonic()
        try:
            result = handler(args)
        except PolicyViolation as exc:
            result = ActionResult(False, str(exc), error_code=exc.code)
        except PlaywrightTimeout as exc:
            result = ActionResult(False, _first_line(exc), error_code="TIMEOUT")
        except PlaywrightError as exc:
            result = ActionResult(False, _first_line(exc), error_code="BROWSER_ERROR")
        result.url_after = self._safe_url()
        result.data.setdefault("duration_ms", int((time.monotonic() - started) * 1000))
        result.summary = redact_text(result.summary)
        result.output = redact_text(result.output)
        return result

    def _safe_url(self) -> str | None:
        try:
            return self.page.url
        except PlaywrightError:
            return None

    def _locate(self, loc: a.Locator) -> PwLocator:
        page = self.page
        match loc.kind:
            case a.LocatorKind.ROLE:
                return page.get_by_role(loc.value, name=loc.name, exact=loc.exact)  # type: ignore[arg-type]
            case a.LocatorKind.LABEL:
                return page.get_by_label(loc.value, exact=loc.exact)
            case a.LocatorKind.TEXT:
                return page.get_by_text(loc.value, exact=loc.exact)
            case a.LocatorKind.TEST_ID:
                return page.get_by_test_id(loc.value)
            case a.LocatorKind.PLACEHOLDER:
                return page.get_by_placeholder(loc.value, exact=loc.exact)
            case a.LocatorKind.CSS:
                return page.locator(loc.value)

    def _single(self, loc: a.Locator) -> PwLocator:
        target = self._locate(loc)
        count = target.count()
        if count == 0:
            # Give late-rendering elements a moment before reporting "not found".
            target.first.wait_for(state="attached", timeout=ACTION_TIMEOUT_MS)
            count = target.count()
        if count > 1:
            raise PlaywrightError(
                f"Locator {loc.describe()} matched {count} elements; make it more specific."
            )
        return target

    def _do_open_page(self, args: a.OpenPage) -> ActionResult:
        url = self.policy.resolve_navigation(self.base_origin, args.path)
        response = self.page.goto(url, wait_until="load")
        self.page.wait_for_load_state("networkidle", timeout=5_000)
        status = response.status if response else None
        return ActionResult(
            True, f"Opened {_path_only(url)} (HTTP {status})", data={"status": status}
        )

    def _do_click(self, args: a.Click) -> ActionResult:
        self._single(args.locator).click()
        self._settle()
        return ActionResult(True, f"Clicked {args.locator.describe()}")

    def _do_fill(self, args: a.Fill) -> ActionResult:
        self._single(args.locator).fill(args.text)
        return ActionResult(True, f"Filled {args.locator.describe()} with {len(args.text)} chars")

    def _do_press(self, args: a.Press) -> ActionResult:
        self._single(args.locator).press(args.key)
        self._settle()
        return ActionResult(True, f"Pressed {args.key} in {args.locator.describe()}")

    def _do_select_option(self, args: a.SelectOption) -> ActionResult:
        selected = self._single(args.locator).select_option(args.value)
        self._settle()
        return ActionResult(True, f"Selected {selected} in {args.locator.describe()}")

    def _do_reload_page(self, _: a.NoArgs) -> ActionResult:
        self.page.reload(wait_until="load")
        self._settle()
        return ActionResult(True, f"Reloaded {_path_only(self.page.url)}")

    def _do_go_back(self, _: a.NoArgs) -> ActionResult:
        response = self.page.go_back(wait_until="load")
        self._settle()
        return ActionResult(True, "Navigated back" if response or self.page.url else "No history")

    def _do_wait_for(self, args: a.WaitFor) -> ActionResult:
        self._locate(args.locator).first.wait_for(state=args.state, timeout=args.timeout_ms)
        return ActionResult(True, f"{args.locator.describe()} is {args.state}")

    def _do_read_page_snapshot(self, _: a.NoArgs) -> ActionResult:
        snapshot = self.page.locator("body").aria_snapshot()
        text = truncate(snapshot, MAX_SNAPSHOT_CHARS)
        return ActionResult(True, f"Accessibility snapshot ({len(snapshot)} chars)", output=text)

    def _do_read_visible_text(self, args: a.ReadVisibleText) -> ActionResult:
        target = self._single(args.locator) if args.locator else self.page.locator("body")
        text = truncate(target.inner_text(), MAX_TEXT_CHARS)
        where = args.locator.describe() if args.locator else "page"
        return ActionResult(True, f"Read visible text of {where} ({len(text)} chars)", output=text)

    def _do_read_current_url(self, _: a.NoArgs) -> ActionResult:
        return ActionResult(True, "Current URL", output=_path_only(self.page.url, keep_query=True))

    def _do_read_console_errors(self, _: a.NoArgs) -> ActionResult:
        out = "\n".join(self.console_errors) or "(no console errors or warnings)"
        return ActionResult(True, f"{len(self.console_errors)} console entries", output=out)

    def _do_read_network_errors(self, _: a.NoArgs) -> ActionResult:
        entries = self.network_errors + [f"blocked by policy: {b}" for b in self.blocked_requests]
        out = "\n".join(entries) or "(no failed requests)"
        return ActionResult(True, f"{len(entries)} network entries", output=out)

    def _do_capture_screenshot(self, args: a.CaptureScreenshot) -> ActionResult:
        image = self.screenshot()
        return ActionResult(
            True,
            f"Captured screenshot '{args.label}'",
            screenshot=image,
            screenshot_label=args.label,
        )

    def _settle(self) -> None:
        with contextlib.suppress(PlaywrightTimeout):
            self.page.wait_for_load_state("networkidle", timeout=3_000)


def _first_line(exc: BaseException) -> str:
    return truncate(
        str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__, 300
    )


def _path_only(url: str, keep_query: bool = True) -> str:
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    path = parts.path or "/"
    return f"{path}?{parts.query}" if keep_query and parts.query else path
