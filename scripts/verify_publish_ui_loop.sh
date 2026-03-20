#!/usr/bin/env bash
set -euo pipefail

TITLE="${1:-MediaCrawler UI 发帖测试}"
DESC="${2:-这是UI自动化发帖最小闭环测试。}"

if command -v uv >/dev/null 2>&1; then
  uv run python -m tools.xhs_verify_publish_ui_loop --title "$TITLE" --desc "$DESC"
elif [ -x "/Users/hetingxin/PycharmProjects/MediaCrawler/.venv/bin/python" ]; then
  /Users/hetingxin/PycharmProjects/MediaCrawler/.venv/bin/python -m tools.xhs_verify_publish_ui_loop --title "$TITLE" --desc "$DESC"
else
  echo "Error: uv not found and .venv Python not available"
  exit 1
fi

