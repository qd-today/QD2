# QD2 使用指南

## 快速开始

```bash
cd d:/github/BBB/qd2

# 启动后端 (端口 8923)
uv run python -m uvicorn qd_server.app:app --host 127.0.0.1 --port 8923

# 启动前端 (端口 8924)
cd qd-web && npm run dev
```

浏览器访问 **http://localhost:8924**

---

## Docker 部署

Docker 配置统一放在 `docker/` 目录。先修改 [`docker/.env`](docker/.env)，再启动服务：

```bash
cd docker
docker compose up -d --build
```

默认使用 GHCR 最新镜像 `ghcr.io/qd-today/qd2:latest`。若要使用其他已发布版本，修改 `.env` 中 `DOCKER_IMAGE` 的标签，然后执行：

```bash
docker compose pull
docker compose up -d
```

后端和打包后的前端统一通过 `http://localhost:8923` 访问，数据库保存在 Docker 命名卷 `qd2-data` 中。

---

## 注册与登录

1. 打开页面，点击「没有账号？去注册」
2. 输入用户名和密码，点击注册
3. **首个注册的用户自动成为管理员**
4. 注册后自动跳转到登录页，输入账号密码登录

---

## 模板管理

### 创建模板

1. 点击左侧「模板管理」
2. 点击「新建模板」
3. 填写模板名称、描述、标签
4. 添加 HTTP 请求（手动添加 / 导入 HAR / 导入 cURL）
5. 保存

### 导入 HAR 文件

1. 用 Chrome 打开开发者工具 → Network 标签
2. 操作目标网站
3. 右键 → Save all as HAR with content
4. 在 QD2 模板编辑器中点击「📥 导入 HAR 文件」
5. 选择导出的 .har 文件，所有请求自动解析导入

### 导入 cURL

1. 在 Chrome 开发者工具中，右键任意请求 → Copy → Copy as cURL
2. 在 QD2 模板编辑器中点击「📋 导入 cURL」
3. 粘贴 cURL 命令，点击解析并导入

### 模板变量

在「模板变量」区域添加变量，请求中用 `{{变量名}}` 引用：

```
变量名: token
默认值: abc123

请求 URL: https://api.example.com?token={{token}}
```

### 原版 QD 参数与语法

| 参数 / 语法 | 说明 |
|---|---|
| `{{_proxy}}` | 当前任务或单请求测试使用的代理地址，支持 HTTP、HTTPS、SOCKS5 |
| `{{_cookies['name']}}` | 读取当前请求会话中的 Cookie；任务和编辑器测试会话均会保留响应 `Set-Cookie` |
| `__log__` | 将规则提取变量命名为 `__log__`，其值会写入任务运行日志并推送到实时日志面板 |
| `{% while ... %}...{% endwhile %}` | 原版 while 语法；支持 `loop_index`、`loop_index0`、`loop_depth` 等循环变量 |
| `list/ltrim/rtrim` | 原版 `list()` 全局函数和左右空白过滤器 |

单请求测试会在同一次编辑会话中复用 Cookie 和已提取变量；点击“重置测试会话”可清空这些状态。

---

## 数据提取

在请求的「数据提取」标签页添加提取规则，用于从响应中提取值存入变量。

### 支持的表达式

| 表达式 | 说明 | 示例 |
|--------|------|------|
| `正则表达式` | **默认正则匹配**，提取第一个捕获组 | `请先(.+?)后再操作` → 提取 `登录` |
| `response.json()["key"]` | JSON 路径提取 | `response.json()["data"]["token"]` |
| `response.json()["arr"][0]` | JSON 数组提取 | `response.json()["list"][0]["name"]` |
| `header:Header-Name` | 响应 Header 值 | `header:Content-Type` |
| `status` | 状态码 | `status` → `200` |
| `regex:pattern` | 显式正则（同默认） | `regex:(\d{6})` → 提取6位数字 |

### 示例

响应体：
```json
{
  "code": 0,
  "data": {
    "token": "eyJhbGciOi...",
    "user_id": 12345
  },
  "message": "请先登录后再操作"
}
```

