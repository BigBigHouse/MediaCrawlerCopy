#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <content> [keyword] [max_notes_try]"
  exit 1
fi

CONTENT="$1"
KEYWORD="${2:-}"
MAX_NOTES_TRY="${3:-5}"

if command -v uv >/dev/null 2>&1; then
  uv run python -m tools.xhs_verify_reply_loop \
    --content "$CONTENT" \
    --keyword "$KEYWORD" \
    --max-notes-try "$MAX_NOTES_TRY"
elif [ -x "/Users/hetingxin/PycharmProjects/MediaCrawler/.venv/bin/python" ]; then
  /Users/hetingxin/PycharmProjects/MediaCrawler/.venv/bin/python -m tools.xhs_verify_reply_loop \
    --content "$CONTENT" \
    --keyword "$KEYWORD" \
    --max-notes-try "$MAX_NOTES_TRY"
else
  echo "Error: uv not found and .venv Python not available"
  exit 1
fi

