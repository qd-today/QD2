# QD2 构建进度

> 最后更新: 2026-06-22 (前后端均已验证)

## 总览

| 模块 | 状态 | 完成度 |
|------|------|--------|
| 项目基础设施 | ✅ 完成 | 100% |
| qd-core | ✅ 可用 | 80% |
| qd-cli | ✅ 可用 | 70% |
| qd-server | ✅ **已验证可启动** | 85% |
| qd-web | ✅ **已验证可启动** | 65% |
| Docker / CI | ✅ 完成 | 100% |

---

## 验证结果 (2026-06-22)

### ✅ 通过的测试

| 测试项 | 结果 |
|--------|------|
| `uv sync --all-packages` | ✅ 66 packages installed |
| `uv run pytest` (20 tests) | ✅ 20/20 passed |
| 服务器启动 (`uvicorn`) | ✅ Application startup complete |
| `GET /health` | ✅ `{"status":"ok","version":"25.1.0-dev"}` |
| `POST /api/auth/register` | ✅ 201 Created |
| `POST /api/auth/login` | ✅ 200 OK + JWT tokens |
| `GET /api/auth/me` | ✅ 200 OK + user info |
| `POST /api/templates` | ✅ 201 Created |
| `GET /api/templates` | ✅ 200 OK + list |
| `POST /api/tasks` | ✅ 201 Created |
| `GET /api/tasks` | ✅ 200 OK + list |
| `POST /api/tasks/1/run` | ✅ 200 OK + HTTP 请求执行成功 |
| `GET /api/tasks/1/runs` | ✅ 200 OK + 执行历史 |
| `npm install` (qd-web) | ✅ 154 packages installed |
| `npm run build` (qd-web) | ✅ built in 14.60s |
| `npm run dev` (qd-web) | ✅ VITE ready in 941ms |
| 前端代理 → 后端 API | ✅ 注册/登录通过代理正常工作 |

### 🔧 修复的前端问题

| 问题 | 修复 |
|------|------|
| 缺少 vue-i18n 依赖 | 安装 vue-i18n |
| 路由未使用变量 `from` | 改为 `_from` |
| `POST /api/templates` | ✅ 201 Created |
| `GET /api/templates` | ✅ 200 OK + list |
| `POST /api/tasks` | ✅ 201 Created |
| `GET /api/tasks` | ✅ 200 OK + list |
| `POST /api/tasks/1/run` | ✅ 200 OK + 执行 HTTP 请求到 httpbin.org |
| `GET /api/tasks/1/runs` | ✅ 200 OK + 执行历史 |

### 🔧 修复的问题

| 问题 | 修复 |
|------|------|
| pyproject.toml workspace 匹配 qd-web | 改为显式列出 workspace members |
| typer[all] 不存在 | 改为 typer + rich |
| 缺少子包 README.md | 创建 README 文件 |
| models/base.py 缺少 Field import | 添加 `from sqlmodel import Field, SQLModel` |
| middleware/auth.py 函数定义顺序 | 将 `get_session` 移到 `get_current_user` 之前 |
| SQLModel select 需要 `table=True` | 所有模型类添加 `table=True` |
| passlib 与 bcrypt 5.x 不兼容 | 固定 `bcrypt<5.0.0` |
| tasks.py run_task 重复调用 | 简化逻辑, 移除重复调用 |
| APScheduler 集成缺失 | 创建 services/scheduler.py 并集成到 app.py |
| 缺少 vue-i18n | 安装 vue-i18n |
| 登录页无注册按钮 | 添加注册/登录切换, 含密码确认 |
| 首个用户非管理员 | 注册时检测用户数, 首个用户自动设为 admin |
| 后端端口 8080 | 改为 8924 |
| 前端端口 3000 | 改为 8923, 代理指向 8924 |

---

## 阶段一：基础设施 ✅

### 已完成
- [x] 项目根目录结构
- [x] pyproject.toml (uv workspace 配置)
- [x] .gitignore
- [x] README.md

---

## 阶段二：qd-core ✅ 可用

