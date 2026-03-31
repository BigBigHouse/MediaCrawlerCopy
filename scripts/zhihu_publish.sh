#!/usr/bin/env bash
# 知乎发帖命令行入口
#
# 用法：
#   ./scripts/zhihu_publish.sh article --title "文章标题" --content "<p>正文</p>"
#   ./scripts/zhihu_publish.sh answer --question-id "12345678" --content "<p>回答</p>"
#
# 所有参数直接透传给 tools/zhihu_publish.py，详细帮助运行：
#   ./scripts/zhihu_publish.sh --help

set -euo pipefail

if command -v uv >/dev/null 2>&1; then
  uv run python -m tools.zhihu_publish "$@"
elif [ -x "$(dirname "$0")/../.venv/bin/python" ]; then
  "$(dirname "$0")/../.venv/bin/python" -m tools.zhihu_publish "$@"
else
  echo '{"success":false,"error":"Python 环境未找到，请安装 uv 或创建 .venv"}' >&2
  exit 1
fi
