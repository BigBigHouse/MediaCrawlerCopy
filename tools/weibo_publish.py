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

"""微博发帖命令行工具

支持发布纯文字微博和图文微博，通过命令行参数驱动。
结果以 JSON 格式输出到 stdout，日志输出到 stderr。

用法示例：
    # 发布纯文字微博
    ./scripts/weibo_publish.sh text --content "今天天气真好 #分享#"

    # 发布图文微博（单张图）
    ./scripts/weibo_publish.sh image --content "分享一张图 #日常#" --images ./img.jpg

    # 发布图文微博（多张图）
    ./scripts/weibo_publish.sh image \\
        --content "分享几张图 #日常#" \\
        --images ./1.jpg,./2.jpg,./3.jpg
"""

import argparse
import asyncio
import json
import sys
from typing import List, Optional

import config
from playwright.async_api import BrowserContext, async_playwright

from media_platform.weibo.client import WeiboClient
from media_platform.weibo.core import WeiboCrawler
from media_platform.weibo.login import WeiboLogin
from media_platform.weibo.publisher import WeiboPublisher
from tools import utils
from tools.app_runner import run


class WeiboPublishApp:
    """微博发帖命令行 App。"""

    def __init__(
        self,
        weibo_type: str,
        content: str,
        images: Optional[List[str]] = None,
    ) -> None:
        self.weibo_type = weibo_type      # "text" | "image"
        self.content = content
        self.images = images or []
        self.crawler: Optional[WeiboCrawler] = None
        self.browser_context: Optional[BrowserContext] = None

    # ------------------------------------------------------------------ #
    #  内部辅助                                                            #
    # ------------------------------------------------------------------ #

    async def _ensure_login(self, wb_client: WeiboClient) -> None:
        if await wb_client.pong():
            utils.logger.info("[WeiboPublishApp] Already logged in")
            return

        print("请在弹出的 Chrome 中登录微博，脚本自动检测登录状态...", file=sys.stderr)
        login_obj = WeiboLogin(
            login_type=config.LOGIN_TYPE,
            login_phone="",
            browser_context=self.browser_context,
            context_page=self.crawler.context_page,
            cookie_str=config.COOKIES,
        )
        await login_obj.begin()

        # 登录后跳转到移动端并更新 cookies
        await self.crawler.context_page.goto(self.crawler.mobile_index_url)
        await asyncio.sleep(3)
        await wb_client.update_cookies(
            browser_context=self.browser_context,
            urls=[self.crawler.mobile_index_url],
        )

        if not await wb_client.pong():
            raise RuntimeError("登录失败，请检查登录配置")
        print("登录成功", file=sys.stderr)

    async def _launch_browser(self, playwright) -> BrowserContext:
        if config.ENABLE_CDP_MODE:
            return await self.crawler.launch_browser_with_cdp(
                playwright,
                playwright_proxy=None,
                user_agent=self.crawler.mobile_user_agent,
                headless=config.CDP_HEADLESS,
            )
        # 强制使用微博专属 user_data_dir，避免被 config.PLATFORM 影响
        if config.SAVE_LOGIN_STATE:
            import os as _os
            user_data_dir = _os.path.join(_os.getcwd(), "browser_data", "weibo_user_data_dir")
            ctx = await playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=config.HEADLESS,
                viewport={"width": 1920, "height": 1080},
                user_agent=self.crawler.mobile_user_agent,
                channel="chrome",
            )
        else:
            ctx = await self.crawler.launch_browser(
                playwright.chromium,
                playwright_proxy=None,
                user_agent=self.crawler.mobile_user_agent,
                headless=config.HEADLESS,
            )
        await ctx.add_init_script(path="libs/stealth.min.js")
        return ctx

    # ------------------------------------------------------------------ #
    #  App 生命周期                                                        #
    # ------------------------------------------------------------------ #

    async def app_main(self) -> None:
        self.crawler = WeiboCrawler()

        async with async_playwright() as playwright:
            self.browser_context = await self._launch_browser(playwright)
            self.crawler.browser_context = self.browser_context
            self.crawler.context_page = await self.browser_context.new_page()
            # 必须先访问移动端，确保 m.weibo.cn 的 XSRF-TOKEN cookie 生效
            await self.crawler.context_page.goto(self.crawler.mobile_index_url)
            await asyncio.sleep(2)

            wb_client: WeiboClient = await self.crawler.create_weibo_client(
                httpx_proxy=None
            )
            await self._ensure_login(wb_client)

            publisher = WeiboPublisher(wb_client)

            if self.weibo_type == "text":
                result = await publisher.publish_text(content=self.content)
            elif self.weibo_type == "image":
                result = await publisher.publish_image_weibo(
                    content=self.content,
                    image_paths=self.images,
                )
            else:
                raise ValueError(f"不支持的 weibo_type: {self.weibo_type!r}")

            output = {
                "success":    result.success,
                "weibo_id":   result.weibo_id,
                "weibo_type": self.weibo_type,
                "content":    self.content,
                "error":      result.error,
            }
            print(json.dumps(output, ensure_ascii=False))

    async def app_cleanup(self) -> None:
        if self.crawler:
            try:
                await self.crawler.close()
            except Exception as exc:
                utils.logger.warning("[WeiboPublishApp] Cleanup failed: %s", exc)


# ------------------------------------------------------------------ #
#  CLI 入口                                                            #
# ------------------------------------------------------------------ #

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="微博发帖命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "type",
        choices=["text", "image"],
        help="发布类型：text（纯文字）或 image（图文）",
    )
    parser.add_argument("--content", required=True, help="微博正文（话题用 #话题# 格式）")
    parser.add_argument(
        "--images",
        help="图文微博图片路径，多张用英文逗号分隔，如 img1.jpg,img2.jpg（最多 9 张）",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    weibo_type: str = args.type
    images: List[str] = [p.strip() for p in args.images.split(",")] if args.images else []

    if weibo_type == "image" and not images:
        print('{"success":false,"error":"--images 不能为空（图文微博必须提供图片路径）"}')
        sys.exit(1)

    app = WeiboPublishApp(
        weibo_type=weibo_type,
        content=args.content,
        images=images,
    )
    run(app.app_main, app.app_cleanup)


if __name__ == "__main__":
    main()
