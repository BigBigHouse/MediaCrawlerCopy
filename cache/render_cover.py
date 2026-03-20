"""使用 Playwright 渲染 HTML 封面图，输出 JPG。"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def render():
    html = Path("/Users/hetingxin/PycharmProjects/MediaCrawler/cache/xhs_cover.html").resolve()
    out  = Path("/Users/hetingxin/PycharmProjects/MediaCrawler/cache/xhs_cover.jpg")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1080, "height": 1440})
        await page.goto(f"file://{html}", wait_until="networkidle")
        # 等字体 + 动画跑一帧
        await asyncio.sleep(1.2)
        await page.screenshot(path=str(out), type="jpeg", quality=96,
                              full_page=False, clip={"x":0,"y":0,"width":1080,"height":1440})
        await browser.close()
    print(f"saved: {out}")

asyncio.run(render())
