"""Deliberately ill-typed, but otherwise clean, Python fixture."""


def greeting(name: str) -> str:
    """Return an invalid greeting value for type-checking tests."""
    return len(name)
