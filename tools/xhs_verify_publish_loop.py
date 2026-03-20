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

import argparse
import asyncio
from pathlib import Path
from typing import Optional

import config
from playwright.async_api import BrowserContext, async_playwright

from media_platform.xhs.client import XiaoHongShuClient
from media_platform.xhs.core import XiaoHongShuCrawler
from media_platform.xhs.publisher import XiaoHongShuPublisher
from tools import utils
from tools.app_runner import run


class VerifyPublishLoopApp:
    """最小闭环：生成1张测试图片并发布1条图文笔记。"""

    def __init__(self, title: str, desc: str) -> None:
        self.title = title
        self.desc = desc
        self.crawler: Optional[XiaoHongShuCrawler] = None
        self.browser_context: Optional[BrowserContext] = None
        self.temp_image_path: Optional[Path] = None

    async def _ensure_login(self, xhs_client: XiaoHongShuClient) -> None:
        if await xhs_client.pong():
            utils.logger.info("[VerifyPublishLoopApp] Already logged in, skip login")
            return

        print("\n" + "=" * 60)
        print("⚠️  请在弹出的 Chrome 中手动登录小红书，脚本会自动检测登录状态")
        print("=" * 60 + "\n")

        for i in range(90):
            await asyncio.sleep(2)
            await xhs_client.update_cookies(self.browser_context)
            if await xhs_client.pong():
                print("\n✅ 登录成功，继续执行...\n")
                return
            remain = 180 - (i + 1) * 2
            print(f"\r⏳ 等待登录中... 剩余 {remain}s", end="", flush=True)

        raise RuntimeError("等待登录超时（3分钟）")

    def _create_temp_image(self) -> Path:
        from PIL import Image, ImageDraw

        temp_dir = Path("/Users/hetingxin/PycharmProjects/MediaCrawler/cache")
        temp_dir.mkdir(parents=True, exist_ok=True)
        path = temp_dir / "xhs_publish_smoke.jpg"

        img = Image.new("RGB", (1080, 1440), color=(247, 104, 161))
        draw = ImageDraw.Draw(img)
        draw.text((60, 80), "MediaCrawler Publish Smoke Test", fill=(255, 255, 255))
        draw.text((60, 150), "Do not use for commercial purpose", fill=(255, 255, 255))
        img.save(path, format="JPEG", quality=95)
        return path

    async def app_main(self) -> None:
        self.crawler = XiaoHongShuCrawler()

        async with async_playwright() as playwright:
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[VerifyPublishLoopApp] Using CDP mode")
                self.browser_context = await self.crawler.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy=None,
                    user_agent=self.crawler.user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[VerifyPublishLoopApp] Using standard mode")
                self.browser_context = await self.crawler.launch_browser(
                    playwright.chromium,
                    playwright_proxy=None,
                    user_agent=self.crawler.user_agent,
                    headless=config.HEADLESS,
                )
                await self.browser_context.add_init_script(path="libs/stealth.min.js")

            self.crawler.browser_context = self.browser_context
            self.crawler.context_page = await self.browser_context.new_page()
            await self.crawler.context_page.goto(self.crawler.index_url)

            xhs_client: XiaoHongShuClient = await self.crawler.create_xhs_client(httpx_proxy=None)
            await self._ensure_login(xhs_client)

            self.temp_image_path = self._create_temp_image()
            publisher = XiaoHongShuPublisher(xhs_client)
            result = await publisher.publish_image_note(
                title=self.title,
                desc=self.desc,
                image_paths=[str(self.temp_image_path)],
                topics=["自动化测试"],
            )

            output = {
                "step": "publish_one_image_note",
                "title": self.title,
                "desc": self.desc,
                "image": str(self.temp_image_path),
                "success": result.success,
                "note_id": result.note_id,
                "error": result.error,
                "raw": result.raw,
            }
            print(output)

    async def app_cleanup(self) -> None:
        if self.crawler:
            try:
                await self.crawler.close()
            except Exception as exc:
                utils.logger.warning("[VerifyPublishLoopApp] Cleanup failed: %s", exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="XHS 发帖最小闭环：生成1张图并发布")
    parser.add_argument("--title", default="MediaCrawler 发帖闭环测试", help="发布标题")
    parser.add_argument("--desc", default="这是自动化最小闭环测试笔记。", help="发布正文")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    app = VerifyPublishLoopApp(title=args.title, desc=args.desc)
    run(app.app_main, app.app_cleanup)

