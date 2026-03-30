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

"""微博发布器

封装「上传图片 → 构建内容 → 发布微博」完整链路。
支持纯文字微博和图文微博两种类型。
"""

import asyncio
import random
from typing import Dict, List, Optional

from tools import utils
from .client import WeiboClient


class WeiboPublishResult:
    """发布结果数据类"""

    def __init__(
        self,
        success: bool,
        weibo_id: str = "",
        raw: Optional[Dict] = None,
        error: str = "",
    ) -> None:
        self.success = success
        self.weibo_id = weibo_id
        self.raw = raw or {}
        self.error = error

    def __repr__(self) -> str:
        if self.success:
            return f"WeiboPublishResult(success=True, weibo_id={self.weibo_id!r})"
        return f"WeiboPublishResult(success=False, error={self.error!r})"


class WeiboPublisher:
    """微博发布器。

    使用方式::

        publisher = WeiboPublisher(wb_client)

        # 纯文字微博
        result = await publisher.publish_text("今天天气真好 #分享#")

        # 图文微博
        result = await publisher.publish_image_weibo(
            content="分享几张图片 #日常#",
            image_paths=["./1.jpg", "./2.jpg"],
        )
        print(result.weibo_id)
    """

    def __init__(self, client: WeiboClient) -> None:
        self._client = client

    # ------------------------------------------------------------------ #
    #  公开发布接口                                                         #
    # ------------------------------------------------------------------ #

    async def publish_text(self, content: str) -> WeiboPublishResult:
        """发布纯文字微博。

        Args:
            content: 微博正文（话题用 #话题# 格式）

        Returns:
            WeiboPublishResult
        """
        try:
            delay = random.uniform(3, 8)
            utils.logger.info(f"[WeiboPublisher] Waiting {delay:.1f}s before publishing...")
            await asyncio.sleep(delay)

            raw = await self._client.publish_weibo(content=content)
            weibo_id = str(raw.get("id") or raw.get("idstr", ""))
            utils.logger.info(f"[WeiboPublisher] Text weibo published, weibo_id={weibo_id}")
            return WeiboPublishResult(success=True, weibo_id=weibo_id, raw=raw)

        except Exception as exc:
            detail = self._unwrap_error(exc)
            utils.logger.error(f"[WeiboPublisher.publish_text] Failed: {detail}")
            return WeiboPublishResult(success=False, error=detail)

    async def publish_image_weibo(
        self,
        content: str,
        image_paths: List[str],
    ) -> WeiboPublishResult:
        """发布图文微博。

        Args:
            content:     微博正文
            image_paths: 本地图片路径列表（最多 9 张）

        Returns:
            WeiboPublishResult
        """
        if not image_paths:
            return WeiboPublishResult(success=False, error="image_paths 不能为空")

        try:
            # 逐张上传图片
            pic_ids: List[str] = []
            for path in image_paths:
                pic_id = await self._client.upload_pic(path)
                pic_ids.append(pic_id)
                utils.logger.info(f"[WeiboPublisher] Uploaded: {path} → pic_id={pic_id!r}")
                await asyncio.sleep(random.uniform(1, 3))

            # 上传完成后随机等待，模拟人工操作间隔
            delay = random.uniform(5, 12)
            utils.logger.info(f"[WeiboPublisher] Waiting {delay:.1f}s before publishing...")
            await asyncio.sleep(delay)

            raw = await self._client.publish_weibo(content=content, pic_ids=pic_ids)
            weibo_id = str(raw.get("id") or raw.get("idstr", ""))
            utils.logger.info(f"[WeiboPublisher] Image weibo published, weibo_id={weibo_id}")
            return WeiboPublishResult(success=True, weibo_id=weibo_id, raw=raw)

        except Exception as exc:
            detail = self._unwrap_error(exc)
            utils.logger.error(f"[WeiboPublisher.publish_image_weibo] Failed: {detail}")
            return WeiboPublishResult(success=False, error=detail)

    # ------------------------------------------------------------------ #
    #  内部辅助方法                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _unwrap_error(exc: Exception) -> str:
        """展开 RetryError 等包装异常，输出最内层错误信息。"""
        last_attempt = getattr(exc, "last_attempt", None)
        if last_attempt is not None:
            try:
                inner = last_attempt.exception()
                if inner is not None:
                    return str(inner)
            except Exception:
                pass
        if exc.__cause__:
            return f"{exc} | cause={exc.__cause__}"
        return str(exc)
