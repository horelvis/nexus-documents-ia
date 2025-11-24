#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/create_pre_tag.sh [<base_version>] [--push]

Creates the next PRE deployment tag following the SemVer pattern vX.Y.Z-pre.N.

Arguments:
  <base_version>  Optional SemVer (e.g., 1.4.0). If omitted, the script reads
                  the version from frontend/package.json.
  --push          Pushes the newly created tag to origin automatically.

Examples:
  scripts/create_pre_tag.sh 1.4.0
  scripts/create_pre_tag.sh --push
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

BASE_VERSION=""
PUSH_TAG="false"

for arg in "$@"; do
  case "$arg" in
    --push)
      PUSH_TAG="true"
      ;;
    *)
      if [[ -n "$BASE_VERSION" ]]; then
        echo "Unexpected argument: $arg" >&2
        usage
        exit 1
      fi
      BASE_VERSION="$arg"
      ;;
  esac
done

if [[ -z "$BASE_VERSION" ]]; then
  if command -v jq >/dev/null 2>&1; then
    BASE_VERSION=$(jq -r '.version' frontend/package.json)
  else
    BASE_VERSION=$(grep -m1 '"version"' frontend/package.json | sed -E 's/.*"version": *"([^"]+)".*/\1/')
  fi
fi

if ! [[ "$BASE_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid base version '$BASE_VERSION'. Expected SemVer format X.Y.Z" >&2
  exit 1
fi

LATEST_TAG=$(git tag --list "v${BASE_VERSION}-pre.*" | sort -V | tail -n1)

if [[ -z "$LATEST_TAG" ]]; then
  NEXT_PRE="1"
else
  CURRENT_PRE=${LATEST_TAG##*-pre.}
  if ! [[ "$CURRENT_PRE" =~ ^[0-9]+$ ]]; then
    echo "Latest tag '$LATEST_TAG' has unexpected format." >&2
    exit 1
  fi
  NEXT_PRE=$((CURRENT_PRE + 1))
fi

NEW_TAG="v${BASE_VERSION}-pre.${NEXT_PRE}"
TAG_MESSAGE="PRE env release ${BASE_VERSION} pre.${NEXT_PRE}"

echo "Creating tag ${NEW_TAG}"
git tag -a "${NEW_TAG}" -m "${TAG_MESSAGE}"

if [[ "$PUSH_TAG" == "true" ]]; then
  echo "Pushing ${NEW_TAG} to origin"
  git push origin "${NEW_TAG}"
else
  echo "Tag ${NEW_TAG} created locally. Run 'git push origin ${NEW_TAG}' when ready."
fi
