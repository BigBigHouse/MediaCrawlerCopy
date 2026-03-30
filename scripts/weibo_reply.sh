#!/usr/bin/env bash
# 微博回复评论命令行入口
#
# 用法：
#   ./scripts/weibo_reply.sh --weibo-id <微博ID> --content "回复内容"
#   ./scripts/weibo_reply.sh --weibo-id <微博ID> --comment-id <评论ID> --content "回复内容"
#
# 参数说明：
#   --weibo-id    必填，目标微博 ID
#   --content     必填，回复内容
#   --comment-id  选填，要回复的评论 ID（为空则直接评论微博本身）

set -euo pipefail

if command -v uv >/dev/null 2>&1; then
  uv run python -m tools.weibo_reply_one_comment "$@"
elif [ -x "$(dirname "$0")/../.venv/bin/python" ]; then
  "$(dirname "$0")/../.venv/bin/python" -m tools.weibo_reply_one_comment "$@"
else
  echo '{"success":false,"error":"Python 环境未找到，请安装 uv 或创建 .venv"}' >&2
  exit 1
fi
