#!/usr/bin/env bash
set -uo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: clang_tidy_filter <clang-tidy> <external-header-manifest> <clang-tidy args...>" >&2
  exit 2
fi

clang_tidy=$1
external_headers=$2
shift 2

raw_output=$(mktemp)
filtered_output=$(mktemp)
trap 'rm -f "$raw_output" "$filtered_output"' EXIT

clang_tidy_status=0
"$clang_tidy" "$@" >"$raw_output" 2>&1 || clang_tidy_status=$?

awk -v external_headers="$external_headers" '
  BEGIN {
    while ((getline path < external_headers) > 0) {
      external[path] = 1
    }
    close(external_headers)
  }

  function is_external(path, candidate) {
    if (path in external) {
      return 1
    }
    for (candidate in external) {
      if (length(path) > length(candidate) &&
          substr(path, length(path) - length(candidate) + 1) == candidate) {
        return 1
      }
    }
    return 0
  }

  function flush() {
    if (keep) {
      printf "%s", block
    }
    block = ""
  }

  /^[0-9]+ (warnings?|errors?)( and [0-9]+ errors?)? generated\.$/ { next }
  /^Suppressed [0-9]+ warnings? \(.*\)\.$/ { next }
  /^Use -header-filter=.*$/ { next }
  /^[0-9]+ warnings? treated as errors?$/ { next }

  /^.+:[0-9]+:[0-9]+: (warning|error|fatal error): / {
    flush()
    path = $0
    sub(/:[0-9]+:[0-9]+: (warning|error|fatal error): .*/, "", path)
    keep = !is_external(path) || $0 ~ /\[clang-diagnostic-error/
    block = $0 ORS
    next
  }

  /^(warning|error|fatal error): .*\[[^]]+\]$/ {
    flush()
    keep = ($0 ~ /\[clang-diagnostic-/)
    block = $0 ORS
    next
  }

  {
    if (block != "") {
      block = block $0 ORS
    } else {
      print
    }
  }

  END { flush() }
' "$raw_output" >"$filtered_output"

cat "$filtered_output"
if [[ $clang_tidy_status -ne 0 && -s $filtered_output ]]; then
  exit "$clang_tidy_status"
fi
