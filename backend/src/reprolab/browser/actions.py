"""Typed, validated browser action inputs. Model output is parsed into these before anything runs."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ARIA_ROLES = frozenset(
    {
        "button", "link", "textbox", "checkbox", "radio", "combobox", "listbox", "option",
        "heading", "row", "cell", "table", "list", "listitem", "navigation", "region", "dialog",
        "alert", "status", "spinbutton", "tab", "tabpanel", "menu", "menuitem", "img", "main",
        "form", "search", "complementary", "banner", "contentinfo", "article", "group",
    }
)  # fmt: skip

ALLOWED_KEYS = frozenset(
    {"Enter", "Tab", "Escape", "Backspace", "Delete", "ArrowUp", "ArrowDown", "ArrowLeft",
     "ArrowRight", "Home", "End", "PageUp", "PageDown", "Space"}
)  # fmt: skip


class LocatorKind(StrEnum):
    ROLE = "role"
    LABEL = "label"
    TEXT = "text"
    TEST_ID = "test_id"
    PLACEHOLDER = "placeholder"
    CSS = "css"


class Locator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: LocatorKind
    value: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=200)
    exact: bool = False

    @field_validator("value")
    @classmethod
    def _no_control_chars(cls, v: str) -> str:
        if any(ord(c) < 32 for c in v):
            raise ValueError("control characters are not allowed")
        return v

    @model_validator(mode="after")
    def _check_kind(self) -> Self:
        if self.kind is LocatorKind.ROLE and self.value not in ARIA_ROLES:
            raise ValueError(f"unsupported ARIA role {self.value!r}")
        if self.kind is LocatorKind.CSS and any(t in self.value for t in ("javascript:", "<")):
            raise ValueError("unsupported CSS selector")
        return self

    def describe(self) -> str:
        if self.kind is LocatorKind.ROLE:
            return f"role={self.value}" + (f' name="{self.name}"' if self.name else "")
        return f'{self.kind.value}="{self.value}"'


class OpenPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=500)


class Click(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locator: Locator


class Fill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locator: Locator
    text: str = Field(max_length=500)


class Press(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locator: Locator
    key: str

    @field_validator("key")
    @classmethod
    def _allowed_key(cls, v: str) -> str:
        if v not in ALLOWED_KEYS:
            raise ValueError(f"key must be one of {sorted(ALLOWED_KEYS)}")
        return v


class SelectOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locator: Locator
    value: str = Field(min_length=1, max_length=200)


class WaitFor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locator: Locator
    state: Literal["visible", "hidden", "attached", "detached"] = "visible"
    timeout_ms: int = Field(default=3000, ge=100, le=10_000)


class ReadVisibleText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locator: Locator | None = None


class CaptureScreenshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9 _\-]+$")


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


BROWSER_ACTIONS: dict[str, type[BaseModel]] = {
    "open_page": OpenPage,
    "click": Click,
    "fill": Fill,
    "press": Press,
    "select_option": SelectOption,
    "reload_page": NoArgs,
    "go_back": NoArgs,
    "wait_for": WaitFor,
    "read_page_snapshot": NoArgs,
    "read_visible_text": ReadVisibleText,
    "read_current_url": NoArgs,
    "read_console_errors": NoArgs,
    "read_network_errors": NoArgs,
    "capture_screenshot": CaptureScreenshot,
}

# Actions that change page state; everything else only observes.
MUTATING_ACTIONS = frozenset(
    {"open_page", "click", "fill", "press", "select_option", "reload_page", "go_back"}
)
OBSERVATION_ACTIONS = frozenset(BROWSER_ACTIONS) - MUTATING_ACTIONS - {"wait_for"}
