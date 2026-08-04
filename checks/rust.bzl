"""Public Rust check factories without loading other language integrations."""

load(
    "@rules_rust//rust:defs.bzl",
    _rust_clippy_aspect = "rust_clippy_aspect",
    _rustfmt_aspect = "rustfmt_aspect",
)

rust_clippy_aspect = _rust_clippy_aspect
rustfmt_aspect = _rustfmt_aspect
