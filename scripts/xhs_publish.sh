#!/usr/bin/env bash
# 小红书发帖命令行入口
#
# 用法：
#   ./scripts/xhs_publish.sh image --title "标题" --desc "正文" --images ./img.jpg
#   ./scripts/xhs_publish.sh image --title "标题" --desc "正文" --images ./1.jpg,./2.jpg --topics "日常,分享"
#   ./scripts/xhs_publish.sh video --title "标题" --desc "正文" --video ./clip.mp4 --cover ./cover.jpg
#
# 所有参数直接透传给 tools/xhs_publish.py，详细帮助运行：
#   ./scripts/xhs_publish.sh --help

set -euo pipefail

if command -v uv >/dev/null 2>&1; then
  uv run python -m tools.xhs_publish "$@"
elif [ -x "$(dirname "$0")/../.venv/bin/python" ]; then
  "$(dirname "$0")/../.venv/bin/python" -m tools.xhs_publish "$@"
else
  echo '{"success":false,"error":"Python 环境未找到，请安装 uv 或创建 .venv"}' >&2
  exit 1
fi