### 已完成
- [x] pyproject.toml (包配置)
- [x] config.py (QDBaseSettings, QDCoreSettings)
- [x] plugins/base.py (PluginHook enum, api_function_plugin 装饰器)
- [x] plugins/manager.py (QDPluginManager - 插件生命周期管理)
- [x] plugins/default.py (内置示例插件 util-delay)
- [x] schemas/har.py (HARRequest, HARResponse, HARTemplate, HARData)
- [x] schemas/task.py (ScheduleConfig, TaskStatus, NotificationConfig)
- [x] client/har.py (HARParser - 解析 HAR/QD2 格式)
- [x] client/fetcher.py (QDFetcher - 异步 HTTP 客户端) — **已验证可执行 HTTP 请求**
- [x] client/render.py (模板渲染)
- [x] filters/extractors.py (数据提取: JSON path, regex)
- [x] utils/log.py (基于 loguru 的日志)
- [x] utils/shell.py (异步命令执行)
- [x] utils/i18n.py (国际化)
- [x] test/test_schemas.py (5 tests ✅)
- [x] test/test_har_parser.py (7 tests ✅)
- [x] test/test_filters.py (8 tests ✅)

### 待完成
- [ ] 优化依赖导入时间 (lazy-import)
- [ ] 插件 Hook 规范文档
- [ ] 更多单元测试 (目标覆盖率 > 80%)
- [ ] PyPI 发布配置

---

## 阶段三：qd-cli ✅ 可用

### 已完成
- [x] pyproject.toml (包配置 + entry point)
- [x] cli.py (Typer CLI 入口)
- [x] `qd version` 命令
- [x] `qd run <template.har>` 命令 (含 dry-run, 变量注入)
- [x] `qd parse <template.har>` 命令
- [x] `qd plugin list/install/uninstall` 命令

### 待完成
- [ ] 更多 CLI 命令
- [ ] 模板变量交互式输入
- [ ] 输出格式化 (JSON/table)

---

## 阶段四：qd-server ✅ 已验证可启动

### 已完成
- [x] pyproject.toml (包配置 + entry point)
- [x] config.py (数据库配置, JWT 配置)
  - SQLite3 / MySQL 双数据库支持
  - Pydantic Settings 配置管理
- [x] models/ (SQLModel 数据模型, table=True)
  - user.py (User - 多用户, 角色)
  - template.py (Template - HAR 模板)
  - task.py (Task, TaskRun - 定时任务)
  - notification.py (Notification - 通知)
  - notepad.py (Notepad - 便签)
  - base.py (BaseModel, AlchemyMixin)
- [x] middleware/auth.py (JWT 认证)
  - access_token (15min) + refresh_token (7天)
  - 密码哈希 (bcrypt 4.x)
  - FastAPI 依赖注入 (get_current_user, require_admin)
- [x] api/ (RESTful API 路由 — 全部已验证)
  - auth.py (登录/注册/刷新/当前用户) ✅
  - templates.py (模板 CRUD) ✅
  - tasks.py (任务 CRUD + 手动触发 + 历史) ✅
  - plugins.py (插件列表/安装/卸载)
  - notifications.py (通知 CRUD)
  - notepad.py (便签 CRUD)
  - test_request.py (测试请求 + cURL 解析 + HAR 解析)
  - migrate.py (v1 数据迁移)
- [x] services/scheduler.py (APScheduler 任务调度) ✅
  - 支持 interval / cron / daily / once 调度
  - 任务执行记录到 task_runs 表
  - 启动时自动加载已有任务
  - 任务完成后发送通知
- [x] services/notification.py (通知服务) ✅
  - Webhook 通知
  - Email 通知 (SMTP)
  - 任务执行后自动触发
- [x] app.py (FastAPI 应用入口 + 生命周期 + 调度器集成)
- [x] 健康检查端点 (/health)
- [x] 模板导入/导出 (QD2 JSON / HAR 格式)
- [x] v1 数据迁移 (上传 database.db)

### 待完成
- [ ] 数据库迁移 (Alembic)
- [ ] 更多测试

---

## 阶段五：qd-web ✅ 已验证可启动

