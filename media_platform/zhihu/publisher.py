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

"""知乎发布器

封装「创建草稿 → 上传图片 → 发布文章」和「发布回答」完整链路。
支持专栏文章和问题回答两种类型。
"""

import asyncio
import random
from typing import Dict, List, Optional

from tools import utils
from .client import ZhiHuClient


class ZhihuPublishResult:
    """发布结果数据类"""

    def __init__(
        self,
        success: bool,
        content_id: str = "",
        content_type: str = "",
        content_url: str = "",
        raw: Optional[Dict] = None,
        error: str = "",
    ) -> None:
        self.success = success
        self.content_id = content_id
        self.content_type = content_type
        self.content_url = content_url
        self.raw = raw or {}
        self.error = error

    def __repr__(self) -> str:
        if self.success:
            return f"ZhihuPublishResult(success=True, content_id={self.content_id!r}, type={self.content_type!r})"
        return f"ZhihuPublishResult(success=False, error={self.error!r})"


class ZhihuPublisher:
    """知乎发布器。

    使用方式::

        publisher = ZhihuPublisher(zhihu_client)

        # 发布专栏文章
        result = await publisher.publish_article(
            title="文章标题",
            content="<p>文章正文</p>",
            topics=["Python", "编程"],
        )

        # 回答问题
        result = await publisher.publish_answer(
            question_id="12345678",
            content="<p>回答正文</p>",
        )
    """

    def __init__(self, client: ZhiHuClient) -> None:
        self._client = client

    # ------------------------------------------------------------------ #
    #  公开发布接口                                                         #
    # ------------------------------------------------------------------ #

    async def publish_article(
        self,
        title: str,
        content: str,
        topics: Optional[List[str]] = None,
        image_paths: Optional[List[str]] = None,
    ) -> ZhihuPublishResult:
        """发布知乎专栏文章。

        流程：创建草稿 → 上传图片(可选) → 更新草稿内容 → 发布草稿

        Args:
            title: 文章标题
            content: HTML 格式正文
            topics: 话题列表（可选）
            image_paths: 本地图片路径列表（可选，将嵌入正文）

        Returns:
            ZhihuPublishResult
        """
        try:
            # 1. 上传图片并嵌入正文
            if image_paths:
                content = await self._embed_images(content, image_paths)

            # 2. 创建草稿（直接携带标题和内容）
            draft_res = await self._client.create_article_draft(title=title, content=content)
            draft_id = str(draft_res.get("id", ""))
            if not draft_id:
                return ZhihuPublishResult(success=False, error=f"创建草稿失败：{draft_res}")
            utils.logger.info(f"[ZhihuPublisher] 草稿创建成功，draft_id={draft_id}")

            # 3. 若创建时未携带成功，尝试 PATCH 更新草稿内容
            draft_title = draft_res.get("title", "")
            if draft_title != title:
                utils.logger.info("[ZhihuPublisher] 草稿创建未携带内容，尝试 PATCH 更新...")
                update_res = await self._client.update_article_draft(
                    draft_id=draft_id,
                    title=title,
                    content=content,
                    topics=topics,
                )
                if update_res == {}:
                    utils.logger.warning(f"[ZhihuPublisher] PATCH 更新草稿返回空（可能 404），继续尝试发布")
            else:
                utils.logger.info("[ZhihuPublisher] 草稿已包含标题和内容")

            # 4. 随机延迟，模拟人工操作
            delay = random.uniform(3, 8)
            utils.logger.info(f"[ZhihuPublisher] 等待 {delay:.1f}s 后发布...")
            await asyncio.sleep(delay)

            # 5. 发布草稿
            raw = await self._client.publish_article_draft(draft_id)
            content_url = f"https://zhuanlan.zhihu.com/p/{draft_id}"
            utils.logger.info(f"[ZhihuPublisher] 文章发布成功: {content_url}")

            return ZhihuPublishResult(
                success=True,
                content_id=draft_id,
                content_type="article",
                content_url=content_url,
                raw=raw,
            )

        except Exception as exc:
            detail = self._unwrap_error(exc)
            utils.logger.error(f"[ZhihuPublisher.publish_article] 发布失败: {detail}")
            return ZhihuPublishResult(success=False, error=detail)

    async def publish_answer(
        self,
        question_id: str,
        content: str,
        image_paths: Optional[List[str]] = None,
    ) -> ZhihuPublishResult:
        """发布知乎回答。

        Args:
            question_id: 知乎问题 ID
            content: HTML 格式回答正文
            image_paths: 本地图片路径列表（可选，将嵌入正文）

        Returns:
            ZhihuPublishResult
        """
        try:
            # 1. 上传图片并嵌入正文
            if image_paths:
                content = await self._embed_images(content, image_paths)

            # 2. 随机延迟
            delay = random.uniform(3, 8)
            utils.logger.info(f"[ZhihuPublisher] 等待 {delay:.1f}s 后发布回答...")
            await asyncio.sleep(delay)

            # 3. 发布回答
            raw = await self._client.post_answer(question_id=question_id, content=content)
            if not raw or not raw.get("id"):
                error_msg = f"发布回答失败，API 返回：{raw}"
                utils.logger.error(f"[ZhihuPublisher.publish_answer] {error_msg}")
                return ZhihuPublishResult(success=False, error=error_msg)

            answer_id = str(raw.get("id", ""))
            content_url = f"https://www.zhihu.com/question/{question_id}/answer/{answer_id}"
            utils.logger.info(f"[ZhihuPublisher] 回答发布成功: {content_url}")

            return ZhihuPublishResult(
                success=True,
                content_id=answer_id,
                content_type="answer",
                content_url=content_url,
                raw=raw,
            )

        except Exception as exc:
            detail = self._unwrap_error(exc)
            utils.logger.error(f"[ZhihuPublisher.publish_answer] 发布失败: {detail}")
            return ZhihuPublishResult(success=False, error=detail)

    # ------------------------------------------------------------------ #
    #  内部辅助方法                                                         #
    # ------------------------------------------------------------------ #

    async def _embed_images(self, content: str, image_paths: List[str]) -> str:
        """上传图片并将 <img> 标签追加到正文末尾。上传失败时跳过该图片并记录警告。"""
        img_tags: List[str] = []
        for path in image_paths:
            try:
                image_url = await self._client.upload_image(path)
                img_tags.append(f'<figure><img src="{image_url}"></figure>')
                utils.logger.info(f"[ZhihuPublisher] 已上传: {path} → {image_url}")
            except Exception as exc:
                utils.logger.warning(f"[ZhihuPublisher] 图片上传失败，跳过: {path}, 错误: {exc}")
            await asyncio.sleep(random.uniform(1, 3))

        if img_tags:
            content = content + "\n" + "\n".join(img_tags)
        return content

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
