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

import os
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..schemas.weibo import WeiboReplyRequest, WeiboTaskInfo
from ..services.weibo_manager import _TEMP_BASE, weibo_manager

router = APIRouter(tags=["Weibo Operations"])


@router.post("/weibo/publish", response_model=dict, summary="提交发布微博任务")
async def publish_weibo(
    weibo_type: str = Form(..., description="发布类型：text（纯文字）或 image（图文）"),
    content: str = Form(..., description="微博正文（话题用 #话题# 格式）"),
    files: List[UploadFile] = File(default=[], description="图文微博图片（最多 9 张）"),
):
    """提交微博发布任务（异步），返回 task_id 供后续轮询。"""
    if weibo_type not in ("text", "image"):
        raise HTTPException(status_code=400, detail="weibo_type 必须为 text 或 image")
    if weibo_type == "image" and not files:
        raise HTTPException(status_code=400, detail="图文微博必须上传至少一张图片")

    task_id = str(uuid.uuid4())
    task_dir = _TEMP_BASE / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    image_paths: List[str] = []

    try:
        if weibo_type == "image":
            for upload in files:
                filename = _safe_filename(upload.filename or "image.jpg")
                dest = task_dir / filename
                dest.write_bytes(await upload.read())
                image_paths.append(str(dest))

        weibo_manager.submit_publish_task(
            weibo_type=weibo_type,
            content=content,
            image_paths=image_paths,
            task_id=task_id,
        )
        return {"task_id": task_id, "status": "pending"}

    except HTTPException:
        raise
    except Exception as exc:
        import shutil
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/weibo/reply", response_model=dict, summary="提交回复微博评论任务")
async def reply_comment(req: WeiboReplyRequest):
    """提交微博回复评论任务（异步），返回 task_id 供后续轮询。"""
    task_id = weibo_manager.submit_reply_task(
        weibo_id=req.weibo_id,
        content=req.content,
        comment_id=req.comment_id,
    )
    return {"task_id": task_id, "status": "pending"}


@router.get("/weibo/tasks", response_model=List[WeiboTaskInfo], summary="查询最近任务列表")
async def list_tasks(limit: int = 20):
    """查询最近提交的微博任务列表（从最新到最旧）。"""
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit 范围为 1~100")
    return weibo_manager.list_tasks(limit=limit)


@router.get("/weibo/tasks/{task_id}", response_model=WeiboTaskInfo, summary="查询单个任务状态")
async def get_task(task_id: str):
    """查询指定 task_id 的任务状态和结果。"""
    info = weibo_manager.get_task(task_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id!r} 不存在")
    return info


def _safe_filename(filename: str) -> str:
    """去除路径分隔符，防止路径穿越。"""
    return os.path.basename(filename) or "upload"
