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
from typing import Any, Dict, List, Optional, Tuple

import config
from playwright.async_api import BrowserContext, async_playwright

from media_platform.xhs.client import XiaoHongShuClient
from media_platform.xhs.core import XiaoHongShuCrawler
from media_platform.xhs.field import SearchSortType
from tools import utils
from tools.app_runner import run


class VerifyReplyLoopApp:
    """最小闭环：先爬 1 条评论，再对该评论回复 1 条内容。"""

    def __init__(self, keyword: str, content: str, max_notes_try: int = 5) -> None:
        self.keyword = keyword
        self.content = content
        self.max_notes_try = max_notes_try
        self.crawler: Optional[XiaoHongShuCrawler] = None
        self.browser_context: Optional[BrowserContext] = None

    async def _ensure_login(self, xhs_client: XiaoHongShuClient) -> None:
        if await xhs_client.pong():
            utils.logger.info("[VerifyReplyLoopApp] Already logged in, skip login")
            return

        utils.logger.info("[VerifyReplyLoopApp] Not logged in, waiting for manual login in browser ...")
        print("\n" + "=" * 60)
        print("⚠️  请在已弹出的 Chrome 窗口中手动登录小红书")
        print("   完成后脚本将自动继续（最多等待 3 分钟）")
        print("=" * 60 + "\n")

        for i in range(90):
            await asyncio.sleep(2)
            await xhs_client.update_cookies(self.browser_context)
            if await xhs_client.pong():
                utils.logger.info("[VerifyReplyLoopApp] Login detected, continuing ...")
                print("\n✅ 登录成功，继续执行...\n")
                return
            remaining = 180 - (i + 1) * 2
            print(f"\r⏳ 等待登录中... 剩余 {remaining}s", end="", flush=True)

        raise RuntimeError("等待登录超时（3 分钟），请确认已在 Chrome 中完成小红书登录")

    async def _pick_comment_target(self, xhs_client: XiaoHongShuClient) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        sort_type = SearchSortType(config.SORT_TYPE) if config.SORT_TYPE else SearchSortType.GENERAL
        notes_res = await xhs_client.get_note_by_keyword(
            keyword=self.keyword,
            page=1,
            page_size=20,
            sort=sort_type,
        )
        items: List[Dict[str, Any]] = notes_res.get("items", [])

        candidate_notes: List[Dict[str, Any]] = []
        for item in items:
            if item.get("model_type") in ("rec_query", "hot_query"):
                continue
            if not item.get("id"):
                continue
            if not item.get("xsec_token"):
                continue
            candidate_notes.append(item)
            if len(candidate_notes) >= self.max_notes_try:
                break

        if not candidate_notes:
            raise RuntimeError("未检索到可用笔记（缺少 id/xsec_token）")

        for note in candidate_notes:
            note_id = note["id"]
            xsec_token = note["xsec_token"]
            comments_res = await xhs_client.get_note_comments(note_id=note_id, xsec_token=xsec_token)
            comments: List[Dict[str, Any]] = comments_res.get("comments", [])
            if not comments:
                continue

            target = comments[0]
            if not target.get("id"):
                continue

            return note, target

        raise RuntimeError("已检索笔记，但未找到可回复的评论")

    async def app_main(self) -> None:
        self.crawler = XiaoHongShuCrawler()

        async with async_playwright() as playwright:
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[VerifyReplyLoopApp] Using CDP mode")
                self.browser_context = await self.crawler.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy=None,
                    user_agent=self.crawler.user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[VerifyReplyLoopApp] Using standard mode")
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

            note, comment = await self._pick_comment_target(xhs_client)
            note_id = note["id"]
            xsec_token = note.get("xsec_token", "")
            xsec_source = note.get("xsec_source", "pc_search")
            comment_id = comment["id"]

            reply_result = await xhs_client.post_comment(
                note_id=note_id,
                content=self.content,
                target_comment_id=comment_id,
                xsec_token=xsec_token,
                xsec_source=xsec_source,
            )

            output = {
                "step": "crawl_one_then_reply_one",
                "keyword": self.keyword,
                "note_id": note_id,
                "comment_id": comment_id,
                "reply_content": self.content,
                "reply_result": reply_result,
            }
            print(output)

    async def app_cleanup(self) -> None:
        if self.crawler:
            try:
                await self.crawler.close()
            except Exception as exc:
                utils.logger.warning("[VerifyReplyLoopApp] Cleanup failed: %s", exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="XHS 最小闭环验证：爬 1 条评论并回复")
    parser.add_argument("--keyword", default="", help="用于搜索笔记的关键词，默认取 config.KEYWORDS 第一项")
    parser.add_argument("--content", required=True, help="回复内容")
    parser.add_argument("--max-notes-try", type=int, default=5, help="最多尝试多少条笔记以找到可回复评论")
    return parser.parse_args()


def choose_keyword(raw_keyword: str) -> str:
    if raw_keyword:
        return raw_keyword
    parts = [item.strip() for item in config.KEYWORDS.split(",") if item.strip()]
    if not parts:
        raise RuntimeError("config.KEYWORDS 为空，无法执行最小闭环验证")
    return parts[0]


if __name__ == "__main__":
    args = parse_args()
    keyword = choose_keyword(args.keyword)
    app = VerifyReplyLoopApp(keyword=keyword, content=args.content, max_notes_try=args.max_notes_try)
    run(app.app_main, app.app_cleanup)

