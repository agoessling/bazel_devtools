"""Deliberately ill-typed, but otherwise clean, Python fixture."""


def greeting(name: str) -> str:
    """Exercise a type error without changing the runtime return type."""
    _invalid_assignment: str = 42
    return f"Hello, {name}!"
