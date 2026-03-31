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

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel


class ZhihuTaskTypeEnum(str, Enum):
    """知乎任务类型"""
    PUBLISH_ARTICLE = "publish_article"
    PUBLISH_ANSWER = "publish_answer"


class ZhihuTaskStatusEnum(str, Enum):
    """知乎任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ZhihuTaskInfo(BaseModel):
    """知乎任务信息"""
    task_id: str
    task_type: ZhihuTaskTypeEnum
    status: ZhihuTaskStatusEnum
    created_at: datetime
    finished_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ZhihuPublishArticleRequest(BaseModel):
    """发布知乎专栏文章请求体"""
    title: str
    content: str
    topics: Optional[List[str]] = None


class ZhihuPublishAnswerRequest(BaseModel):
    """发布知乎回答请求体"""
    question_id: str
    content: str
