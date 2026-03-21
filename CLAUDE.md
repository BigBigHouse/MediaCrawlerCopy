# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

MediaCrawler 是一个多平台社交媒体爬虫框架，支持小红书(xhs)、抖音(dy)、快手(ks)、B站(bili)、微博(wb)、百度贴吧(tieba)、知乎(zhihu)共7个平台。基于 Playwright 浏览器自动化，无需JS逆向，通过保留登录态的浏览器上下文获取签名参数。许可证为 NON-COMMERCIAL LEARNING LICENSE 1.1（仅供学习研究使用）。

## 常用命令

**环境依赖**（Python ≥ 3.11）：
```bash
uv sync                        # 安装/同步依赖
uv run playwright install      # 安装浏览器驱动
pre-commit install              # 启用 git hooks
```

**运行爬虫**：
```bash
uv run main.py --platform xhs --lt qrcode --type search
uv run main.py --platform dy --lt cookie --type detail
uv run main.py --help
```

**运行 WebUI**：
```bash
uv run uvicorn api.main:app --port 8080 --reload
```

**初始化数据库**：
```bash
uv run main.py --init_db sqlite
uv run main.py --init_db mysql
uv run main.py --init_db postgres
```

**运行测试**：
```bash
uv run pytest test/             # 单元测试
uv run pytest tests/            # 集成测试
uv run pytest test/test_proxy_ip_pool.py  # 运行单个测试文件
```

**代码检查**：
```bash
pre-commit run --all-files      # 运行所有 pre-commit 检查
```

**scripts/ 目录脚本**（小红书发帖/回复等功能）：
```bash
./scripts/xhs_publish.sh image --title "标题" --desc "正文" --images ./img.jpg
./scripts/reply_one_comment.sh
```

## 代码架构

### 核心层次结构

```
base/base_crawler.py         ← 抽象基类：AbstractCrawler, AbstractLogin, AbstractStore, AbstractApiClient
media_platform/{platform}/   ← 各平台爬虫实现
store/{platform}/            ← 各平台存储实现
database/                    ← ORM 层
config/                      ← 配置管理
```

### 各平台标准结构

每个 `media_platform/{platform}/` 目录包含：
- `core.py` — 爬虫主类，继承 `AbstractCrawler`，管理浏览器生命周期、搜索/详情/创作者爬取
- `client.py` — API 客户端，继承 `AbstractApiClient + ProxyRefreshMixin`，封装 HTTP 请求和 Cookie 管理
- `login.py` — 登录实现，继承 `AbstractLogin`，支持二维码、手机号、Cookie 三种登录方式
- `field.py` — 字段枚举常量定义
- `help.py` — 辅助函数

### 存储层工厂模式

`store/{platform}/` 下各平台的存储类继承 `AbstractStore`，实现 `store_content()`、`store_comment()`、`store_creator()` 三个方法。通过 `StoreFactory.STORES` 字典注册，支持：csv、json、jsonl（默认）、sqlite、db（MySQL）、mongodb、excel、postgres 共8种存储方式。

### 关键设计模式

| 模式 | 位置 |
|------|------|
| 工厂模式 | `main.py::CrawlerFactory`、各平台 `StoreFactory` |
| 模板方法 | `base/base_crawler.py::AbstractCrawler` 定义爬虫流程骨架 |
| Mixin 模式 | `proxy/proxy_mixin.py::ProxyRefreshMixin` 混入到各平台 client |
| Context 变量 | `var.py` 中用 `ContextVar` 管理全局上下文（关键词、爬虫类型、评论任务等） |

### 配置系统

- `config/base_config.py` — 所有平台通用配置（平台选择、登录方式、爬虫类型、代理、存储等）
- `config/{platform}_config.py` — 平台特定配置
- `config/db_config.py` — 数据库连接配置
- `cmd_arg/arg.py` — 命令行参数（Typer 框架），参数会覆盖 config 中的默认值

### 代理与缓存基础设施

- `proxy/proxy_ip_pool.py::ProxyIpPool` — IP 池核心，支持快代理、万代理等提供商
- `cache/cache_factory.py` — 本地缓存或 Redis 缓存，通过工厂创建
- `tools/cdp_browser.py` — CDP 模式连接已有 Chrome/Edge 浏览器（增强反检测）

### 浏览器模式

- **标准模式**：Playwright 启动独立浏览器实例
- **CDP 模式**（`ENABLE_CDP_MODE = True`）：通过 DevTools Protocol 连接用户已启动的浏览器，端口默认 9222

### 数据模型

- `model/m_{platform}.py` — Pydantic v2 数据模型，用于数据验证和序列化
- `database/models.py` — SQLAlchemy ORM 模型（内容表、评论表、创作者表）
- `database/db_session.py` — 异步数据库会话和连接池管理

### 扩展指南

**添加新平台**：
1. 在 `media_platform/` 创建目录，实现 `core.py`、`client.py`、`login.py`、`field.py`
2. 在 `store/` 创建对应存储实现
3. 在 `main.py::CrawlerFactory.CRAWLERS` 注册
4. 在 `model/` 添加 Pydantic 模型，在 `database/models.py` 添加 ORM 模型

**添加新存储方式**：
1. 继承 `AbstractStore`，实现三个 store 方法
2. 在各平台 `StoreFactory.STORES` 注册

## 项目规范

- Python 文件每个模块不超过 400 行
- `scripts/` 目录维护运行脚本，所有启停操作使用 `.sh` 脚本
- Pre-commit hooks 会自动检查版权头、格式规范
- 文档写到 `docs/`（正式文档）或 `discuss/`（讨论评审）
