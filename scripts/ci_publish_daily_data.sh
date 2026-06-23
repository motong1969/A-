#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="${1:-daily-data}"
COMMIT_MESSAGE="${2:-daily select update}"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT INT TERM

ORIGIN_URL="$(git -C "$ROOT_DIR" remote get-url origin)"
if [[ -n "${GITHUB_TOKEN:-}" && -n "${GITHUB_REPOSITORY:-}" ]]; then
  ORIGIN_URL="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
fi

git init "$TMP_DIR" >/dev/null
git -C "$TMP_DIR" remote add origin "$ORIGIN_URL"

if git -C "$TMP_DIR" fetch origin "$BRANCH" >/dev/null 2>&1; then
  git -C "$TMP_DIR" checkout -B "$BRANCH" "origin/$BRANCH" >/dev/null 2>&1
else
  git -C "$TMP_DIR" checkout --orphan "$BRANCH" >/dev/null 2>&1
fi

find "$TMP_DIR" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
mkdir -p "$TMP_DIR/reports" "$TMP_DIR/history"

if [[ -d "$ROOT_DIR/reports" ]]; then
  cp -R "$ROOT_DIR/reports/." "$TMP_DIR/reports/"
fi
if [[ -d "$ROOT_DIR/history" ]]; then
  cp -R "$ROOT_DIR/history/." "$TMP_DIR/history/"
fi

git -C "$TMP_DIR" config user.name "github-actions[bot]"
git -C "$TMP_DIR" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git -C "$TMP_DIR" add reports history

if git -C "$TMP_DIR" diff --cached --quiet; then
  echo "No daily-data changes to publish."
  exit 0
fi

git -C "$TMP_DIR" commit -m "$COMMIT_MESSAGE" >/dev/null
git -C "$TMP_DIR" push origin "$BRANCH"

echo "Published reports/history to origin/$BRANCH."
