#!/bin/sh
set -eu

actionlint="$1"
pre_commit="$2"
pre_commit_config="$3"
shift 3

"$pre_commit" validate-config "$pre_commit_config"
"$actionlint" "$@"
