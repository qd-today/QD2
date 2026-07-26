# QD2 使用指南

## 快速开始

```bash
cd d:/github/BBB/qd2

# 启动后端 (端口 8924)
uv run python -m uvicorn qd_server.app:app --host 127.0.0.1 --port 8924

# 启动前端 (端口 8923)
cd qd-web && npm run dev
```

浏览器访问 **http://localhost:8923**

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

## v1 数据迁移

1. 从旧版 QD 备份 `database.db` 文件
2. 点击「通知设置」页面上方的「数据迁移」（仅管理员可见）
3. 上传 `database.db` 文件
4. 预览将导入的数据量
5. 确认导入

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `QD_DEBUG` | 调试模式 | `false` |
| `QD_LOG_LEVEL` | 日志级别 | `INFO` |
| `QD_DB__DB_TYPE` | 数据库类型 | `sqlite3` |
| `QD_JWT_SECRET` | JWT 密钥 | `change-me-in-production` |
| `QD_PORT` | 后端端口 | `8924` |

---

## API 文档

启动后端后访问：
- Swagger UI: http://localhost:8924/docs
- ReDoc: http://localhost:8924/redoc
