# QD2 与原版 QD 兼容性说明

对照上游 [qd-today/qd](https://github.com/qd-today/qd) 的功能迁移状态。

## ✅ 完全兼容

| 功能 | 说明 |
|---|---|
| 模板格式 | QD v1 tpl（顶层 list, entry 含 request/rule）与标准 HAR dict 均自动识别；仓库内解析、渲染和规则测试通过 |
| Jinja2 filter/globals | 52 个：`md5/sha1/sha256/aes_encrypt/aes_decrypt/rsa_encrypt/rsa_decrypt/b64*/regex_*/timestamp/date_time/Faker/ternary/random/...` |
| 断言与变量提取 | `success_asserts` / `failed_asserts` / `extract_variables`，支持 `/pattern/gims` 正则语法 |
| Cookie 会话 | 原版 dump_cookie JSON 格式双向兼容，任务级持久化 |
| 公共模板库 | 订阅 `tpls_history.json` manifest，浏览/搜索/一键安装 |
| 通知渠道 | Bark、Server酱Turbo、Telegram、钉钉、企业微信、PushDeer、Gotify、Webhook、SMTP 邮件（9 种，含测试发送） |
| 定时与执行控制 | `newontime` 秒级时间及正/负随机窗口、retry_count、retry_interval、random_delay、proxy |
| 多用户 | 首个注册用户为管理员；注册开关、任务配额、禁用/删除/重置密码、资源隔离 |
| Util 工具 API | `/util/delay(N)`、`/util/timestamp`、`/util/unicode`、`/util/gb2312`、`/util/urldecode`、`/util/regex`、`/util/string/replace`、`/util/rsa`（GET+POST，无需认证，路径与原版一致） |
| v1 数据迁移 | `/api/migrate/preview|import`：上传 v1 database.db + AES_KEY，解密导入模板/任务/用户（详见下文） |
| 任务日志管理 | `GET /api/tasks/{id}/runs/stats` 统计；`DELETE /api/tasks/{id}/runs?status=success|failed` 分类清理 |

## ⚠️ 行为差异（已实现但语义不完全一致）

1. **迁移的用户密码**：v1 密码为 PBKDF2+AES 链式加密且依赖每用户 userkey，无法转换为 bcrypt。
   导入的用户为 **禁用状态 + 随机密码**，管理员需在「用户管理」中重置密码并启用。
2. **retry_count 上限**：v1 默认 8、无上限；QD2 限制为最大 10（迁移时 clamp）。
3. **/util/delay 上限**：v1 由 delay_max_timeout 配置（默认 30s）；QD2 固定 30s。
4. **真实公共模板样本**：历史开发阶段曾对公共模板库做批量解析；当前仓库不捆绑该外部样本集，离线回归时对应 2 项测试会跳过，不能替代联网后的最新模板库复验。

## ❌ 未迁移（按需求可再补）

| 功能 | 原版位置 | 不迁移原因 / 替代方案 |
|---|---|---|
| ddddocr 验证码识别 (`/util/dddd/ocr\|det\|slide`) | web/handlers/util.py | 依赖 ~100MB onnx 模型，用到的模板极少。需要时可独立部署 ddddocr HTTP 服务并在模板中调用 |
| 模板推送/审核流 (`/tpl/push`, `/pushs`) | web/handlers/push.py | 多用户社区场景才需要；QD2 用 is_public 开关代替 |
| 批量任务操作 (`/task/N/multi`) | web/handlers/task_multi.py | UI 单个操作可覆盖；后端 API 支持脚本批量调用 |
| evil 反暴破封禁 | config.py + Redis | 依赖 Redis；建议部署时用反向代理 (nginx/caddy) 限流 |
| 邮箱验证 / 忘记密码邮件 | web/handlers/login.py | 自部署场景管理员可直接重置密码 |
| DB 备份/还原页面 (`/user/N/database`) | web/handlers/user.py | 直接备份 `~/.qd2/database.db` 文件即可 |
| 模板 lock 锁定 | db/tpl.py | 单管理员场景意义不大 |
| 订阅加速镜像 (gh-proxy CDN) | config.py | 订阅源 URL 本身可填任意镜像地址，等效 |
| Redis 缓存层 | db/redisdb.py | SQLite/MySQL 直查性能足够 |
| WxPusher / 自定义 pusher 渠道 | libs/funcs.py | 已有 9 渠道覆盖主流；webhook 渠道可对接任意服务 |
| ja3/tls 指纹伪装 (Dockerfile.ja3) | 独立镜像 | httpx 无 curl_cffi 集成；有需求时可换 curl_cffi backend |

## 部署差异

- 原版：Tornado 多进程 + 可选 Redis/MySQL。
- QD2：单进程 uvicorn（FastAPI + APScheduler + SQLite/MySQL），前端静态文件由后端直接托管，
  `uv run python -m uvicorn qd_server.app:app --host 0.0.0.0 --port 8924` 一条命令启动。
