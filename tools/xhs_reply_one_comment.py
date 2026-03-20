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
from typing import Optional

import config
from playwright.async_api import BrowserContext, async_playwright

from media_platform.xhs.client import XiaoHongShuClient
from media_platform.xhs.core import XiaoHongShuCrawler
from media_platform.xhs.login import XiaoHongShuLogin
from tools import utils
from tools.app_runner import run


class OneCommentReplyApp:
    def __init__(
        self,
        note_id: str,
        target_comment_id: str,
        content: str,
        xsec_token: str = "",
        xsec_source: str = "",
    ) -> None:
        self.note_id = note_id
        self.target_comment_id = target_comment_id
        self.content = content
        self.xsec_token = xsec_token
        self.xsec_source = xsec_source
        self.crawler: Optional[XiaoHongShuCrawler] = None
        self.browser_context: Optional[BrowserContext] = None

    async def app_main(self) -> None:
        self.crawler = XiaoHongShuCrawler()

        async with async_playwright() as playwright:
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[OneCommentReplyApp] Using CDP mode")
                self.browser_context = await self.crawler.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy=None,
                    user_agent=self.crawler.user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[OneCommentReplyApp] Using standard mode")
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
            if not await xhs_client.pong():
                utils.logger.info("[OneCommentReplyApp] Login expired, start relogin")
                login_obj = XiaoHongShuLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="",
                    browser_context=self.browser_context,
                    context_page=self.crawler.context_page,
                    cookie_str=config.COOKIES,
                )
                await login_obj.begin()
                await xhs_client.update_cookies(self.browser_context)

            reply_result = await xhs_client.post_comment(
                note_id=self.note_id,
                content=self.content,
                target_comment_id=self.target_comment_id,
                xsec_token=self.xsec_token,
                xsec_source=self.xsec_source,
            )
            utils.logger.info("[OneCommentReplyApp] Reply result: %s", reply_result)
            print(reply_result)

    async def app_cleanup(self) -> None:
        if self.crawler:
            try:
                await self.crawler.close()
            except Exception as exc:
                utils.logger.warning("[OneCommentReplyApp] Cleanup failed: %s", exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reply one Xiaohongshu comment (minimal closed loop)")
    parser.add_argument("--note-id", required=True, help="Target note id")
    parser.add_argument("--comment-id", required=True, help="Target comment id to reply")
    parser.add_argument("--content", required=True, help="Reply content")
    parser.add_argument("--xsec-token", default="", help="Optional xsec_token from note URL")
    parser.add_argument("--xsec-source", default="", help="Optional xsec_source from note URL")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    app = OneCommentReplyApp(
        note_id=args.note_id,
        target_comment_id=args.comment_id,
        content=args.content,
        xsec_token=args.xsec_token,
        xsec_source=args.xsec_source,
    )
    run(app.app_main, app.app_cleanup)

