#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="${1:-daily-data}"

cd "$ROOT_DIR"
mkdir -p reports history

if ! git fetch origin "$BRANCH":"refs/remotes/origin/$BRANCH" >/dev/null 2>&1; then
  echo "No remote branch '$BRANCH' found. Starting with empty reports/history."
  exit 0
fi

for path in reports history; do
  if git cat-file -e "origin/$BRANCH:$path" 2>/dev/null; then
    git checkout "origin/$BRANCH" -- "$path"
  fi
done

echo "Restored reports/history from origin/$BRANCH."
