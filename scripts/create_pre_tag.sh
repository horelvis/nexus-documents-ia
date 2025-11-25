#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/create_pre_tag.sh [<base_version>] [--push] [--service <backend|frontend>]

Creates the next PRE deployment tag following the SemVer pattern <service>-vX.Y.Z-pre.N.

Arguments:
  <base_version>  Optional SemVer (e.g., 1.4.0). If omitted, the script reads
                  the version from frontend/package.json.
  --push          Pushes the newly created tag to origin automatically.
  --service       Target service (backend or frontend). Defaults to frontend.

Examples:
  scripts/create_pre_tag.sh 1.4.0 --service backend
  scripts/create_pre_tag.sh --push --service frontend
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

BASE_VERSION=""
PUSH_TAG="false"
SERVICE="frontend"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push)
      PUSH_TAG="true"
      shift
      ;;
    --service)
      if [[ $# -lt 2 ]]; then
        echo "Error: --service requires a value (backend or frontend)" >&2
        exit 1
      fi
      SERVICE="$2"
      shift 2
      ;;
    --service=*)
      SERVICE="${1#*=}"
      shift
      ;;
    -*)
      echo "Unexpected option: $1" >&2
      usage
      exit 1
      ;;
    *)
      if [[ -n "$BASE_VERSION" ]]; then
        echo "Base version already specified as '$BASE_VERSION'. Unexpected extra argument '$1'." >&2
        usage
        exit 1
      fi
      BASE_VERSION="$1"
      shift
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

if [[ "$SERVICE" != "backend" && "$SERVICE" != "frontend" ]]; then
  echo "Invalid service '$SERVICE'. Expected 'backend' or 'frontend'." >&2
  exit 1
fi

TAG_PREFIX="${SERVICE}-"
TAG_GLOB="${TAG_PREFIX}v${BASE_VERSION}-pre.*"

LATEST_TAG=$(git tag --list "$TAG_GLOB" | sort -V | tail -n1)

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

NEW_TAG="${TAG_PREFIX}v${BASE_VERSION}-pre.${NEXT_PRE}"
TAG_MESSAGE="PRE ${SERVICE} release ${BASE_VERSION} pre.${NEXT_PRE}"

echo "Creating tag ${NEW_TAG}"
git tag -a "${NEW_TAG}" -m "${TAG_MESSAGE}"

if [[ "$PUSH_TAG" == "true" ]]; then
  echo "Pushing ${NEW_TAG} to origin"
  git push origin "${NEW_TAG}"
else
  echo "Tag ${NEW_TAG} created locally. Run 'git push origin ${NEW_TAG}' when ready."
fi
