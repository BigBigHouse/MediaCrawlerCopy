#!/usr/bin/env bash
set -euo pipefail

if command -v uv >/dev/null 2>&1; then
  uv run python -m tools.xhs_sniff_upload_api
elif [ -x "/Users/hetingxin/PycharmProjects/MediaCrawler/.venv/bin/python" ]; then
  /Users/hetingxin/PycharmProjects/MediaCrawler/.venv/bin/python -m tools.xhs_sniff_upload_api
else
  echo "Error: uv not found and .venv Python not available"
  exit 1
fi
