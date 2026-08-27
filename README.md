# QD2 - HTTP Request Scheduled Task Automation Framework

> 基于 HAR Editor 的 HTTP 请求定时任务自动执行框架 v2

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 架构

QD2 采用前后端分离架构，由四个独立模块组成：

```
qd2/
├── docker/       # Dockerfile、Compose 和带中文注释的环境配置
├── qd-core/      # 核心库：插件系统、HAR 解析、HTTP 客户端
├── qd-cli/       # 命令行工具：终端执行 HAR 模板
├── qd-server/    # 后端服务：FastAPI + JWT + 数据库
├── qd-web/       # 前端界面：Vue 3 + Element Plus
└── pyproject.toml # uv workspace 配置
```

## 技术栈

| 模块 | 技术 |
|------|------|
| QD Core | Python 3.10+ / aiohttp / plux / pydantic |
| QD CLI | Python / Typer / Rich |
| QD Server | Python / FastAPI / SQLAlchemy (async) / PyJWT |
| QD Web | Vue 3 / TypeScript / Element Plus / Pinia / Vite |

## 快速开始

### 开发环境

```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 同步依赖
uv sync --all-packages

# 启动后端开发服务器（端口 8923）
uv run qd-server

# 启动前端开发服务器（端口 8924，代理到后端 8923）
cd qd-web && npm install && npm run dev
```

### Docker 部署

```bash
# 进入 Docker 配置目录
cd docker

# 按需修改 .env，然后构建并启动
docker compose up -d --build

# 访问
open http://localhost:8923
```

所有 Docker 环境变量集中在 [`docker/.env`](docker/.env)，每项均附有中文说明。任务并发数默认是 5，可通过其中的 `QD_MAX_CONCURRENT_TASKS` 修改。任务请求上限、运行超时、登录限流、敏感数据加密、SMTP TLS 和 WebSocket 参数也可在该文件调整，完整列表见 [USAGE.md](USAGE.md#环境变量)。配置中不包含全局代理功能。

发布工作流会在手动触发或推送新 Tag 时构建 `linux/amd64`、`linux/arm64`、`linux/arm/v7` 镜像并推送到 `ghcr.io/qd-today/qd2`。Tag 构建还会创建 GitHub Release，并附带 `.tar.gz` 和 `.zip` 源码包。

## API 文档

启动后端后访问：
- Swagger UI: http://localhost:8923/docs
- ReDoc: http://localhost:8923/redoc

## 开发

```bash
# 运行测试
uv run pytest

# 代码检查
uv run ruff check .
uv run mypy

# 前端构建
cd qd-web && npm run build
```

## 许可证

[MIT License](LICENSE)
