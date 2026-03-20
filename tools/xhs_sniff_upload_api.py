# -*- coding: utf-8 -*-
"""调试工具：拦截小红书创作者中心的网络请求，找出真实的媒体上传 API 端点。

运行后会打开创作者中心，请在浏览器中手动操作「发布图文」，
当点击"上传图片"时脚本会打印捕获的请求信息。

用法：
    .venv/bin/python -m tools.xhs_sniff_upload_api
"""

import asyncio
import json
from typing import Optional

import config
from playwright.async_api import BrowserContext, Page, Request, async_playwright

from media_platform.xhs.core import XiaoHongShuCrawler
from tools import utils
from tools.app_runner import run


class SniffUploadApiApp:
    def __init__(self) -> None:
        self.crawler: Optional[XiaoHongShuCrawler] = None
        self.browser_context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def app_main(self) -> None:
        self.crawler = XiaoHongShuCrawler()

        async with async_playwright() as playwright:
            if config.ENABLE_CDP_MODE:
                self.browser_context = await self.crawler.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy=None,
                    user_agent=self.crawler.user_agent,
                    headless=False,
                )
            else:
                self.browser_context = await self.crawler.launch_browser(
                    playwright.chromium,
                    playwright_proxy=None,
                    user_agent=self.crawler.user_agent,
                    headless=False,
                )

            self.crawler.browser_context = self.browser_context
            self.page = await self.browser_context.new_page()
            self.crawler.context_page = self.page

            # 拦截所有 POST 请求，打印关键信息
            # 过滤掉纯监控/埋点域名
            SKIP_DOMAINS = ["apm-fe.xiaohongshu.com", "as.xiaohongshu.com"]

            async def on_request(req: Request) -> None:
                url = req.url
                method = req.method
                # 跳过监控域名
                if any(d in url for d in SKIP_DOMAINS):
                    return
                # 只关注小红书相关域名
                interesting = any(d in url for d in [
                    "xiaohongshu.com",
                    "xhscdn.com",
                    "sns-webpic",
                    "spectrum.xiaohongshu.com",
                ])
                if not interesting:
                    return
                try:
                    body = req.post_data or ""
                except Exception:
                    body = ""
                # 截断 body 避免二进制太长
                body_snippet = body[:2000] if isinstance(body, str) else "<binary>"
                # PUT 请求打印全部头；其他请求只打印关键头
                if method == "PUT":
                    all_headers = {k: v for k, v in req.headers.items()}
                    print(f"\n[SNIFF] {method} {url}")
                    print(f"  body_len: {len(body) if isinstance(body, str) else 'binary'}")
                    print(f"  ALL headers: {all_headers}")
                else:
                    print(f"\n[SNIFF] {method} {url}")
                    print(f"  body: {body_snippet}")
                    print(f"  headers: {json.dumps({k: v for k, v in req.headers.items() if k.lower() in ('content-type', 'x-s', 'x-t', 'authorization', 'uptoken')}, ensure_ascii=False)}")

            self.page.on("request", on_request)

            # 同时捕获 API 响应
            from playwright.async_api import Response as PlaywrightResponse

            async def on_response(resp: PlaywrightResponse) -> None:
                url = resp.url
                SKIP_DOMAINS = ["apm-fe.xiaohongshu.com", "as.xiaohongshu.com",
                                 "fe-static.xhscdn.com", "picasso-static",
                                 "fe.xiaohongshu.com", "t2.xiaohongshu.com"]
                if any(d in url for d in SKIP_DOMAINS):
                    return
                if not any(d in url for d in ["xiaohongshu.com", "xhscdn.com"]):
                    return
                # 只打印 API 类请求的响应
                if "/api/" not in url:
                    return
                try:
                    body = await resp.text()
                    body_snippet = body[:600]
                except Exception:
                    body_snippet = "<unreadable>"
                print(f"\n[RESP] {resp.status} {url}")
                print(f"  body: {body_snippet}")

            self.page.on("response", on_response)

            # 打开创作者中心发帖页
            target_url = "https://creator.xiaohongshu.com/publish/publish"
            print(f"\n正在打开: {target_url}")
            print("请在浏览器中手动点击「上传图片」并选择文件，脚本会打印捕获到的请求与响应。")
            print("按 Ctrl+C 退出。\n")
            await self.page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

            # 持续等待，让用户手动操作
            await asyncio.sleep(300)

    async def app_cleanup(self) -> None:
        if self.crawler:
            try:
                await self.crawler.close()
            except Exception:
                pass


if __name__ == "__main__":
    app = SniffUploadApiApp()
    run(app.app_main, app.app_cleanup)
