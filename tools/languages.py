"""Canonical language integration names and selection validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

LEGACY_LANGUAGES = ("python", "cpp", "rust")
SUPPORTED_LANGUAGES = (*LEGACY_LANGUAGES, "typescript")


def normalize_languages(languages: Iterable[str]) -> tuple[str, ...]:
    """Validate and canonicalize a requested language set."""
    requested = set(languages)
    unknown = sorted(requested - set(SUPPORTED_LANGUAGES))
    if unknown:
        msg = f"unsupported bazel_devtools languages: {', '.join(unknown)}"
        raise ValueError(msg)
    if not requested:
        msg = "at least one bazel_devtools language must be selected"
        raise ValueError(msg)
    return tuple(language for language in SUPPORTED_LANGUAGES if language in requested)
