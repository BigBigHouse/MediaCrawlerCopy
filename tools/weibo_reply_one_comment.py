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

"""微博回复评论命令行工具

用法示例：
    ./scripts/weibo_reply.sh --weibo-id 1234567890 --comment-id 9876543210 --content "感谢分享！"

    # 直接评论微博本身（不指定 comment-id）
    ./scripts/weibo_reply.sh --weibo-id 1234567890 --content "赞！"
"""

import argparse
import asyncio
import json
import sys
from typing import Optional

import config
from playwright.async_api import BrowserContext, async_playwright

from media_platform.weibo.client import WeiboClient
from media_platform.weibo.core import WeiboCrawler
from media_platform.weibo.login import WeiboLogin
from tools import utils
from tools.app_runner import run


class WeiboReplyApp:
    """微博回复评论命令行 App。"""

    def __init__(
        self,
        weibo_id: str,
        content: str,
        comment_id: str = "",
    ) -> None:
        self.weibo_id = weibo_id
        self.content = content
        self.comment_id = comment_id
        self.crawler: Optional[WeiboCrawler] = None
        self.browser_context: Optional[BrowserContext] = None

    async def _ensure_login(self, wb_client: WeiboClient) -> None:
        if await wb_client.pong():
            utils.logger.info("[WeiboReplyApp] Already logged in")
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

        await self.crawler.context_page.goto(self.crawler.mobile_index_url)
        await asyncio.sleep(3)
        await wb_client.update_cookies(
            browser_context=self.browser_context,
            urls=[self.crawler.mobile_index_url],
        )

        if not await wb_client.pong():
            raise RuntimeError("登录失败，请检查登录配置")
        print("登录成功", file=sys.stderr)

    async def app_main(self) -> None:
        self.crawler = WeiboCrawler()

        async with async_playwright() as playwright:
            if config.ENABLE_CDP_MODE:
                self.browser_context = await self.crawler.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy=None,
                    user_agent=self.crawler.mobile_user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                self.browser_context = await self.crawler.launch_browser(
                    playwright.chromium,
                    playwright_proxy=None,
                    user_agent=self.crawler.mobile_user_agent,
                    headless=config.HEADLESS,
                )
                await self.browser_context.add_init_script(path="libs/stealth.min.js")

            self.crawler.browser_context = self.browser_context
            self.crawler.context_page = await self.browser_context.new_page()
            await self.crawler.context_page.goto(self.crawler.mobile_index_url)
            await asyncio.sleep(2)

            wb_client: WeiboClient = await self.crawler.create_weibo_client(
                httpx_proxy=None
            )
            await self._ensure_login(wb_client)

            reply_result = await wb_client.post_comment(
                weibo_id=self.weibo_id,
                content=self.content,
                comment_id=self.comment_id,
            )
            output = {
                "success":    True,
                "comment_id": str(reply_result.get("id") or reply_result.get("idstr", "")),
                "weibo_id":   self.weibo_id,
                "content":    self.content,
                "raw":        reply_result,
            }
            utils.logger.info("[WeiboReplyApp] Reply result: %s", reply_result)
            print(json.dumps(output, ensure_ascii=False))

    async def app_cleanup(self) -> None:
        if self.crawler:
            try:
                await self.crawler.close()
            except Exception as exc:
                utils.logger.warning("[WeiboReplyApp] Cleanup failed: %s", exc)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="微博回复评论命令行工具")
    parser.add_argument("--weibo-id", required=True, help="微博 ID")
    parser.add_argument("--content", required=True, help="回复内容")
    parser.add_argument(
        "--comment-id",
        default="",
        help="要回复的评论 ID（为空则直接评论微博）",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    app = WeiboReplyApp(
        weibo_id=args.weibo_id,
        content=args.content,
        comment_id=args.comment_id,
    )
    run(app.app_main, app.app_cleanup)


if __name__ == "__main__":
    main()
