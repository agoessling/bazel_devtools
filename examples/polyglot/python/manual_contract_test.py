"""Manual test fixture that fails if Bazel executes it implicitly."""


def main() -> int:
    """Return failure so the integration test detects accidental execution."""
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
