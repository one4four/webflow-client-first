#!/usr/bin/env bash
# Sets up a fresh copy of this starter for one Webflow project:
# writes .mcp.json with a project-scoped Webflow MCP server and fills PROJECT.md.
# Holds no secrets: the Webflow sign-in is OAuth, stored locally by Claude Code.
#
# Usage (run from the copy's root folder):
#   scripts/new-project.sh --slug opd --name "OPD Project" [--client "One4Four"] \
#     [--site "OPD Project"] [--staging https://opd-prototype.webflow.io] [--eu] [--force]
# Any value left out is asked for. Unknown values can stay blank and be filled later.
set -euo pipefail

cd "$(dirname "$0")/.."

SLUG="" NAME="" CLIENT="" SITE="" STAGING="" REGION="US" FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --slug) SLUG="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --client) CLIENT="$2"; shift 2 ;;
    --site) SITE="$2"; shift 2 ;;
    --staging) STAGING="$2"; shift 2 ;;
    --eu) REGION="EU"; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) sed -n 2,10p "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

ask() { # ask VAR "Question"
  local __var="$1" __q="$2" __a
  if [ -z "${!__var}" ] && [ -t 0 ]; then read -r -p "$__q " __a; printf -v "$__var" '%s' "$__a"; fi
}
ask NAME   "Project name (e.g. OPD Project):"
ask SLUG   "Short slug for the MCP server, lowercase and hyphens (e.g. opd):"
ask CLIENT "Client name:"
ask SITE   "Webflow site name (blank if not created yet):"
ask STAGING "Staging URL, e.g. https://name.webflow.io (blank if unknown):"

SLUG="$(printf '%s' "$SLUG" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-\n' '-' | sed 's/^-*//;s/-*$//')"
if [ -z "$SLUG" ] || [ -z "$NAME" ]; then
  echo "A project name and slug are required." >&2; exit 1
fi

if [ -f .mcp.json ] && [ "$FORCE" -ne 1 ]; then
  echo ".mcp.json already exists. Re-run with --force to replace it." >&2; exit 1
fi
if ! grep -q '{{PROJECT_SLUG}}' PROJECT.md && [ "$FORCE" -ne 1 ]; then
  echo "PROJECT.md is already filled in. Re-run with --force only if you mean to start over." >&2; exit 1
fi

if [ "$REGION" = "EU" ]; then URL="https://mcp.eu.webflow.com/mcp"; else URL="https://mcp.webflow.com/mcp"; fi

export PROJECT_SLUG="$SLUG" PROJECT_SLUG_UNDERSCORE="${SLUG//-/_}" PROJECT_NAME="$NAME" \
  CLIENT_NAME="${CLIENT:-TBD}" WEBFLOW_SITE_NAME="${SITE:-TBD}" WEBFLOW_STAGING_URL="${STAGING:-TBD}" \
  WEBFLOW_REGION="$REGION" WEBFLOW_MCP_URL="$URL" WEBFLOW_SITE_ID="TBD (Claude fills this after sign-in)" \
  WEBFLOW_WORKSPACE="TBD" BRAND_LINK="TBD" LOCAL_FOLDER="$(pwd)" \
  SETUP_STATUS="Config written $(date +%Y-%m-%d). Sign-in and connection test not done yet."

fill() { # fill SRC DEST: replace every {{KEY}} with $KEY from the environment
  perl -pe 's/\{\{([A-Z_]+)\}\}/exists $ENV{$1} ? $ENV{$1} : "{{$1}}"/ge' "$1" > "$2.tmp" && mv "$2.tmp" "$2"
}
fill templates/mcp.json .mcp.json
fill templates/PROJECT.md PROJECT.md

cat <<MSG

Done. Wrote .mcp.json (server "webflow-$SLUG", $URL) and filled PROJECT.md.

Next, in Terminal:
  cd "$(pwd)"
  claude
Then: choose "Use this MCP server", type /mcp, pick webflow-$SLUG, choose Authenticate,
and tick ONLY this project's site. Then open the site in the Designer, press E and launch
the MCP Bridge App. Ask Claude to "finish the new project setup" and it runs the test.
Full steps: docs/webflow-project-connection.md
MSG
