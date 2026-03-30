#!/usr/bin/env bash
# 微博发帖命令行入口
#
# 用法：
#   ./scripts/weibo_publish.sh text --content "今天天气真好 #分享#"
#   ./scripts/weibo_publish.sh image --content "分享几张图 #日常#" --images ./1.jpg,./2.jpg
#
# 所有参数直接透传给 tools/weibo_publish.py，详细帮助运行：
#   ./scripts/weibo_publish.sh --help

set -euo pipefail

if command -v uv >/dev/null 2>&1; then
  uv run python -m tools.weibo_publish "$@"
elif [ -x "$(dirname "$0")/../.venv/bin/python" ]; then
  "$(dirname "$0")/../.venv/bin/python" -m tools.weibo_publish "$@"
else
  echo '{"success":false,"error":"Python 环境未找到，请安装 uv 或创建 .venv"}' >&2
  exit 1
fi
