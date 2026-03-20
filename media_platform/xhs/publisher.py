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

"""小红书笔记发布器

封装「申请上传凭证 → OSS 直传媒体 → 等待转码 → 构建 payload → 发布」完整链路。
支持图文笔记和视频笔记两种类型。
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tools import utils
from .client import XiaoHongShuClient


class NotePublishResult:
    """发布结果数据类"""

    def __init__(self, success: bool, note_id: str = "", raw: Optional[Dict] = None, error: str = "") -> None:
        self.success  = success
        self.note_id  = note_id
        self.raw      = raw or {}
        self.error    = error

    def __repr__(self) -> str:
        if self.success:
            return f"NotePublishResult(success=True, note_id={self.note_id!r})"
        return f"NotePublishResult(success=False, error={self.error!r})"


class XiaoHongShuPublisher:
    """小红书笔记发布器。

    使用方式::

        publisher = XiaoHongShuPublisher(xhs_client)
        result = await publisher.publish_image_note(
            title="测试标题",
            desc="这是正文内容",
            image_paths=["./imgs/1.jpg", "./imgs/2.jpg"],
            topics=["Python", "编程"],
        )
        print(result.note_id)
    """

    def __init__(self, client: XiaoHongShuClient) -> None:
        self._client = client

    # ------------------------------------------------------------------ #
    #  公开发布接口                                                         #
    # ------------------------------------------------------------------ #

    async def publish_image_note(
        self,
        title: str,
        desc: str,
        image_paths: List[str],
        topics: Optional[List[str]] = None,
    ) -> NotePublishResult:
        """发布图文笔记。

        Args:
            title:       笔记标题（最多 20 字）
            desc:        笔记正文
            image_paths: 本地图片路径列表（至少 1 张，最多 18 张）
            topics:      话题标签列表（可选），如 ["Python", "编程"]

        Returns:
            NotePublishResult
        """
        if not image_paths:
            return NotePublishResult(success=False, error="image_paths 不能为空")

        try:
            # 1. 逐张上传图片，获取 file_id + 尺寸
            image_info_list: List[Dict] = []
            for path in image_paths:
                file_id, width, height = await self._upload_media(path)
                suffix = Path(path).suffix.lstrip(".").lower()
                mime = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix}"
                image_info_list.append({
                    "file_id":        file_id,
                    "width":          width,
                    "height":         height,
                    "metadata":       {"source": -1},
                    "stickers":       {"version": 2, "floating": []},
                    "extra_info_json": f'{{"mimeType":"{mime}","image_metadata":{{"bg_color":"","origin_size":0}}}}',
                })
                utils.logger.info(
                    f"[XiaoHongShuPublisher] Uploaded image: {path} → file_id={file_id}"
                )

            # 2. 构建 payload 并发布
            payload = self._build_image_payload(title, desc, image_info_list, topics or [])
            raw = await self._client.publish_note(payload)
            note_id = raw.get("note_id", "") or raw.get("id", "")
            utils.logger.info(
                f"[XiaoHongShuPublisher] Image note published, note_id={note_id}"
            )
            return NotePublishResult(success=True, note_id=note_id, raw=raw)

        except Exception as exc:
            detail = self._unwrap_error(exc)
            utils.logger.error(f"[XiaoHongShuPublisher.publish_image_note] Failed: {detail}")
            return NotePublishResult(success=False, error=detail)

    async def publish_video_note(
        self,
        title: str,
        desc: str,
        video_path: str,
        cover_path: Optional[str] = None,
        topics: Optional[List[str]] = None,
        max_wait_sec: int = 300,
    ) -> NotePublishResult:
        """发布视频笔记。

        Args:
            title:        笔记标题
            desc:         笔记正文
            video_path:   本地视频文件路径（支持 mp4 / mov）
            cover_path:   封面图路径（可选，不传则由平台自动截帧）
            topics:       话题标签列表（可选）
            max_wait_sec: 等待视频转码的最长秒数（默认 300 秒）

        Returns:
            NotePublishResult
        """
        try:
            # 1. 上传视频
            video_file_id, _, _ = await self._upload_media(video_path, filetype="mp4")
            utils.logger.info(
                f"[XiaoHongShuPublisher] Video uploaded, file_id={video_file_id}"
            )

            # 2. 等待视频转码完成
            utils.logger.info(
                f"[XiaoHongShuPublisher] Waiting for video transcoding (max {max_wait_sec}s)..."
            )
            ready = await self._wait_video_ready(video_file_id, max_wait_sec)
            if not ready:
                raise RuntimeError(
                    f"视频转码超时（{max_wait_sec}s），file_id={video_file_id}"
                )

            # 3. 上传封面（可选）
            cover_file_id = ""
            if cover_path:
                cover_file_id, _, _ = await self._upload_media(cover_path)
                utils.logger.info(
                    f"[XiaoHongShuPublisher] Cover uploaded, file_id={cover_file_id}"
                )

            # 4. 获取视频时长
            duration = self._get_video_duration(video_path)

            # 5. 构建 payload 并发布
            payload = self._build_video_payload(
                title, desc, video_file_id, cover_file_id, duration, topics or []
            )
            raw = await self._client.publish_note(payload)
            note_id = raw.get("note_id", "") or raw.get("id", "")
            utils.logger.info(
                f"[XiaoHongShuPublisher] Video note published, note_id={note_id}"
            )
            return NotePublishResult(success=True, note_id=note_id, raw=raw)

        except Exception as exc:
            detail = self._unwrap_error(exc)
            utils.logger.error(f"[XiaoHongShuPublisher.publish_video_note] Failed: {detail}")
            return NotePublishResult(success=False, error=detail)

    # ------------------------------------------------------------------ #
    #  内部辅助方法                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _unwrap_error(exc: Exception) -> str:
        """展开 RetryError 等包装异常，输出最内层错误信息。"""
        # 兼容 tenacity.RetryError
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

    async def _upload_media(
        self,
        file_path: str,
        filetype: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        """上传单个媒体文件，返回 (file_id, width, height)。

        width/height 对视频返回 0；图片由 Pillow 读取真实尺寸。
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"媒体文件不存在：{file_path}")

        if filetype is None:
            filetype = path.suffix.lstrip(".").lower()
            if filetype == "jpeg":
                filetype = "jpg"

        # 根据文件类型选择上传场景
        is_video = filetype in ("mp4", "mov")
        scene = "video" if is_video else "image"

        with open(file_path, "rb") as fh:
            content = fh.read()

        # 申请上传凭证
        token_res = await self._client.apply_upload_token(scene=scene, filetype=filetype)
        upload_url: str = token_res["upload_url"]
        token:      str = token_res["token"]
        file_id:    str = token_res["file_id"]

        # OSS 直传
        ok = await self._client.upload_file_to_oss(upload_url, token, content, filetype)
        if not ok:
            raise RuntimeError(f"OSS 上传失败：{file_path}")

        # 图片读取实际尺寸
        width, height = 0, 0
        if filetype in ("jpg", "jpeg", "png", "webp"):
            width, height = self._get_image_size(file_path)

        return file_id, width, height

    async def _wait_video_ready(self, file_id: str, max_wait_sec: int = 300) -> bool:
        """轮询视频转码状态，每 5 秒查询一次直到 done 或超时。"""
        for _ in range(max_wait_sec // 5):
            await asyncio.sleep(5)
            try:
                res = await self._client.query_video_status([file_id])
                status_list = res.get("file_status_list", [])
                if not status_list:
                    continue
                status: str = status_list[0].get("status", "")
                utils.logger.info(
                    f"[XiaoHongShuPublisher] Video transcoding status: {status}"
                )
                if status == "done":
                    return True
                if status == "failed":
                    utils.logger.error(
                        f"[XiaoHongShuPublisher] Video transcoding failed, file_id={file_id}"
                    )
                    return False
            except Exception as exc:
                utils.logger.warning(
                    f"[XiaoHongShuPublisher._wait_video_ready] query error: {exc}"
                )
        return False

    @staticmethod
    def _get_image_size(path: str) -> Tuple[int, int]:
        """使用 Pillow 读取图片尺寸，失败时返回 (0, 0)。"""
        try:
            from PIL import Image
            with Image.open(path) as img:
                return img.width, img.height
        except Exception as exc:
            utils.logger.warning(f"[XiaoHongShuPublisher._get_image_size] {exc}")
            return 0, 0

    @staticmethod
    def _get_video_duration(path: str) -> float:
        """使用 opencv 读取视频时长（秒），失败时返回 0.0。"""
        try:
            import cv2
            cap = cv2.VideoCapture(path)
            fps         = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            return round(frame_count / fps, 2) if fps > 0 else 0.0
        except Exception as exc:
            utils.logger.warning(f"[XiaoHongShuPublisher._get_video_duration] {exc}")
            return 0.0

    @staticmethod
    def _build_ops(desc: str, topics: List[str]) -> List[Dict]:
        """构建笔记正文的 Quill Delta ops 结构（保留，暂未使用）。"""
        ops: List[Dict] = []
        if desc:
            ops.append({"insert": desc})
        for topic in topics:
            ops.append({
                "insert":     f"#{topic} ",
                "attributes": {"topic": {"name": topic}},
            })
        ops.append({"insert": "\n"})
        return ops

    _SOURCE = (
        '{"type":"web","ids":"","extraInfo":"{\\"systemId\\":\\"web\\"}"}'
    )
    _BUSINESS_BINDS = (
        '{"version":1,"noteId":0,"bizType":0,"noteOrderBind":{},'
        '"notePostTiming":{},"noteCollectionBind":{"id":""},'
        '"noteSketchCollectionBind":{"id":""},'
        '"coProduceBind":{"enable":true},'
        '"noteCopyBind":{"copyable":true},'
        '"interactionPermissionBind":{"commentPermission":0},'
        '"optionRelationList":[]}'
    )
    _CAPA_TRACE = (
        '{"recommend_title":{"recommend_title_id":"","is_use":3,"used_index":-1},'
        '"recommendTitle":[],"recommend_topics":{"used":[]}}'
    )

    def _build_common(self, note_type: str, title: str, desc: str) -> Dict:
        """构建 common 字段。"""
        return {
            "type":           note_type,
            "note_id":        "",
            "source":         self._SOURCE,
            "title":          title,
            "desc":           desc,
            "ats":            [],
            "hash_tag":       [],
            "business_binds": self._BUSINESS_BINDS,
            "privacy_info":   {"op_type": 1, "type": 0, "user_ids": []},
            "goods_info":     {},
            "biz_relations":  [],
            "capa_trace_info": {"contextJson": self._CAPA_TRACE},
        }

    def _build_image_payload(
        self,
        title:           str,
        desc:            str,
        image_info_list: List[Dict],
        topics:          List[str],
    ) -> Dict:
        """构建图文笔记发布 payload（web_api/sns/v2/note）。"""
        return {
            "common":     self._build_common("normal", title, desc),
            "image_info": {"images": image_info_list},
            "video_info": None,
        }

    def _build_video_payload(
        self,
        title:         str,
        desc:          str,
        video_file_id: str,
        cover_file_id: str,
        duration:      float,
        topics:        List[str],
    ) -> Dict:
        """构建视频笔记发布 payload（web_api/sns/v2/note）。"""
        video_info: Dict = {
            "file_id":        video_file_id,
            "video_duration": duration,
        }
        if cover_file_id:
            video_info["cover_file_id"] = cover_file_id
        return {
            "common":     self._build_common("video", title, desc),
            "image_info": None,
            "video_info": video_info,
        }