提取规则：
```
变量名: token        表达式: response.json()["data"]["token"]
变量名: user_id      表达式: response.json()["data"]["user_id"]
变量名: error_msg    表达式: 请先(.+?)后再操作
变量名: content_type 表达式: header:content-type
```

提取后变量可在下一个请求中通过 `{{token}}` 引用。

---

## 单条请求测试

1. 展开任意请求
2. 点击「▶ 测试」按钮
3. 右侧显示响应面板：
   - 状态码 (200/404/500 等)
   - 耗时 (ms)
   - Body 内容 (自动 JSON 格式化)
   - Headers 列表

---

## 成功/失败条件

在请求的「成功/失败条件」标签页配置判定规则。

### 条件类型

| 类型 | 说明 | 示例值 |
|------|------|--------|
| 状态码 | HTTP 响应状态码 | `200` |
| 响应包含 | 响应体包含指定文本 | `success` |
| 响应正则匹配 | 响应体匹配正则 | `"code":0` |
| 响应 Header 包含 | Header 包含指定文本 | `application/json` |
| JSON 字段等于 | JSON 特定字段值 | `data.token` |

### 运算符

| 运算符 | 说明 |
|--------|------|
| 等于 | 值完全相等 |
| 不等于 | 值不相等 |
| 大于 | 数值大于 |
| 小于 | 数值小于 |
| 包含 | 字符串包含 |
| 匹配 | 正则匹配 |

### 判定结果

- **成功** - 条件满足时标记为成功
- **失败** - 条件满足时标记为失败

### 示例

```
条件1: 状态码 等于 200  → 判定: 成功    (200 时 ✅)
条件2: 响应包含 "error" → 判定: 失败    (包含 error 时 ❌)
条件3: JSON字段 code 等于 0 → 判定: 成功  (code=0 时 ✅)
```

测试后每行显示 ✅ 或 ❌。

---

## 任务管理

### 创建任务

1. 点击左侧「任务管理」
2. 点击「新建任务」
3. 选择关联模板
4. 配置调度：
   - 固定间隔：每 N 秒执行一次
   - Cron 表达式：标准 cron 格式
   - 每天执行：指定时间
   - 仅手动：不自动执行

### 手动执行

点击任务列表中的「立即执行」按钮，任务会即时触发。

### 查看历史

仪表盘展示最近执行记录，任务列表点击可查看完整历史。

---

## 插件管理

管理员可在「插件管理」页面查看已安装插件。

```bash
# 通过 CLI 安装插件
qd plugin install <plugin-name>
```

---

## 通知设置

### Webhook 通知

1. 点击左侧「通知设置」
2. 点击「新建通知」
3. 选择类型为 Webhook
4. 填写 Webhook URL (如 Slack、企业微信、钉钉机器人)
5. 选择触发条件：成功时 / 失败时
6. 保存

任务执行完成后会自动发送 POST 请求到 Webhook URL：

```json
{
  "event": "task_completed",
  "task_name": "我的任务",
  "status": "success",
  "duration_seconds": 2.5
}
```

### 邮件通知

1. 选择类型为邮件
2. 填写 SMTP 配置（服务器、端口、用户名、密码）
3. 填写发件人和收件人
4. 保存

---

## 模板导入/导出

### 导出

1. 在模板列表点击「导出 ▾」
2. 选择格式：
   - **QD2 格式** - QD2 原生 JSON 格式
   - **HAR 格式** - 标准 HTTP Archive 格式，可导入其他工具

### 导入

在模板编辑器中：
- 📥 导入 HAR 文件 - 上传浏览器导出的 .har 文件
- 📋 导入 cURL - 粘贴 cURL 命令

---

## 数据备份与迁移

登录后点击左侧「数据管理」。

### 个人数据

- 所有用户均可下载自己的 QD2 JSON 备份。
- 备份包含模板、任务、分组、运行记录、Cookie 会话、通知配置、记事本和模板源。
- 备份不包含密码、角色、系统设置或其他用户的数据。
- 上传备份后可先预览，再选择「合并」或「替换」当前账号的数据。

