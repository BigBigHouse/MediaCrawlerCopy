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

from ..schemas.xhs import XhsReplyRequest, XhsTaskInfo
from ..services.xhs_manager import _TEMP_BASE, xhs_manager

router = APIRouter(tags=["XHS Operations"])


@router.post("/xhs/publish", response_model=dict, summary="提交发布笔记任务")
async def publish_note(
    note_type: str = Form(..., description="笔记类型：image 或 video"),
    title: str = Form(..., description="笔记标题（建议不超过 20 字）"),
    desc: str = Form(..., description="笔记正文"),
    topics: Optional[str] = Form(None, description="话题标签，逗号分隔，如 美食,旅行"),
    files: List[UploadFile] = File(default=[], description="图文：1~18张图片；视频：1个mp4/mov"),
    cover: Optional[UploadFile] = File(default=None, description="视频封面图（可选）"),
):
    """提交小红书发布笔记任务（异步），返回 task_id 供后续轮询。"""
    if note_type not in ("image", "video"):
        raise HTTPException(status_code=400, detail="note_type 必须为 image 或 video")
    if note_type == "image" and not files:
        raise HTTPException(status_code=400, detail="图文笔记必须上传至少一张图片")
    if note_type == "video" and not files:
        raise HTTPException(status_code=400, detail="视频笔记必须上传视频文件")

    # 预分配 task_id，文件直接写到 data/xhs_temp/{task_id}/
    task_id = str(uuid.uuid4())
    task_dir = _TEMP_BASE / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    image_paths: List[str] = []
    video_path: Optional[str] = None
    cover_path: Optional[str] = None

    try:
        if note_type == "image":
            for upload in files:
                filename = _safe_filename(upload.filename or "image.jpg")
                dest = task_dir / filename
                dest.write_bytes(await upload.read())
                image_paths.append(str(dest))
        else:
            video_file = files[0]
            filename = _safe_filename(video_file.filename or "video.mp4")
            dest = task_dir / filename
            dest.write_bytes(await video_file.read())
            video_path = str(dest)

            if cover:
                cover_filename = _safe_filename(cover.filename or "cover.jpg")
                cover_dest = task_dir / cover_filename
                cover_dest.write_bytes(await cover.read())
                cover_path = str(cover_dest)

        topics_list = [t.strip() for t in topics.split(",")] if topics else []

        xhs_manager.submit_publish_task(
            note_type=note_type,
            title=title,
            desc=desc,
            image_paths=image_paths,
            video_path=video_path,
            cover_path=cover_path,
            topics=topics_list,
            task_id=task_id,
        )

        return {"task_id": task_id, "status": "pending"}

    except HTTPException:
        raise
    except Exception as exc:
        import shutil
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/xhs/reply", response_model=dict, summary="提交回复评论任务")
async def reply_comment(req: XhsReplyRequest):
    """提交小红书回复评论任务（异步），返回 task_id 供后续轮询。"""
    task_id = xhs_manager.submit_reply_task(
        note_id=req.note_id,
        comment_id=req.comment_id,
        content=req.content,
        xsec_token=req.xsec_token,
        xsec_source=req.xsec_source,
    )
    return {"task_id": task_id, "status": "pending"}


@router.get("/xhs/tasks", response_model=List[XhsTaskInfo], summary="查询最近任务列表")
async def list_tasks(limit: int = 20):
    """查询最近提交的 XHS 任务列表（从最新到最旧）。"""
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit 范围为 1~100")
    return xhs_manager.list_tasks(limit=limit)


@router.get("/xhs/tasks/{task_id}", response_model=XhsTaskInfo, summary="查询单个任务状态")
async def get_task(task_id: str):
    """查询指定 task_id 的任务状态和结果。"""
    info = xhs_manager.get_task(task_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id!r} 不存在")
    return info


def _safe_filename(filename: str) -> str:
    """去除路径分隔符，防止路径穿越。"""
    return os.path.basename(filename) or "upload"
