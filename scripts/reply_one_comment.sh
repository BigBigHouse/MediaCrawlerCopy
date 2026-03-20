#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "Usage: $0 <note_id> <comment_id> <content> [xsec_token] [xsec_source]"
  exit 1
fi

NOTE_ID="$1"
COMMENT_ID="$2"
CONTENT="$3"
XSEC_TOKEN="${4:-}"
XSEC_SOURCE="${5:-}"

if command -v uv >/dev/null 2>&1; then
  uv run python -m tools.xhs_reply_one_comment \
    --note-id "$NOTE_ID" \
    --comment-id "$COMMENT_ID" \
    --content "$CONTENT" \
    --xsec-token "$XSEC_TOKEN" \
    --xsec-source "$XSEC_SOURCE"
elif [ -x "/Users/hetingxin/PycharmProjects/MediaCrawler/.venv/bin/python" ]; then
  /Users/hetingxin/PycharmProjects/MediaCrawler/.venv/bin/python -m tools.xhs_reply_one_comment \
    --note-id "$NOTE_ID" \
    --comment-id "$COMMENT_ID" \
    --content "$CONTENT" \
    --xsec-token "$XSEC_TOKEN" \
    --xsec-source "$XSEC_SOURCE"
else
  echo "Error: uv not found and .venv Python not available"
  exit 1
fi

