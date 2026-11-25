#!/usr/bin/env bash
# Refreshes this project's copy of the build standard from the starter repo
# (one4four/webflow-client-first, main). Replaces only the rule files; PROJECT.md,
# .mcp.json and anything else project-specific is left alone. Review with
# `git diff --staged`, then commit.
set -euo pipefail
cd "$(dirname "$0")/.."

UPSTREAM_URL="https://github.com/one4four/webflow-client-first.git"
RULE_PATHS=(CLAUDE.md README.md SKILL.md docs views reference templates scripts)

git remote get-url upstream >/dev/null 2>&1 || git remote add upstream "$UPSTREAM_URL"
git fetch upstream main
git checkout upstream/main -- "${RULE_PATHS[@]}"
echo "Rule files updated from the starter. Review with: git diff --staged"
