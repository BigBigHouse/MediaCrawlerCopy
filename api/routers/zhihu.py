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

from ..schemas.zhihu import ZhihuTaskInfo
from ..services.zhihu_manager import _TEMP_BASE, zhihu_manager

router = APIRouter(tags=["Zhihu Operations"])


@router.post("/zhihu/publish/article", response_model=dict, summary="提交发布知乎专栏文章任务")
async def publish_article(
    title: str = Form(..., description="文章标题"),
    content: str = Form(..., description="正文内容（支持 HTML 格式）"),
    topics: Optional[str] = Form(None, description="话题，多个用英文逗号分隔"),
    files: List[UploadFile] = File(default=[], description="文章图片"),
):
    """提交知乎文章发布任务（异步），返回 task_id 供后续轮询。"""
    task_id = str(uuid.uuid4())
    task_dir = _TEMP_BASE / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    image_paths: List[str] = []
    topic_list: List[str] = []

    try:
        if topics:
            topic_list = [t.strip() for t in topics.split(",") if t.strip()]

        for upload in files:
            filename = _safe_filename(upload.filename or "image.jpg")
            dest = task_dir / filename
            dest.write_bytes(await upload.read())
            image_paths.append(str(dest))

        zhihu_manager.submit_publish_article_task(
            title=title,
            content=content,
            topics=topic_list or None,
            image_paths=image_paths or None,
            task_id=task_id,
        )
        return {"task_id": task_id, "status": "pending"}

    except HTTPException:
        raise
    except Exception as exc:
        import shutil
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/zhihu/publish/answer", response_model=dict, summary="提交发布知乎回答任务")
async def publish_answer(
    question_id: str = Form(..., description="知乎问题 ID"),
    content: str = Form(..., description="回答内容（支持 HTML 格式）"),
    files: List[UploadFile] = File(default=[], description="回答图片"),
):
    """提交知乎回答发布任务（异步），返回 task_id 供后续轮询。"""
    task_id = str(uuid.uuid4())
    task_dir = _TEMP_BASE / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    image_paths: List[str] = []

    try:
        for upload in files:
            filename = _safe_filename(upload.filename or "image.jpg")
            dest = task_dir / filename
            dest.write_bytes(await upload.read())
            image_paths.append(str(dest))

        zhihu_manager.submit_publish_answer_task(
            question_id=question_id,
            content=content,
            image_paths=image_paths or None,
            task_id=task_id,
        )
        return {"task_id": task_id, "status": "pending"}

    except HTTPException:
        raise
    except Exception as exc:
        import shutil
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/zhihu/tasks", response_model=List[ZhihuTaskInfo], summary="查询知乎最近任务列表")
async def list_tasks(limit: int = 20):
    """查询最近提交的知乎任务列表（从最新到最旧）。"""
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit 范围为 1~100")
    return zhihu_manager.list_tasks(limit=limit)


@router.get("/zhihu/tasks/{task_id}", response_model=ZhihuTaskInfo, summary="查询单个知乎任务状态")
async def get_task(task_id: str):
    """查询指定 task_id 的知乎任务状态和结果。"""
    info = zhihu_manager.get_task(task_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id!r} 不存在")
    return info


def _safe_filename(filename: str) -> str:
    """去除路径分隔符，防止路径穿越。"""
    return os.path.basename(filename) or "upload"
