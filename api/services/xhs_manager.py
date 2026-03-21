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

from ..schemas.xhs import XhsTaskInfo, XhsTaskStatusEnum, XhsTaskTypeEnum

# 项目根目录
_PROJECT_ROOT = Path(__file__).parent.parent.parent
# 临时文件目录
_TEMP_BASE = _PROJECT_ROOT / "data" / "xhs_temp"
# 最大保留任务数
_MAX_TASKS = 100

# 查找 uv 可执行文件路径
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


class XhsOperationManager:
    """XHS 操作任务管理器（全局单例）。

    负责提交异步任务、调度子进程、查询任务状态。
    任务状态存储于内存 OrderedDict，最多保留 _MAX_TASKS 条记录。
    """

    def __init__(self) -> None:
        # 使用 OrderedDict 方便按插入顺序截断旧任务
        self._tasks: OrderedDict[str, XhsTaskInfo] = OrderedDict()

    # ------------------------------------------------------------------ #
    #  公开接口                                                             #
    # ------------------------------------------------------------------ #

    def submit_publish_task(
        self,
        note_type: str,
        title: str,
        desc: str,
        image_paths: Optional[List[str]] = None,
        video_path: Optional[str] = None,
        cover_path: Optional[str] = None,
        topics: Optional[List[str]] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """提交发布笔记任务，返回 task_id。

        调用方可通过 task_id 参数预先指定任务 ID（用于文件目录已按 task_id 命名的场景）。
        """
        task_id = task_id or str(uuid.uuid4())
        info = XhsTaskInfo(
            task_id=task_id,
            task_type=XhsTaskTypeEnum.PUBLISH,
            status=XhsTaskStatusEnum.PENDING,
            created_at=datetime.now(),
        )
        self._store_task(info)
        asyncio.create_task(
            self._run_publish(
                task_id=task_id,
                note_type=note_type,
                title=title,
                desc=desc,
                image_paths=image_paths or [],
                video_path=video_path,
                cover_path=cover_path,
                topics=topics or [],
            )
        )
        return task_id

    def submit_reply_task(
        self,
        note_id: str,
        comment_id: str,
        content: str,
        xsec_token: str = "",
        xsec_source: str = "",
    ) -> str:
        """提交回复评论任务，返回 task_id。"""
        task_id = str(uuid.uuid4())
        info = XhsTaskInfo(
            task_id=task_id,
            task_type=XhsTaskTypeEnum.REPLY,
            status=XhsTaskStatusEnum.PENDING,
            created_at=datetime.now(),
        )
        self._store_task(info)
        asyncio.create_task(
            self._run_reply(
                task_id=task_id,
                note_id=note_id,
                comment_id=comment_id,
                content=content,
                xsec_token=xsec_token,
                xsec_source=xsec_source,
            )
        )
        return task_id

    def get_task(self, task_id: str) -> Optional[XhsTaskInfo]:
        """查询单个任务信息，不存在返回 None。"""
        return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 20) -> List[XhsTaskInfo]:
        """查询最近任务列表（从最新到最旧）。"""
        tasks = list(self._tasks.values())
        tasks.reverse()
        return tasks[:limit]

    # ------------------------------------------------------------------ #
    #  内部实现                                                             #
    # ------------------------------------------------------------------ #

    def _store_task(self, info: XhsTaskInfo) -> None:
        """存储任务，超出上限时删除最旧的条目。"""
        self._tasks[info.task_id] = info
        while len(self._tasks) > _MAX_TASKS:
            self._tasks.popitem(last=False)

    def _update_task(self, task_id: str, **kwargs) -> None:
        """就地更新任务字段。"""
        info = self._tasks.get(task_id)
        if info is None:
            return
        updated = info.model_copy(update=kwargs)
        self._tasks[task_id] = updated

    async def _run_publish(
        self,
        task_id: str,
        note_type: str,
        title: str,
        desc: str,
        image_paths: List[str],
        video_path: Optional[str],
        cover_path: Optional[str],
        topics: List[str],
    ) -> None:
        """后台执行发布子进程。"""
        self._update_task(task_id, status=XhsTaskStatusEnum.RUNNING)

        cmd = [
            _UV_BIN, "run", "python", "tools/xhs_publish.py",
            note_type,
            "--title", title,
            "--desc", desc,
        ]

        if note_type == "image" and image_paths:
            cmd.extend(["--images", ",".join(image_paths)])
        elif note_type == "video":
            if video_path:
                cmd.extend(["--video", video_path])
            if cover_path:
                cmd.extend(["--cover", cover_path])

        if topics:
            cmd.extend(["--topics", ",".join(topics)])

        await self._exec_subprocess(task_id, cmd)

    async def _run_reply(
        self,
        task_id: str,
        note_id: str,
        comment_id: str,
        content: str,
        xsec_token: str,
        xsec_source: str,
    ) -> None:
        """后台执行回复评论子进程。"""
        self._update_task(task_id, status=XhsTaskStatusEnum.RUNNING)

        cmd = [
            _UV_BIN, "run", "python", "tools/xhs_reply_one_comment.py",
            "--note-id", note_id,
            "--comment-id", comment_id,
            "--content", content,
        ]
        if xsec_token:
            cmd.extend(["--xsec-token", xsec_token])
        if xsec_source:
            cmd.extend(["--xsec-source", xsec_source])

        await self._exec_subprocess(task_id, cmd)

    async def _exec_subprocess(self, task_id: str, cmd: List[str]) -> None:
        """通用子进程执行，捕获 stdout 解析 JSON，写回任务状态。"""
        try:
            # 确保子进程能导入项目根目录的模块（如 config、media_platform 等）
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
                # 尝试提取最后一行 JSON（子进程可能有多行输出）
                result = _extract_json(stdout_text)
                self._update_task(
                    task_id,
                    status=XhsTaskStatusEnum.SUCCESS,
                    finished_at=datetime.now(),
                    result=result,
                )
            else:
                error_msg = stderr_text or stdout_text or f"Exit code: {proc.returncode}"
                self._update_task(
                    task_id,
                    status=XhsTaskStatusEnum.FAILED,
                    finished_at=datetime.now(),
                    error=error_msg[:2000],
                )
        except Exception as exc:
            self._update_task(
                task_id,
                status=XhsTaskStatusEnum.FAILED,
                finished_at=datetime.now(),
                error=str(exc),
            )
        finally:
            _cleanup_temp_dir(task_id)


def _extract_json(text: str) -> Dict:
    """从 stdout 文本中提取 JSON，优先取最后一行，失败时返回原始文本包装。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {"raw": text[:1000]}


def _cleanup_temp_dir(task_id: str) -> None:
    """清理任务临时目录。"""
    task_dir = _TEMP_BASE / task_id
    if task_dir.exists():
        shutil.rmtree(task_dir, ignore_errors=True)


# 全局单例
xhs_manager = XhsOperationManager()
