"""Notification service for QD2.

Supports all channels from original QD plus webhook/email:
- webhook (generic)
- email (SMTP)
- bark (iOS push)
- serverchan (Server酱 Turbo)
- wxpusher
- telegram (Bot API)
- pushdeer
- gotify
- dingtalk (钉钉群机器人)
- wecom (企业微信群机器人)
- wecom_app (企业微信应用 Pusher)
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger("qd2.notification")

_TIMEOUT = 15


def _build_title_body(
    task_name: str,
    status: str,
    error_message: Optional[str],
    duration_seconds: Optional[float],
    task_log: Optional[str] = None,
) -> tuple[str, str]:
    ok = status == "success"
    title = f"[QD2] 任务 {task_name} {'成功 ✅' if ok else '失败 ❌'}"
    body = f"任务: {task_name}\n状态: {'成功' if ok else '失败'}"
    log_message = error_message if not ok and error_message else task_log
    body += f"\n日志: {str(log_message)[:1000] if log_message not in (None, '') else '-'}"
    return title, body


async def send_notification(
    notification_config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    task_log: Optional[str] = None,
) -> bool:
    """Send a notification based on config['type']."""
    notification_type = notification_config.get("type", "webhook")

    handlers = {
        "webhook": send_webhook,
        "email": send_email,
        "bark": send_bark,
        "serverchan": send_serverchan,
        "wxpusher": send_wxpusher,
        "telegram": send_telegram,
        "pushdeer": send_pushdeer,
        "gotify": send_gotify,
        "dingtalk": send_dingtalk,
        "wecom": send_wecom,
        "wecom_app": send_wecom_app,
    }

    handler = handlers.get(notification_type)
    if handler is None:
        logger.warning("Unknown notification type: %s", notification_type)
        return False

    return await handler(
        notification_config,
        task_name=task_name,
        status=status,
        error_message=error_message,
        duration_seconds=duration_seconds,
        task_log=task_log,
    )


async def _post(url: str, **kwargs) -> bool:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.post(url, **kwargs)
            logger.info("Notification POST %s → %d", url.split("?")[0][:80], resp.status_code)
            return resp.status_code < 400
    except Exception as e:
        logger.error("Notification POST failed: %s", e)
        return False


async def _get(url: str, **kwargs) -> bool:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, **kwargs)
            logger.info("Notification GET %s → %d", url.split("?")[0][:80], resp.status_code)
            return resp.status_code < 400
    except Exception as e:
        logger.error("Notification GET failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# webhook / email (existing)
# ---------------------------------------------------------------------------

async def send_webhook(
    config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    task_log: Optional[str] = None,
) -> bool:
    """Generic webhook.

    Config: url (required), method (default POST), headers (dict).
    """
    url = config.get("url")
    if not url:
        logger.error("Webhook URL not configured")
        return False

    method = config.get("method", "POST").upper()
    headers = dict(config.get("headers", {}))
    headers.setdefault("Content-Type", "application/json")

    payload = {
        "event": "task_completed",
        "task_name": task_name,
        "status": status,
        "error_message": error_message,
        "task_log": task_log if task_log not in (None, "") else error_message,
        "duration_seconds": duration_seconds,
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=payload if method == "POST" else None,
            )
            logger.info("Webhook sent to %s: %d", url, response.status_code)
            return response.status_code < 400
    except Exception as e:
        logger.error("Webhook failed: %s", e)
        return False


async def send_email(
    config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    task_log: Optional[str] = None,
) -> bool:
    """SMTP email.

    Config: smtp_host (required), smtp_port (587), smtp_user, smtp_password,
    from_addr, to_addr (required), use_ssl/use_starttls. ``use_tls`` remains
    accepted as the legacy alias for ``use_starttls``.
    """
    import smtplib
    import ssl
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    smtp_host = config.get("smtp_host")
    to_addr = config.get("to_addr")

    if not smtp_host or not to_addr:
        logger.error("Email SMTP host or recipient not configured")
        return False

    smtp_port = config.get("smtp_port", 587)
    smtp_user = config.get("smtp_user", "")
    smtp_password = config.get("smtp_password", "")
    from_addr = config.get("from_addr", smtp_user)
    from qd_server.config import get_settings

    settings = get_settings()
    smtp_settings = settings.smtp
    use_ssl = bool(config.get("use_ssl", smtp_settings.ssl))
    use_starttls = bool(
        config.get(
            "use_starttls",
            config.get("use_tls", smtp_settings.starttls),
        )
    )
    if use_ssl and use_starttls:
        logger.error("Email configuration cannot enable SSL and STARTTLS together")
        return False

    title, body = _build_title_body(
        task_name, status, error_message, duration_seconds, task_log
    )
    if settings.public_url:
        body = f"{body}\n\nQD2: {settings.public_url}"

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = title
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        smtp_client = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_client(smtp_host, smtp_port) as server:
            if use_starttls:
                server.starttls(context=ssl.create_default_context())
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        logger.info("Email sent to %s", to_addr)
        return True
    except Exception as e:
        logger.error("Email failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# push channels (original QD parity)
# ---------------------------------------------------------------------------

async def send_bark(
    config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    task_log: Optional[str] = None,
) -> bool:
    """Bark (iOS).

    Config: server (default https://api.day.app), device_key (required),
    group (optional), sound (optional).
    """
    device_key = config.get("device_key")
    if not device_key:
        logger.error("Bark device_key not configured")
        return False

    server = (config.get("server") or "https://api.day.app").rstrip("/")
    title, body = _build_title_body(
        task_name, status, error_message, duration_seconds, task_log
    )

    payload = {"title": title, "body": body}
    if config.get("group"):
        payload["group"] = config["group"]
    if config.get("sound"):
        payload["sound"] = config["sound"]

    return await _post(f"{server}/{device_key}", json=payload)


async def send_serverchan(
    config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    task_log: Optional[str] = None,
) -> bool:
    """Server酱 Turbo.

    Config: sendkey (required).
    """
    sendkey = config.get("sendkey")
    if not sendkey:
        logger.error("ServerChan sendkey not configured")
        return False

    title, body = _build_title_body(
        task_name, status, error_message, duration_seconds, task_log
    )
    server = "https://sc.ftqq.com" if sendkey.startswith("SCU") else "https://sctapi.ftqq.com"
    return await _post(
        f"{server}/{sendkey}.send",
        data={"title": title, "desp": body.replace("\n", "\n\n")},
    )


async def send_wxpusher(
    config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    task_log: Optional[str] = None,
) -> bool:
    """Wxpusher app notification."""
    app_token = config.get("app_token")
    raw_uids = config.get("uids")
    if not app_token or not raw_uids:
        logger.error("Wxpusher app_token/uids not configured")
        return False
    if isinstance(raw_uids, str):
        uids = [value.strip() for value in raw_uids.replace(";", ",").split(",") if value.strip()]
    else:
        uids = [str(value).strip() for value in raw_uids if str(value).strip()]
    if not uids:
        return False

    title, body = _build_title_body(
        task_name, status, error_message, duration_seconds, task_log
    )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                "https://wxpusher.zjiecode.com/api/send/message",
                json={
                    "appToken": app_token,
                    "summary": title,
                    "content": body,
                    "contentType": 1,
                    "uids": uids,
                },
            )
            response.raise_for_status()
            return response.json().get("code") in (0, 1000)
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Wxpusher request failed: %s", type(exc).__name__)
        return False


async def send_telegram(
    config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    task_log: Optional[str] = None,
) -> bool:
    """Telegram Bot.

    Config: bot_token (required), chat_id (required), api_host (optional,
    default https://api.telegram.org for users behind proxies).
    """
    bot_token = config.get("bot_token")
    chat_id = config.get("chat_id")
    if not bot_token or not chat_id:
        logger.error("Telegram bot_token/chat_id not configured")
        return False

    api_host = (config.get("api_host") or "https://api.telegram.org").rstrip("/")
    title, body = _build_title_body(
        task_name, status, error_message, duration_seconds, task_log
    )

    return await _post(
        f"{api_host}/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": f"{title}\n\n{body}"},
    )


async def send_pushdeer(
    config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    task_log: Optional[str] = None,
) -> bool:
    """PushDeer.

    Config: pushkey (required), server (default https://api2.pushdeer.com).
    """
    pushkey = config.get("pushkey")
    if not pushkey:
        logger.error("PushDeer pushkey not configured")
        return False

    server = (config.get("server") or "https://api2.pushdeer.com").rstrip("/")
    title, body = _build_title_body(
        task_name, status, error_message, duration_seconds, task_log
    )

    return await _post(
        f"{server}/message/push",
        data={"pushkey": pushkey, "text": title, "desp": body, "type": "text"},
    )


async def send_gotify(
    config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    task_log: Optional[str] = None,
) -> bool:
    """Gotify.

    Config: server (required, e.g. https://gotify.example.com),
    token (required), priority (default 5).
    """
    server = config.get("server")
    token = config.get("token")
    if not server or not token:
        logger.error("Gotify server/token not configured")
        return False

    title, body = _build_title_body(
        task_name, status, error_message, duration_seconds, task_log
    )
    return await _post(
        f"{server.rstrip('/')}/message?token={token}",
        json={"title": title, "message": body, "priority": int(config.get("priority", 5))},
    )


async def send_dingtalk(
    config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    task_log: Optional[str] = None,
) -> bool:
    """钉钉群机器人 (custom robot webhook).

    Config: access_token (required) OR full webhook url; secret (optional, 加签).
    """
    import base64
    import hashlib
    import hmac
    import time
    import urllib.parse

    url = config.get("url")
    if not url:
        access_token = config.get("access_token")
        if not access_token:
            logger.error("DingTalk access_token not configured")
            return False
        url = f"https://oapi.dingtalk.com/robot/send?access_token={access_token}"

    secret = config.get("secret")
    if secret:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        url += f"&timestamp={timestamp}&sign={sign}"

    title, body = _build_title_body(
        task_name, status, error_message, duration_seconds, task_log
    )
    return await _post(url, json={"msgtype": "text", "text": {"content": f"{title}\n{body}"}})


async def send_wecom(
    config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    task_log: Optional[str] = None,
) -> bool:
    """企业微信群机器人.

    Config: key (required) OR full webhook url.
    """
    url = config.get("url")
    if not url:
        key = config.get("key")
        if not key:
            logger.error("WeCom key not configured")
            return False
        url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"

    title, body = _build_title_body(
        task_name, status, error_message, duration_seconds, task_log
    )
    return await _post(url, json={"msgtype": "text", "text": {"content": f"{title}\n{body}"}})


async def send_wecom_app(
    config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    task_log: Optional[str] = None,
) -> bool:
    """企业微信自建应用 Pusher.

    Config: corp_id/corpid, corp_secret/corpsecret, agent_id/agentid,
    and touser. ``touser`` accepts the enterprise WeChat ``@all`` value.
    """
    corp_id = config.get("corp_id") or config.get("corpid")
    corp_secret = config.get("corp_secret") or config.get("corpsecret")
    agent_id = config.get("agent_id") or config.get("agentid")
    touser = config.get("touser")
    if not corp_id or not corp_secret or agent_id in (None, "") or not touser:
        logger.error("WeCom app corp_id/corp_secret/agent_id/touser not configured")
        return False

    try:
        agent_id = int(agent_id)
    except (TypeError, ValueError):
        logger.error("WeCom app agent_id must be an integer")
        return False

    title, body = _build_title_body(
        task_name, status, error_message, duration_seconds, task_log
    )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            token_resp = await client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                params={"corpid": corp_id, "corpsecret": corp_secret},
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if token_data.get("errcode", 0) != 0 or not access_token:
                logger.error(
                    "WeCom app token request failed: errcode=%s errmsg=%s",
                    token_data.get("errcode"),
                    token_data.get("errmsg", ""),
                )
                return False

            send_resp = await client.post(
                "https://qyapi.weixin.qq.com/cgi-bin/message/send",
                params={"access_token": access_token},
                json={
                    "touser": str(touser),
                    "msgtype": "text",
                    "agentid": agent_id,
                    "text": {"content": f"{title}\n{body}"},
                },
            )
            send_resp.raise_for_status()
            send_data = send_resp.json()
            if send_data.get("errcode", 0) != 0:
                logger.error(
                    "WeCom app message failed: errcode=%s errmsg=%s",
                    send_data.get("errcode"),
                    send_data.get("errmsg", ""),
                )
                return False
            return True
    except (httpx.HTTPError, ValueError) as exc:
        # HTTP exception strings may include the query string containing
        # corpsecret or access_token, so only log the exception type.
        logger.error("WeCom app request failed: %s", type(exc).__name__)
        return False
