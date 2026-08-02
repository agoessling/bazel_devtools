"""Tests for the example Python greeting library."""

from python.greeting import greeting


def test_greeting() -> None:
    """The greeting includes the supplied name."""
    assert greeting("Bazel") == "Hello, Bazel!"