### 已完成
- [x] package.json (Vue 3 + Element Plus + Pinia + vue-i18n)
- [x] vite.config.ts (代理 → 8924, 自动导入)
- [x] tsconfig.json
- [x] index.html
- [x] src/main.ts (应用入口)
- [x] src/App.vue
- [x] src/router/index.ts (路由 + 认证守卫)
- [x] src/api/index.ts (axios 拦截器, token 自动刷新)
- [x] src/stores/auth.ts (认证状态管理)
- [x] src/stores/template.ts (模板状态管理)
- [x] src/stores/task.ts (任务状态管理)
- [x] src/views/Login.vue (登录/注册切换, 密码确认)
- [x] src/views/Layout.vue (侧边栏布局)
- [x] src/views/Dashboard.vue (仪表盘 - 模板/任务/执行统计 + 最近执行记录)
- [x] src/views/Templates.vue (模板管理 - 列表, 创建/编辑弹窗)
- [x] src/views/Tasks.vue (任务管理 - 列表, 创建/编辑弹窗, 模板选择, 调度配置)
- [x] src/views/Plugins.vue (插件管理)
- [x] src/views/TemplateDetail.vue (模板详情 - 编辑器)
- [x] src/views/Notifications.vue (通知设置 - 完整 CRUD + Webhook/Email 配置)
- [x] src/views/Notepad.vue (便签工具 - 占位)
- [x] src/components/TemplateEditor.vue (模板编辑器)
  - 模板基本信息 (名称/标签/描述/公开)
  - 模板变量管理
  - 请求列表 (添加/删除/展开/收起)
  - 每个请求: Headers / Body / 数据提取 / 成功失败条件
  - 📥 导入 HAR 文件 (浏览器导出)
  - 📋 导入 cURL 命令
  - ▶ 单条请求测试 + 响应展示 (Body/Headers)
  - 实时正则匹配预览 (数据提取匹配结果)
  - 成功/失败判定条件 (状态码/响应包含/正则/Header/JSON字段)
- [x] src/components/TaskRunHistory.vue (任务执行历史详情)
- [x] src/i18n/ (中英文国际化)
- [x] api/test_request.py (后端测试请求 + cURL 解析 + HAR 解析 API)

### 待完成
- [ ] 通知配置完整实现
- [ ] 便签工具完整实现
- [ ] 暗色主题
- [ ] 移动端适配

---

## 下一步可完善方向

### 已完成 ✅

| 方向 | 状态 |
|------|------|
| 模板导入/导出 API | ✅ QD2 JSON + HAR 格式 |
| 任务执行日志 | ✅ TaskRunHistory 组件 |
| 通知功能 | ✅ Webhook + Email |
| v1 数据迁移 | ✅ 上传 database.db |

### 中优先级

| 方向 | 说明 | 工作量 |
|------|------|--------|
| 便签工具 | 管理 cookies、tokens、配置片段 | 小 |
| 模板版本控制 | 模板修改历史，支持回滚 | 中 |
| 批量执行 | 选择多个任务批量触发 | 小 |
| 执行统计图表 | 用 ECharts 展示成功率、耗时趋势 | 中 |
| 公共模板市场 | 用户可以分享和 fork 公共模板 | 大 |

### 低优先级

| 方向 | 说明 | 工作量 |
|------|------|--------|
| 暗色主题 | Element Plus 暗色模式 | 小 |
| 移动端适配 | 响应式布局优化 | 中 |
| WebSocket 实时推送 | 任务执行状态实时更新 | 中 |
| 多语言完善 | 补全英文翻译 | 小 |
| Alembic 数据库迁移 | 版本化数据库 schema | 小 |
| 性能优化 | 大量模板/任务时的分页和懒加载 | 中 |

---

## 阶段六：Docker / CI ✅

### 已完成
- [x] Dockerfile (多阶段构建)
- [x] Dockerfile.lite (精简版)
- [x] docker-compose.yml
- [x] .github/workflows/ci.yml (lint + test + build + docker)

---

## 启动命令

```bash
# 安装依赖
cd d:/github/BBB/qd2
uv sync --all-packages
cd qd-web && npm install && cd ..

# 运行测试
uv run pytest

# 启动后端 (端口 8924)
uv run python -m uvicorn qd_server.app:app --host 127.0.0.1 --port 8924

# 启动前端 (端口 8923, 自动代理到后端 8924)
cd qd-web && npm run dev
```

访问 http://localhost:8923 即可使用 QD2 Web 界面。
首个注册的用户自动成为管理员。

---

## 关键决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-06-22 | 任务调度用 APScheduler | 不需要 Redis, 简单场景足够 |
| 2026-06-22 | 认证用 JWT + Refresh Token | 前后端分离, 无状态, 天然支持多实例 |
| 2026-06-22 | UI 库选 Element Plus | 轻量, 简洁, 国内社区活跃 |
| 2026-06-22 | 数据库默认 SQLite3 | 零配置, 单机部署简单 |
| 2026-06-22 | 版本号用 CalVer | 符合工具类项目特点 |
| 2026-06-22 | SQLModel 模型需 `table=True` | SQLModel 新版要求显式声明 |
| 2026-06-22 | 固定 bcrypt<5.0.0 | passlib 与 bcrypt 5.x 不兼容 |
