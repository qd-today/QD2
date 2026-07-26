# QD2 - HTTP Request Scheduled Task Automation Framework

> 基于 HAR Editor 的 HTTP 请求定时任务自动执行框架 v2

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 架构

QD2 采用前后端分离架构，由四个独立模块组成：

```
qd2/
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

# 启动后端开发服务器
uv run qd-server

# 启动前端开发服务器
cd qd-web && npm install && npm run dev
```

### Docker 部署

```bash
# 构建并启动
docker compose up -d

# 访问
open http://localhost:8080
```

## API 文档

启动后端后访问：
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

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
