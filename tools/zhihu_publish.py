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

"""知乎发帖命令行工具

支持发布专栏文章和问题回答，通过命令行参数驱动。
结果以 JSON 格式输出到 stdout，日志输出到 stderr。

用法示例：
    # 发布专栏文章
    ./scripts/zhihu_publish.sh article --title "文章标题" --content "<p>正文</p>"

    # 发布带图片的文章
    ./scripts/zhihu_publish.sh article \\
        --title "文章标题" --content "<p>正文</p>" \\
        --images ./img1.jpg,./img2.jpg --topics "Python,编程"

    # 回答问题
    ./scripts/zhihu_publish.sh answer --question-id "12345678" --content "<p>回答</p>"
"""

import argparse
import asyncio
import json
import sys
from typing import List, Optional

import config
from playwright.async_api import BrowserContext, async_playwright

from media_platform.zhihu.client import ZhiHuClient
from media_platform.zhihu.core import ZhihuCrawler
from media_platform.zhihu.login import ZhiHuLogin
from media_platform.zhihu.publisher import ZhihuPublisher
from tools import utils
from tools.app_runner import run


class ZhihuPublishApp:
    """知乎发帖命令行 App。"""

    def __init__(
        self,
        publish_type: str,
        title: str = "",
        content: str = "",
        question_id: str = "",
        topics: Optional[List[str]] = None,
        images: Optional[List[str]] = None,
    ) -> None:
        self.publish_type = publish_type  # "article" | "answer"
        self.title = title
        self.content = content
        self.question_id = question_id
        self.topics = topics or []
        self.images = images or []
        self.crawler: Optional[ZhihuCrawler] = None
        self.browser_context: Optional[BrowserContext] = None

    # ------------------------------------------------------------------ #
    #  内部辅助                                                            #
    # ------------------------------------------------------------------ #

    async def _ensure_login(self, zhihu_client: ZhiHuClient) -> None:
        if await zhihu_client.pong():
            utils.logger.info("[ZhihuPublishApp] Already logged in")
            return

        print("请在弹出的浏览器中登录知乎，脚本自动检测登录状态...", file=sys.stderr)
        login_obj = ZhiHuLogin(
            login_type=config.LOGIN_TYPE,
            login_phone="",
            browser_context=self.browser_context,
            context_page=self.crawler.context_page,
            cookie_str=config.COOKIES,
        )
        await login_obj.begin()
        await zhihu_client.update_cookies(browser_context=self.browser_context)

        if not await zhihu_client.pong():
            raise RuntimeError("登录失败，请检查登录配置")
        print("登录成功", file=sys.stderr)

    async def _launch_browser(self, playwright) -> BrowserContext:
        if config.ENABLE_CDP_MODE:
            return await self.crawler.launch_browser_with_cdp(
                playwright,
                playwright_proxy=None,
                user_agent=self.crawler.user_agent,
                headless=config.CDP_HEADLESS,
            )
        if config.SAVE_LOGIN_STATE:
            import os as _os
            user_data_dir = _os.path.join(
                _os.getcwd(), "browser_data", "zhihu_user_data_dir"
            )
            ctx = await playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=config.HEADLESS,
                viewport={"width": 1920, "height": 1080},
                user_agent=self.crawler.user_agent,
                channel="chrome",
            )
        else:
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
        self.crawler = ZhihuCrawler()

        async with async_playwright() as playwright:
            self.browser_context = await self._launch_browser(playwright)
            self.crawler.browser_context = self.browser_context
            self.crawler.context_page = await self.browser_context.new_page()
            await self.crawler.context_page.goto(self.crawler.index_url)
            await asyncio.sleep(3)

            zhihu_client: ZhiHuClient = await self.crawler.create_zhihu_client(
                httpx_proxy=None
            )
            await self._ensure_login(zhihu_client)

            publisher = ZhihuPublisher(zhihu_client)

            if self.publish_type == "article":
                result = await publisher.publish_article(
                    title=self.title,
                    content=self.content,
                    topics=self.topics or None,
                    image_paths=self.images or None,
                )
            elif self.publish_type == "answer":
                result = await publisher.publish_answer(
                    question_id=self.question_id,
                    content=self.content,
                    image_paths=self.images or None,
                )
            else:
                raise ValueError(f"不支持的 publish_type: {self.publish_type!r}")

            output = {
                "success": result.success,
                "content_id": result.content_id,
                "content_type": result.content_type,
                "content_url": result.content_url,
                "title": self.title,
                "error": result.error,
            }
            print(json.dumps(output, ensure_ascii=False))

    async def app_cleanup(self) -> None:
        if self.crawler:
            try:
                await self.crawler.close()
            except Exception as exc:
                utils.logger.warning("[ZhihuPublishApp] Cleanup failed: %s", exc)


# ------------------------------------------------------------------ #
#  CLI 入口                                                            #
# ------------------------------------------------------------------ #

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="知乎发帖命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "type",
        choices=["article", "answer"],
        help="发布类型：article（专栏文章）或 answer（问题回答）",
    )
    parser.add_argument("--title", default="", help="文章标题（仅 article 类型需要）")
    parser.add_argument("--content", required=True, help="正文内容（支持 HTML 格式）")
    parser.add_argument("--question-id", default="", help="问题 ID（仅 answer 类型需要）")
    parser.add_argument(
        "--topics",
        help="话题，多个用英文逗号分隔（仅 article 类型）",
    )
    parser.add_argument(
        "--images",
        help="图片路径，多张用英文逗号分隔，如 img1.jpg,img2.jpg",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    publish_type: str = args.type
    topics: List[str] = [t.strip() for t in args.topics.split(",")] if args.topics else []
    images: List[str] = [p.strip() for p in args.images.split(",")] if args.images else []

    if publish_type == "article" and not args.title:
        print('{"success":false,"error":"article 类型必须提供 --title 参数"}')
        sys.exit(1)

    if publish_type == "answer" and not args.question_id:
        print('{"success":false,"error":"answer 类型必须提供 --question-id 参数"}')
        sys.exit(1)

    app = ZhihuPublishApp(
        publish_type=publish_type,
        title=args.title,
        content=args.content,
        question_id=args.question_id,
        topics=topics,
        images=images,
    )
    run(app.app_main, app.app_cleanup)


if __name__ == "__main__":
    main()
