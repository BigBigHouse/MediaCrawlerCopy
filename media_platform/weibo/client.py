# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/weibo/client.py
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

# -*- coding: utf-8 -*-
# @Author  : relakkes@gmail.com
# @Time    : 2023/12/23 15:40
# @Desc    : Weibo crawler API request client

import asyncio
import copy
import json
import re
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Union
from urllib.parse import parse_qs, unquote, urlencode

import httpx
from httpx import Response
from playwright.async_api import BrowserContext, Page
from tools.httpx_util import make_async_client
from tenacity import retry, stop_after_attempt, wait_fixed

import config
from proxy.proxy_mixin import ProxyRefreshMixin
from tools import utils

if TYPE_CHECKING:
    from proxy.proxy_ip_pool import ProxyIpPool

from .exception import DataFetchError
from .field import SearchType


class WeiboClient(ProxyRefreshMixin):

    def __init__(
        self,
        timeout=60,  # If media crawling is enabled, Weibo images need a longer timeout
        proxy=None,
        *,
        headers: Dict[str, str],
        playwright_page: Page,
        cookie_dict: Dict[str, str],
        proxy_ip_pool: Optional["ProxyIpPool"] = None,
    ):
        self.proxy = proxy
        self.timeout = timeout
        self.headers = headers
        self._host = "https://m.weibo.cn"
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        self._image_agent_host = "https://i1.wp.com/"
        # Initialize proxy pool (from ProxyRefreshMixin)
        self.init_proxy_pool(proxy_ip_pool)

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(3))
    async def request(self, method, url, **kwargs) -> Union[Response, Dict]:
        # Check if proxy is expired before each request
        await self._refresh_proxy_if_expired()

        enable_return_response = kwargs.pop("return_response", False)
        async with make_async_client(proxy=self.proxy) as client:
            response = await client.request(method, url, timeout=self.timeout, **kwargs)

        if enable_return_response:
            return response

        try:
            data: Dict = response.json()
        except json.decoder.JSONDecodeError:
            # issue: #771 Search API returns error 432, retry multiple times + update h5 cookies
            utils.logger.error(f"[WeiboClient.request] request {method}:{url} err code: {response.status_code} res:{response.text}")
            await self.playwright_page.goto(self._host)
            await asyncio.sleep(2)
            await self.update_cookies(browser_context=self.playwright_page.context)
            raise DataFetchError(f"get response code error: {response.status_code}")

        ok_code = data.get("ok")
        if ok_code == 0:  # response error
            utils.logger.error(f"[WeiboClient.request] request {method}:{url} err, res:{data}")
            raise DataFetchError(data.get("msg", "response error"))
        elif ok_code != 1:  # unknown error
            utils.logger.error(f"[WeiboClient.request] request {method}:{url} err, res:{data}")
            raise DataFetchError(data.get("msg", "unknown error"))
        else:  # response right
            return data.get("data", {})

    async def get(self, uri: str, params=None, headers=None, **kwargs) -> Union[Response, Dict]:
        final_uri = uri
        if isinstance(params, dict):
            final_uri = (f"{uri}?"
                         f"{urlencode(params)}")

        if headers is None:
            headers = self.headers
        return await self.request(method="GET", url=f"{self._host}{final_uri}", headers=headers, **kwargs)

    async def post(self, uri: str, data: dict) -> Dict:
        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        return await self.request(method="POST", url=f"{self._host}{uri}", data=json_str, headers=self.headers)

    async def pong(self) -> bool:
        """get a note to check if login state is ok"""
        utils.logger.info("[WeiboClient.pong] Begin pong weibo...")
        ping_flag = False
        try:
            uri = "/api/config"
            resp_data: Dict = await self.request(method="GET", url=f"{self._host}{uri}", headers=self.headers)
            if resp_data.get("login"):
                ping_flag = True
            else:
                utils.logger.error(f"[WeiboClient.pong] cookie may be invalid and again login...")
        except Exception as e:
            utils.logger.error(f"[WeiboClient.pong] Pong weibo failed: {e}, and try to login again...")
            ping_flag = False
        return ping_flag

    async def update_cookies(self, browser_context: BrowserContext, urls: Optional[List[str]] = None):
        """
        Update cookies from browser context
        :param browser_context: Browser context
        :param urls: Optional list of URLs to filter cookies (e.g., ["https://m.weibo.cn"])
                     If provided, only cookies for these URLs will be retrieved
        """
        if urls:
            cookies = await browser_context.cookies(urls=urls)
            utils.logger.info(f"[WeiboClient.update_cookies] Updating cookies for specific URLs: {urls}")
        else:
            cookies = await browser_context.cookies()
            utils.logger.info("[WeiboClient.update_cookies] Updating all cookies")

        cookie_str, cookie_dict = utils.convert_cookies(cookies)
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict
        utils.logger.info(f"[WeiboClient.update_cookies] Cookie updated successfully, total: {len(cookie_dict)} cookies")

    async def get_note_by_keyword(
        self,
        keyword: str,
        page: int = 1,
        search_type: SearchType = SearchType.DEFAULT,
    ) -> Dict:
        """
        search note by keyword
        :param keyword: Search keyword for Weibo
        :param page: Pagination parameter - current page number
        :param search_type: Search type, see SearchType enum in weibo/field.py
        :return:
        """
        uri = "/api/container/getIndex"
        containerid = f"100103type={search_type.value}&q={keyword}"
        params = {
            "containerid": containerid,
            "page_type": "searchall",
            "page": page,
        }
        return await self.get(uri, params)

    async def get_note_comments(self, mid_id: str, max_id: int, max_id_type: int = 0) -> Dict:
        """get notes comments
        :param mid_id: Weibo ID
        :param max_id: Pagination parameter ID
        :param max_id_type: Pagination parameter ID type
        :return:
        """
        uri = "/comments/hotflow"
        params = {
            "id": mid_id,
            "mid": mid_id,
            "max_id_type": max_id_type,
        }
        if max_id > 0:
            params.update({"max_id": max_id})
        referer_url = f"https://m.weibo.cn/detail/{mid_id}"
        headers = copy.copy(self.headers)
        headers["Referer"] = referer_url

        return await self.get(uri, params, headers=headers)

    async def get_note_all_comments(
        self,
        note_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        max_count: int = 10,
    ):
        """
        get note all comments include sub comments
        :param note_id:
        :param crawl_interval:
        :param callback:
        :param max_count:
        :return:
        """
        result = []
        is_end = False
        max_id = -1
        max_id_type = 0
        while not is_end and len(result) < max_count:
            comments_res = await self.get_note_comments(note_id, max_id, max_id_type)
            max_id: int = comments_res.get("max_id")
            max_id_type: int = comments_res.get("max_id_type")
            comment_list: List[Dict] = comments_res.get("data", [])
            is_end = max_id == 0
            if len(result) + len(comment_list) > max_count:
                comment_list = comment_list[:max_count - len(result)]
            if callback:  # If callback function exists, execute it
                await callback(note_id, comment_list)
            await asyncio.sleep(crawl_interval)
            result.extend(comment_list)
            sub_comment_result = await self.get_comments_all_sub_comments(note_id, comment_list, callback)
            result.extend(sub_comment_result)
        return result

    @staticmethod
    async def get_comments_all_sub_comments(
        note_id: str,
        comment_list: List[Dict],
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """
        Get all sub-comments of comments
        Args:
            note_id:
            comment_list:
            callback:

        Returns:

        """
        if not config.ENABLE_GET_SUB_COMMENTS:
            utils.logger.info(f"[WeiboClient.get_comments_all_sub_comments] Crawling sub_comment mode is not enabled")
            return []

        res_sub_comments = []
        for comment in comment_list:
            sub_comments = comment.get("comments")
            if sub_comments and isinstance(sub_comments, list):
                await callback(note_id, sub_comments)
                res_sub_comments.extend(sub_comments)
        return res_sub_comments

    async def get_note_info_by_id(self, note_id: str) -> Dict:
        """
        Get note details by note ID
        :param note_id:
        :return:
        """
        url = f"{self._host}/detail/{note_id}"
        async with make_async_client(proxy=self.proxy) as client:
            response = await client.request("GET", url, timeout=self.timeout, headers=self.headers)
            if response.status_code != 200:
                raise DataFetchError(f"get weibo detail err: {response.text}")
            match = re.search(r'var \$render_data = (\[.*?\])\[0\]', response.text, re.DOTALL)
            if match:
                render_data_json = match.group(1)
                render_data_dict = json.loads(render_data_json)
                note_detail = render_data_dict[0].get("status")
                note_item = {"mblog": note_detail}
                return note_item
            else:
                utils.logger.info(f"[WeiboClient.get_note_info_by_id] $render_data value not found")
                return dict()

    async def get_note_image(self, image_url: str) -> bytes:
        image_url = image_url[8:]  # Remove https://
        sub_url = image_url.split("/")
        image_url = ""
        for i in range(len(sub_url)):
            if i == 1:
                image_url += "large/"  # Get high-resolution images
            elif i == len(sub_url) - 1:
                image_url += sub_url[i]
            else:
                image_url += sub_url[i] + "/"
        # Weibo image hosting has anti-hotlinking, so proxy access is needed
        # Since Weibo images are accessed through i1.wp.com, we need to concatenate the URL
        final_uri = (f"{self._image_agent_host}"
                     f"{image_url}")
        async with make_async_client(proxy=self.proxy) as client:
            try:
                response = await client.request("GET", final_uri, timeout=self.timeout)
                response.raise_for_status()
                if not response.reason_phrase == "OK":
                    utils.logger.error(f"[WeiboClient.get_note_image] request {final_uri} err, res:{response.text}")
                    return None
                else:
                    return response.content
            except httpx.HTTPError as exc:  # some wrong when call httpx.request method, such as connection error, client error, server error or response status code is not 2xx
                utils.logger.error(f"[DouYinClient.get_aweme_media] {exc.__class__.__name__} for {exc.request.url} - {exc}")    # Keep original exception type name for developer debugging
                return None

    async def get_creator_container_info(self, creator_id: str) -> Dict:
        """
        Get user's container ID, container information represents the real API request path
            fid_container_id: Container ID for user's Weibo detail API
            lfid_container_id: Container ID for user's Weibo list API
        Args:
            creator_id: User ID

        Returns: Dictionary with container IDs

        """
        response = await self.get(f"/u/{creator_id}", return_response=True)
        m_weibocn_params = response.cookies.get("M_WEIBOCN_PARAMS")
        if not m_weibocn_params:
            raise DataFetchError("get containerid failed")
        m_weibocn_params_dict = parse_qs(unquote(m_weibocn_params))
        return {"fid_container_id": m_weibocn_params_dict.get("fid", [""])[0], "lfid_container_id": m_weibocn_params_dict.get("lfid", [""])[0]}

    async def get_creator_info_by_id(self, creator_id: str) -> Dict:
        """
        Get user details by user ID
        Args:
            creator_id:

        Returns:

        """
        uri = "/api/container/getIndex"
        containerid = f"100505{creator_id}"
        params = {
            "jumpfrom": "weibocom",
            "type": "uid",
            "value": creator_id,
            "containerid":containerid,
        }
        user_res = await self.get(uri, params)
        return user_res

    async def get_notes_by_creator(
        self,
        creator: str,
        container_id: str,
        since_id: str = "0",
    ) -> Dict:
        """
        Get creator's notes
        Args:
            creator: Creator ID
            container_id: Container ID
            since_id: ID of the last note from previous page
        Returns:

        """

        uri = "/api/container/getIndex"
        params = {
            "jumpfrom": "weibocom",
            "type": "uid",
            "value": creator,
            "containerid": container_id,
            "since_id": since_id,
        }
        return await self.get(uri, params)

    def _get_st_token(self) -> str:
        """从 Cookie 中提取 CSRF Token（st）"""
        return self.cookie_dict.get("XSRF-TOKEN", "")

    @staticmethod
    def _parse_upload_pic_id(text: str) -> str:
        """解析 picupload.weibo.com 的混合 HTML+JSON 响应，提取 pic_id。

        响应格式：
            <meta ...><script ...></script>
            {"code":"A00006","data":{"count":1,"data":"<base64>","..."}}

        base64 解码后：
            {"uid":..., "pics":{"pic_1":{"pid":"007UiXXX..."}}}
        """
        import base64
        import json as _json

        # 1. 从混合响应里提取 JSON 部分（找第一个 { 到结尾）
        json_start = text.find("{")
        if json_start == -1:
            return ""
        try:
            outer = _json.loads(text[json_start:])
        except Exception:
            return ""

        # 2. 检查 code（A00006 = 成功）
        code = outer.get("code", "")
        if code and not code.startswith("A00006"):
            utils.logger.warning(f"[WeiboClient] 图片上传返回非成功 code={code}")

        # 3. 解码 data.data（base64）
        raw_data = outer.get("data", {})
        b64_str: str = raw_data.get("data", "")
        if b64_str:
            try:
                inner_json = base64.b64decode(b64_str + "==").decode("utf-8", errors="ignore")
                inner = _json.loads(inner_json)
                pics: dict = inner.get("pics", {})
                # 取第一张图的 pid
                for pic_info in pics.values():
                    if isinstance(pic_info, dict) and pic_info.get("pid"):
                        return pic_info["pid"]
            except Exception as e:
                utils.logger.warning(f"[WeiboClient] base64 decode failed: {e}")

        # 4. 直接从 data 层取 pic_id
        for key in ("pic_id", "picid", "pid"):
            v = raw_data.get(key, "")
            if v:
                return str(v)

        # 5. XML 兜底
        for tag in ("pic_id", "picid", "pid"):
            m = re.search(rf"<{tag}>([^<]+)</{tag}>", text, re.IGNORECASE)
            if m:
                return m.group(1).strip()

        return ""

    async def upload_pic(self, image_path: str) -> str:
        """上传图片到微博，返回 pic_id。

        使用 m.weibo.cn 同域接口，pic_id 与当前 session 绑定，可直接用于发布。

        Args:
            image_path: 本地图片路径

        Returns:
            pic_id 字符串，发布微博时用 picId 字段传入
        """
        import mimetypes
        from pathlib import Path

        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"图片文件不存在：{image_path}")

        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg"

        with open(image_path, "rb") as fh:
            content = fh.read()

        st = self._get_st_token()
        # picupload.weibo.com 是 weibo.com 子域，m.weibo.cn 的 cookie 完全适用
        upload_url = "https://picupload.weibo.com/interface/pic_upload.php"
        headers = {
            **self.headers,
            "X-XSRF-TOKEN": st,
            "Origin": "https://m.weibo.cn",
            "Referer": "https://m.weibo.cn/",
        }
        headers.pop("Content-Type", None)

        async with make_async_client(proxy=self.proxy) as client:
            response = await client.request(
                "POST",
                upload_url,
                headers=headers,
                files={"pic1": (path.name, content, mime_type)},
                data={"st": st, "s": "json"},   # 请求 JSON 格式响应
                timeout=self.timeout,
            )

        utils.logger.info(
            f"[WeiboClient.upload_pic] status={response.status_code} "
            f"response={response.text[:500]}"
        )

        if response.status_code != 200:
            raise DataFetchError(f"图片上传失败，status={response.status_code}, body={response.text[:200]}")

        text = response.text.strip()
        pic_id = self._parse_upload_pic_id(text)
        utils.logger.info(f"[WeiboClient.upload_pic] 提取到 pic_id={pic_id!r}")

        if not pic_id:
            raise DataFetchError(f"图片上传响应中未找到 pic_id，响应：{text[:400]}")

        utils.logger.info(f"[WeiboClient.upload_pic] 图片上传成功，pic_id={pic_id}")
        return pic_id

    async def publish_weibo(
        self,
        content: str,
        pic_ids: Optional[List[str]] = None,
    ) -> Dict:
        """发布微博。

        Args:
            content:  微博正文（纯文本，话题用 #话题名# 格式）
            pic_ids:  已上传图片的 pic_id 列表（最多 9 张）

        Returns:
            微博数据字典，包含 id、idstr 等字段
        """
        st = self._get_st_token()
        uri = "/api/statuses/update"
        payload: Dict = {
            "content": content,
            "st": st,
            "visible": 0,
        }
        if pic_ids:
            payload["picId"] = ",".join(pic_ids)

        headers = {
            **self.headers,
            "X-XSRF-TOKEN": st,
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": "https://m.weibo.cn/compose/",
        }
        import json as _json
        async with make_async_client(proxy=self.proxy) as client:
            response = await client.request(
                "POST",
                f"{self._host}{uri}",
                headers=headers,
                content=_json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=self.timeout,
            )

        try:
            data = response.json()
        except Exception:
            raise DataFetchError(f"发布微博响应解析失败：{response.text[:200]}")

        utils.logger.info(f"[WeiboClient.publish_weibo] response={data}")

        ok_code = data.get("ok")
        if ok_code != 1:
            raise DataFetchError(f"发布微博失败：{data.get('msg', data)}")

        weibo_data: Dict = data.get("data", {})
        weibo_id = weibo_data.get("id") or weibo_data.get("idstr", "")
        utils.logger.info(f"[WeiboClient.publish_weibo] 发布成功，weibo_id={weibo_id}")
        return weibo_data

    async def post_comment(
        self,
        weibo_id: str,
        content: str,
        comment_id: str = "",
    ) -> Dict:
        """回复微博评论。

        Args:
            weibo_id:   微博 ID
            content:    回复内容
            comment_id: 要回复的评论 ID（为空则评论微博本身）

        Returns:
            评论数据字典
        """
        st = self._get_st_token()
        uri = "/api/comments/create"
        form_data: Dict[str, str] = {
            "content": content,
            "mid": weibo_id,
            "st": st,
            "_spr": "screen:1470x956",
        }
        if comment_id:
            form_data["comment_ori"] = comment_id

        headers = {
            **self.headers,
            "X-XSRF-TOKEN": st,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"https://m.weibo.cn/detail/{weibo_id}",
        }
        async with make_async_client(proxy=self.proxy) as client:
            response = await client.request(
                "POST",
                f"{self._host}{uri}",
                headers=headers,
                data=form_data,
                timeout=self.timeout,
            )

        try:
            data = response.json()
        except Exception:
            raise DataFetchError(f"回复评论响应解析失败：{response.text[:200]}")

        utils.logger.info(f"[WeiboClient.post_comment] response={data}")

        ok_code = data.get("ok")
        if ok_code != 1:
            raise DataFetchError(f"回复评论失败：{data.get('msg', data)}")

        comment_data: Dict = data.get("data", {})
        comment_result_id = comment_data.get("id") or comment_data.get("idstr", "")
        utils.logger.info(f"[WeiboClient.post_comment] 回复成功，comment_id={comment_result_id}")
        return comment_data

    async def get_all_notes_by_creator_id(
        self,
        creator_id: str,
        container_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """
        Get all posts published by a specified user, this method will continuously fetch all posts from a user
        Args:
            creator_id: Creator user ID
            container_id: Container ID for the user
            crawl_interval: Interval between requests in seconds
            callback: Optional callback function to process notes

        Returns: List of all notes

        """
        result = []
        notes_has_more = True
        since_id = ""
        crawler_total_count = 0
        while notes_has_more:
            notes_res = await self.get_notes_by_creator(creator_id, container_id, since_id)
            if not notes_res:
                utils.logger.error(f"[WeiboClient.get_notes_by_creator] The current creator may have been banned by Weibo, so they cannot access the data.")
                break
            since_id = notes_res.get("cardlistInfo", {}).get("since_id", "0")
            if "cards" not in notes_res:
                utils.logger.info(f"[WeiboClient.get_all_notes_by_creator] No 'notes' key found in response: {notes_res}")
                break

            notes = notes_res["cards"]
            utils.logger.info(f"[WeiboClient.get_all_notes_by_creator] got user_id:{creator_id} notes len : {len(notes)}")
            notes = [note for note in notes if note.get("card_type") == 9]
            if callback:
                await callback(notes)
            await asyncio.sleep(crawl_interval)
            result.extend(notes)
            crawler_total_count += 10
            notes_has_more = notes_res.get("cardlistInfo", {}).get("total", 0) > crawler_total_count
        return result