### QD v1 迁移

仅管理员可见。上传旧版 QD 的 `database.db` 并填写原 `AES_KEY`（默认 `binux`），预览确认后迁移。
迁移包含用户模板、任务引用的公共模板副本、任务、通知渠道和记事本；标准 HAR 会转换为 QD2 可编辑的请求结构。
v1 用户会以禁用状态导入，管理员需要在「用户管理」中启用账号并重置密码。

### 系统备份

仅管理员可见。SQLite 部署可下载运行时一致的完整 `database.db` 快照，也可上传快照并安排恢复。
完整恢复会在下次启动后端时执行，恢复前的数据库会自动保留为 `database.before-restore-时间.db`。

---

## 环境变量

Docker 部署直接编辑 [`docker/.env`](docker/.env)；该文件包含全部推荐变量及逐项中文注释。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `QD_DEBUG` | 调试模式 | `false` |
| `QD_LOG_LEVEL` | 日志级别 | `INFO` |
| `QD_DB__DB_TYPE` | 数据库类型 | `sqlite3` |
| `QD_JWT_SECRET` | JWT 密钥；未配置时自动生成到 `~/.qd2/jwt-secret` | 自动生成 |
| `QD_PORT` | 后端端口 | `8923` |
| `QD_MAX_CONCURRENT_TASKS` | 单个服务进程允许同时执行的最大任务数 | `5` |
| `QD_TASK_REQUEST_LIMIT` | 单次任务运行允许发出的最大 HTTP 请求数，包含重试 | `1500` |
| `QD_TASK_TIMEOUT` | 单次任务执行最长时间（秒），不包含任务开始前的随机延迟 | `900` |
| `QD_WHILE_LOOP_LIMIT` | 单个模板 `while` 循环最大迭代次数 | `10000` |
| `QD_WHILE_LOOP_TIMEOUT` | 单个模板 `while` 循环最长运行时间（秒） | `900` |
| `QD_LOGIN_RATE_LIMIT` | 同一客户端 IP 与用户名在窗口内允许的失败登录次数；`0` 表示关闭 | `10` |
| `QD_LOGIN_RATE_LIMIT_WINDOW_SECONDS` | 失败登录计数窗口（秒） | `3600` |
| `QD_PUBLIC_URL` | 对外访问根地址，供生成邮件或通知链接使用，例如 `https://qd.example.com` | 空 |
| `QD_ENCRYPTION_KEY` | 任务变量、任务 Cookie、通知渠道配置的固定数据库加密密钥；部署后不要随意修改 | `binux` |
| `QD_SMTP_SSL` | 邮件渠道未单独指定时是否使用 SMTP SSL/TLS | `false` |
| `QD_SMTP_STARTTLS` | 邮件渠道未单独指定时是否使用 STARTTLS | `true` |
| `QD_WS_PING_INTERVAL` | 实时日志 WebSocket 心跳间隔（秒） | `5` |
| `QD_WS_PING_TIMEOUT` | 实时日志 WebSocket 心跳响应超时（秒） | `30` |
| `QD_WS_MAX_QUEUE_SIZE` | 每个实时日志连接的待发送消息队列上限 | `100` |
| `QD_WS_MAX_CONNECTIONS` | 单个后端进程允许的实时日志 WebSocket 连接总数 | `30` |

敏感字段在后端启动时自动从旧明文转换为 AES-256-GCM 密文。默认固定密钥为 `binux`，需要自定义时只需在首次启动前设置 `QD_ENCRYPTION_KEY`，之后保持不变。完整 `database.db` 迁移到其他实例时必须使用相同的 `QD_ENCRYPTION_KEY`。用户自己的 JSON 备份仍以可移植的明文格式导出，应按敏感文件保管。

邮件渠道的 `use_ssl` 和 `use_starttls` 不能同时开启。旧通知配置中的 `use_tls` 会继续按 STARTTLS 处理。

---

## API 文档

启动后端后访问：
- Swagger UI: http://localhost:8923/docs
- ReDoc: http://localhost:8923/redoc
