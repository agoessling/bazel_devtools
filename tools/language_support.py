"""Read the language integrations selected by setup."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from tools.languages import SUPPORTED_LANGUAGES, normalize_languages

_STATE_PATH = Path(".bazel_devtools/state.json")


def configured_languages(workspace: Path) -> tuple[str, ...]:
    """Return setup's canonical language selection, defaulting legacy installs to all."""
    path = workspace / _STATE_PATH
    if not path.exists():
        return SUPPORTED_LANGUAGES
    try:
        decoded: object = json.loads(  # pyright: ignore[reportAny]
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        msg = f"cannot read bazel_devtools language selection from {path}: {error}"
        raise RuntimeError(msg) from error
    if not isinstance(decoded, dict):
        msg = f"bazel_devtools state in {path} is not a JSON object"
        raise TypeError(msg)
    state = cast("dict[object, object]", decoded)
    raw_languages = state.get("languages", list(SUPPORTED_LANGUAGES))
    if not isinstance(raw_languages, list):
        msg = f"bazel_devtools state in {path} has an invalid language selection"
        raise TypeError(msg)
    language_values = cast("list[object]", raw_languages)
    if not all(isinstance(language, str) for language in language_values):
        msg = f"bazel_devtools state in {path} has an invalid language selection"
        raise TypeError(msg)
    try:
        return normalize_languages(cast("list[str]", language_values))
    except ValueError as error:
        msg = f"bazel_devtools state in {path} has an invalid language selection: {error}"
        raise RuntimeError(msg) from error
