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
from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel


class WeiboTaskTypeEnum(str, Enum):
    """微博任务类型"""
    PUBLISH = "publish"
    REPLY = "reply"


class WeiboTaskStatusEnum(str, Enum):
    """微博任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class WeiboTaskInfo(BaseModel):
    """微博任务信息"""
    task_id: str
    task_type: WeiboTaskTypeEnum
    status: WeiboTaskStatusEnum
    created_at: datetime
    finished_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WeiboPublishRequest(BaseModel):
    """发布微博请求体（纯文字场景，图文通过 multipart 传）"""
    content: str


class WeiboReplyRequest(BaseModel):
    """回复微博评论请求体"""
    weibo_id: str
    content: str
    comment_id: str = ""
