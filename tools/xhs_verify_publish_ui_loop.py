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
import re
from typing import Optional

import config
from playwright.async_api import BrowserContext, Page, async_playwright

from media_platform.xhs.client import XiaoHongShuClient
from media_platform.xhs.core import XiaoHongShuCrawler
from tools import utils
from tools.app_runner import run


class VerifyPublishUiLoopApp:
    """纯 UI 最小闭环：打开发帖页 -> 填充标题正文 -> 尝试点击发布。"""

    def __init__(self, title: str, desc: str) -> None:
        self.title = title
        self.desc = desc
        self.crawler: Optional[XiaoHongShuCrawler] = None
        self.browser_context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def _ensure_login(self, xhs_client: XiaoHongShuClient) -> None:
        if await xhs_client.pong():
            utils.logger.info("[VerifyPublishUiLoopApp] Already logged in, skip login")
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

    async def _has_publish_editor(self, page: Page) -> bool:
        selectors = [
            "input[placeholder*='标题']",
            "textarea[placeholder*='标题']",
            "textarea[placeholder*='正文']",
            "textarea[placeholder*='描述']",
            "div[contenteditable='true']",
            "button:has-text('发布')",
            "button:has-text('立即发布')",
        ]
        for sel in selectors:
            try:
                if await page.locator(sel).count() > 0:
                    return True
            except Exception:
                pass

        for frame in page.frames:
            for sel in selectors:
                try:
                    if await frame.locator(sel).count() > 0:
                        return True
                except Exception:
                    pass
        return False

    async def _goto_publish_page(self, page: Page) -> bool:
        urls = [
            "https://creator.xiaohongshu.com/publish/publish",
            "https://www.xiaohongshu.com/publish/publish",
            "https://www.xiaohongshu.com/explore",
        ]
        for url in urls:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                if await self._has_publish_editor(page):
                    utils.logger.info(f"[VerifyPublishUiLoopApp] Found publish editor at: {url}")
                    return True

                # 兜底：在首页先点击“发布”入口，再次探测
                if "xiaohongshu.com/explore" in page.url:
                    publish_entry = page.locator("a:has-text('发布'), button:has-text('发布'), div:has-text('发布笔记')")
                    if await publish_entry.count() > 0:
                        try:
                            await publish_entry.first.click()
                            await asyncio.sleep(3)
                            if await self._has_publish_editor(page):
                                utils.logger.info("[VerifyPublishUiLoopApp] Found publish editor after clicking publish entry")
                                return True
                        except Exception:
                            pass
            except Exception as exc:
                utils.logger.warning(f"[VerifyPublishUiLoopApp] goto {url} failed: {exc}")
        return False

    async def _fill_text(self, page: Page) -> None:
        title_selectors = [
            "input[placeholder*='标题']",
            "textarea[placeholder*='标题']",
        ]
        desc_selectors = [
            "textarea[placeholder*='正文']",
            "textarea[placeholder*='描述']",
            "textarea[placeholder*='说点什么']",
            "div[contenteditable='true']",
        ]

        for sel in title_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0:
                try:
                    await loc.first.fill(self.title)
                    break
                except Exception:
                    pass

        for sel in desc_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0:
                try:
                    first = loc.first
                    tag = await first.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "div":
                        await first.click()
                        await page.keyboard.type(self.desc)
                    else:
                        await first.fill(self.desc)
                    break
                except Exception:
                    pass

    async def _try_click_publish(self, page: Page) -> bool:
        candidates = [
            "button:has-text('发布')",
            "button:has-text('立即发布')",
            "div[role='button']:has-text('发布')",
        ]
        for sel in candidates:
            loc = page.locator(sel)
            if await loc.count() > 0:
                try:
                    await loc.first.click()
                    await asyncio.sleep(2)
                    return True
                except Exception:
                    pass

        # role 兜底
        try:
            btn = page.get_by_role("button", name=re.compile("发布|立即发布"))
            if await btn.count() > 0:
                await btn.first.click()
                await asyncio.sleep(2)
                return True
        except Exception:
            pass
        return False

    async def _detect_publish_result(self, page: Page) -> str:
        success_keywords = ["发布成功", "笔记已发布", "发布完成"]
        fail_keywords = ["发布失败", "请稍后重试", "风控", "异常"]

        content = await page.content()
        for kw in success_keywords:
            if kw in content:
                return f"success:{kw}"
        for kw in fail_keywords:
            if kw in content:
                return f"failed:{kw}"
        return "unknown"

    async def app_main(self) -> None:
        self.crawler = XiaoHongShuCrawler()

        async with async_playwright() as playwright:
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[VerifyPublishUiLoopApp] Using CDP mode")
                self.browser_context = await self.crawler.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy=None,
                    user_agent=self.crawler.user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[VerifyPublishUiLoopApp] Using standard mode")
                self.browser_context = await self.crawler.launch_browser(
                    playwright.chromium,
                    playwright_proxy=None,
                    user_agent=self.crawler.user_agent,
                    headless=config.HEADLESS,
                )
                await self.browser_context.add_init_script(path="libs/stealth.min.js")

            self.crawler.browser_context = self.browser_context
            self.page = await self.browser_context.new_page()
            self.crawler.context_page = self.page
            await self.page.goto(self.crawler.index_url)

            xhs_client: XiaoHongShuClient = await self.crawler.create_xhs_client(httpx_proxy=None)
            await self._ensure_login(xhs_client)

            found_publish_page = await self._goto_publish_page(self.page)
            if not found_publish_page:
                raise RuntimeError(f"未找到可用发帖编辑页，当前URL={self.page.url}")

            await self._fill_text(self.page)
            clicked = await self._try_click_publish(self.page)
            await asyncio.sleep(3)
            result = await self._detect_publish_result(self.page)

            output = {
                "step": "ui_publish_one_note",
                "title": self.title,
                "desc": self.desc,
                "publish_mode": "text_only",
                "clicked_publish": clicked,
                "result": result,
                "note": "result=unknown 时建议人工确认页面状态",
            }
            print(output)

    async def app_cleanup(self) -> None:
        if self.crawler:
            try:
                await self.crawler.close()
            except Exception as exc:
                utils.logger.warning("[VerifyPublishUiLoopApp] Cleanup failed: %s", exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="XHS 纯UI发帖最小闭环")
    parser.add_argument("--title", default="MediaCrawler UI 发帖测试", help="发布标题")
    parser.add_argument("--desc", default="这是UI自动化发帖最小闭环测试。", help="发布正文")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    app = VerifyPublishUiLoopApp(title=args.title, desc=args.desc)
    run(app.app_main, app.app_cleanup)

