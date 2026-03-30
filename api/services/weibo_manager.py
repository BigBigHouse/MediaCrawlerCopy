# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

import asyncio
import json
import os
import shutil
import uuid
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..schemas.weibo import WeiboTaskInfo, WeiboTaskStatusEnum, WeiboTaskTypeEnum

# 项目根目录
_PROJECT_ROOT = Path(__file__).parent.parent.parent
# 临时文件目录
_TEMP_BASE = _PROJECT_ROOT / "data" / "weibo_temp"
# 最大保留任务数
_MAX_TASKS = 100


def _find_uv() -> str:
    """查找 uv 可执行文件的完整路径。"""
    candidates = [
        shutil.which("uv"),
        os.path.expanduser("~/.local/bin/uv"),
        os.path.expanduser("~/.cargo/bin/uv"),
        "/usr/local/bin/uv",
    ]
    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    raise FileNotFoundError("找不到 uv 可执行文件，请确认已安装 uv 并在 PATH 中")


_UV_BIN = _find_uv()


class WeiboOperationManager:
    """微博操作任务管理器（全局单例）。

    负责提交异步任务、调度子进程、查询任务状态。
    任务状态存储于内存 OrderedDict，最多保留 _MAX_TASKS 条记录。
    """

    def __init__(self) -> None:
        self._tasks: OrderedDict[str, WeiboTaskInfo] = OrderedDict()

    # ------------------------------------------------------------------ #
    #  公开接口                                                             #
    # ------------------------------------------------------------------ #

    def submit_publish_task(
        self,
        weibo_type: str,
        content: str,
        image_paths: Optional[List[str]] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """提交发布微博任务，返回 task_id。"""
        task_id = task_id or str(uuid.uuid4())
        info = WeiboTaskInfo(
            task_id=task_id,
            task_type=WeiboTaskTypeEnum.PUBLISH,
            status=WeiboTaskStatusEnum.PENDING,
            created_at=datetime.now(),
        )
        self._store_task(info)
        asyncio.create_task(
            self._run_publish(
                task_id=task_id,
                weibo_type=weibo_type,
                content=content,
                image_paths=image_paths or [],
            )
        )
        return task_id

    def submit_reply_task(
        self,
        weibo_id: str,
        content: str,
        comment_id: str = "",
    ) -> str:
        """提交回复评论任务，返回 task_id。"""
        task_id = str(uuid.uuid4())
        info = WeiboTaskInfo(
            task_id=task_id,
            task_type=WeiboTaskTypeEnum.REPLY,
            status=WeiboTaskStatusEnum.PENDING,
            created_at=datetime.now(),
        )
        self._store_task(info)
        asyncio.create_task(
            self._run_reply(
                task_id=task_id,
                weibo_id=weibo_id,
                content=content,
                comment_id=comment_id,
            )
        )
        return task_id

    def get_task(self, task_id: str) -> Optional[WeiboTaskInfo]:
        """查询单个任务信息，不存在返回 None。"""
        return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 20) -> List[WeiboTaskInfo]:
        """查询最近任务列表（从最新到最旧）。"""
        tasks = list(self._tasks.values())
        tasks.reverse()
        return tasks[:limit]

    # ------------------------------------------------------------------ #
    #  内部实现                                                             #
    # ------------------------------------------------------------------ #

    def _store_task(self, info: WeiboTaskInfo) -> None:
        self._tasks[info.task_id] = info
        while len(self._tasks) > _MAX_TASKS:
            self._tasks.popitem(last=False)

    def _update_task(self, task_id: str, **kwargs) -> None:
        info = self._tasks.get(task_id)
        if info is None:
            return
        self._tasks[task_id] = info.model_copy(update=kwargs)

    async def _run_publish(
        self,
        task_id: str,
        weibo_type: str,
        content: str,
        image_paths: List[str],
    ) -> None:
        """后台执行发布子进程。"""
        self._update_task(task_id, status=WeiboTaskStatusEnum.RUNNING)

        cmd = [
            _UV_BIN, "run", "python", "tools/weibo_publish.py",
            weibo_type,
            "--content", content,
        ]
        if weibo_type == "image" and image_paths:
            cmd.extend(["--images", ",".join(image_paths)])

        await self._exec_subprocess(task_id, cmd)

    async def _run_reply(
        self,
        task_id: str,
        weibo_id: str,
        content: str,
        comment_id: str,
    ) -> None:
        """后台执行回复评论子进程。"""
        self._update_task(task_id, status=WeiboTaskStatusEnum.RUNNING)

        cmd = [
            _UV_BIN, "run", "python", "tools/weibo_reply_one_comment.py",
            "--weibo-id", weibo_id,
            "--content", content,
        ]
        if comment_id:
            cmd.extend(["--comment-id", comment_id])

        await self._exec_subprocess(task_id, cmd)

    async def _exec_subprocess(self, task_id: str, cmd: List[str]) -> None:
        """通用子进程执行，捕获 stdout 解析 JSON，写回任务状态。"""
        try:
            env = {
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                "PYTHONPATH": str(_PROJECT_ROOT),
            }
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_PROJECT_ROOT),
                env=env,
            )
            stdout, stderr = await proc.communicate()

            stdout_text = stdout.decode("utf-8", errors="ignore").strip()
            stderr_text = stderr.decode("utf-8", errors="ignore").strip()

            if proc.returncode == 0 and stdout_text:
                result = _extract_json(stdout_text)
                # 把 stderr 日志也挂到 result 里，方便调试
                if stderr_text:
                    result["_stderr"] = stderr_text[-2000:]
                self._update_task(
                    task_id,
                    status=WeiboTaskStatusEnum.SUCCESS,
                    finished_at=datetime.now(),
                    result=result,
                )
            else:
                error_msg = stderr_text or stdout_text or f"Exit code: {proc.returncode}"
                self._update_task(
                    task_id,
                    status=WeiboTaskStatusEnum.FAILED,
                    finished_at=datetime.now(),
                    error=error_msg[:2000],
                )
        except Exception as exc:
            self._update_task(
                task_id,
                status=WeiboTaskStatusEnum.FAILED,
                finished_at=datetime.now(),
                error=str(exc),
            )
        finally:
            _cleanup_temp_dir(task_id)


def _extract_json(text: str) -> Dict:
    """从 stdout 文本中提取 JSON，优先取最后一行。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {"raw": text[:1000]}


def _cleanup_temp_dir(task_id: str) -> None:
    task_dir = _TEMP_BASE / task_id
    if task_dir.exists():
        shutil.rmtree(task_dir, ignore_errors=True)


# 全局单例
weibo_manager = WeiboOperationManager()
