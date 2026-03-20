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

"""小红书发帖命令行工具

支持发布图文笔记和视频笔记，通过命令行参数驱动。
结果以 JSON 格式输出到 stdout，日志输出到 stderr。

用法示例：
    # 发布图文笔记（单张图）
    ./scripts/xhs_publish.sh image \\
        --title "今日分享" \\
        --desc "内容正文" \\
        --images ./imgs/photo1.jpg

    # 发布图文笔记（多张图）
    ./scripts/xhs_publish.sh image \\
        --title "今日分享" \\
        --desc "内容正文" \\
        --images ./imgs/1.jpg,./imgs/2.jpg,./imgs/3.jpg \\
        --topics "日常,生活"

    # 发布视频笔记
    ./scripts/xhs_publish.sh video \\
        --title "我的视频" \\
        --desc "视频简介" \\
        --video ./videos/clip.mp4 \\
        --cover ./imgs/cover.jpg
"""

import argparse
import asyncio
import json
import sys
from typing import List, Optional

import config
from playwright.async_api import BrowserContext, async_playwright

from media_platform.xhs.client import XiaoHongShuClient
from media_platform.xhs.core import XiaoHongShuCrawler
from media_platform.xhs.publisher import XiaoHongShuPublisher
from tools import utils
from tools.app_runner import run


class XhsPublishApp:
    """小红书发帖命令行 App。"""

    def __init__(
        self,
        note_type: str,
        title: str,
        desc: str,
        images: Optional[List[str]] = None,
        video: Optional[str] = None,
        cover: Optional[str] = None,
        topics: Optional[List[str]] = None,
    ) -> None:
        self.note_type = note_type          # "image" | "video"
        self.title = title
        self.desc = desc
        self.images = images or []
        self.video = video
        self.cover = cover
        self.topics = topics or []
        self.crawler: Optional[XiaoHongShuCrawler] = None
        self.browser_context: Optional[BrowserContext] = None

    # ------------------------------------------------------------------ #
    #  内部辅助                                                            #
    # ------------------------------------------------------------------ #

    async def _ensure_login(self, xhs_client: XiaoHongShuClient) -> None:
        if await xhs_client.pong():
            utils.logger.info("[XhsPublishApp] Already logged in")
            return

        print("请在弹出的 Chrome 中登录小红书，脚本自动检测登录状态...", file=sys.stderr)
        for i in range(90):
            await asyncio.sleep(2)
            await xhs_client.update_cookies(self.browser_context)
            if await xhs_client.pong():
                print("登录成功", file=sys.stderr)
                return
            remain = 180 - (i + 1) * 2
            print(f"\r等待登录... 剩余 {remain}s", end="", flush=True, file=sys.stderr)

        raise RuntimeError("等待登录超时（3分钟）")

    async def _launch_browser(self, playwright) -> BrowserContext:
        if config.ENABLE_CDP_MODE:
            return await self.crawler.launch_browser_with_cdp(
                playwright,
                playwright_proxy=None,
                user_agent=self.crawler.user_agent,
                headless=config.CDP_HEADLESS,
            )
        ctx = await self.crawler.launch_browser(
            playwright.chromium,
            playwright_proxy=None,
            user_agent=self.crawler.user_agent,
            headless=config.HEADLESS,
        )
        await ctx.add_init_script(path="libs/stealth.min.js")
        return ctx

    # ------------------------------------------------------------------ #
    #  App 生命周期                                                        #
    # ------------------------------------------------------------------ #

    async def app_main(self) -> None:
        self.crawler = XiaoHongShuCrawler()

        async with async_playwright() as playwright:
            self.browser_context = await self._launch_browser(playwright)
            self.crawler.browser_context = self.browser_context
            self.crawler.context_page = await self.browser_context.new_page()
            await self.crawler.context_page.goto(self.crawler.index_url)

            xhs_client: XiaoHongShuClient = await self.crawler.create_xhs_client(
                httpx_proxy=None
            )
            await self._ensure_login(xhs_client)

            publisher = XiaoHongShuPublisher(xhs_client)

            if self.note_type == "image":
                result = await publisher.publish_image_note(
                    title=self.title,
                    desc=self.desc,
                    image_paths=self.images,
                    topics=self.topics,
                )
            elif self.note_type == "video":
                result = await publisher.publish_video_note(
                    title=self.title,
                    desc=self.desc,
                    video_path=self.video,
                    cover_path=self.cover or None,
                    topics=self.topics,
                )
            else:
                raise ValueError(f"不支持的 note_type: {self.note_type!r}")

            output = {
                "success":   result.success,
                "note_id":   result.note_id,
                "note_type": self.note_type,
                "title":     self.title,
                "error":     result.error,
            }
            # JSON 输出到 stdout，便于脚本解析
            print(json.dumps(output, ensure_ascii=False))

    async def app_cleanup(self) -> None:
        if self.crawler:
            try:
                await self.crawler.close()
            except Exception as exc:
                utils.logger.warning("[XhsPublishApp] Cleanup failed: %s", exc)


# ------------------------------------------------------------------ #
#  CLI 入口                                                            #
# ------------------------------------------------------------------ #

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="小红书发帖命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "type",
        choices=["image", "video"],
        help="笔记类型：image（图文）或 video（视频）",
    )
    parser.add_argument("--title", required=True, help="笔记标题（建议不超过 20 字）")
    parser.add_argument("--desc",  required=True, help="笔记正文")
    parser.add_argument(
        "--images",
        help="图文笔记图片路径，多张用英文逗号分隔，如 img1.jpg,img2.jpg",
    )
    parser.add_argument("--video", help="视频笔记视频路径，如 clip.mp4")
    parser.add_argument("--cover", help="视频封面路径（可选）")
    parser.add_argument(
        "--topics",
        help="话题标签，多个用英文逗号分隔，如 日常,分享",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    note_type: str = args.type
    images: List[str] = [p.strip() for p in args.images.split(",")] if args.images else []
    topics: List[str] = [t.strip() for t in args.topics.split(",")] if args.topics else []

    # 参数校验
    if note_type == "image" and not images:
        print('{"success":false,"error":"--images 不能为空（图文笔记必须提供图片路径）"}')
        sys.exit(1)
    if note_type == "video" and not args.video:
        print('{"success":false,"error":"--video 不能为空（视频笔记必须提供视频路径）"}')
        sys.exit(1)

    app = XhsPublishApp(
        note_type=note_type,
        title=args.title,
        desc=args.desc,
        images=images,
        video=args.video,
        cover=args.cover,
        topics=topics,
    )
    run(app.app_main, app.app_cleanup)


if __name__ == "__main__":
    main()
