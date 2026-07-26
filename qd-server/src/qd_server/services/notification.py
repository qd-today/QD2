"""Notification service for QD2.

Sends notifications via webhook or email when task execution completes.
"""

import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger("qd2.notification")


async def send_notification(
    notification_config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> bool:
    """Send a notification based on config.

    Args:
        notification_config: Notification configuration dict.
        task_name: Name of the task.
        status: Task execution status (success/failed).
        error_message: Error message if failed.
        duration_seconds: Execution duration.

    Returns:
        True if notification sent successfully.
    """
    notification_type = notification_config.get("type", "webhook")

    if notification_type == "webhook":
        return await send_webhook(
            notification_config,
            task_name=task_name,
            status=status,
            error_message=error_message,
            duration_seconds=duration_seconds,
        )
    elif notification_type == "email":
        return await send_email(
            notification_config,
            task_name=task_name,
            status=status,
            error_message=error_message,
            duration_seconds=duration_seconds,
        )

    logger.warning("Unknown notification type: %s", notification_type)
    return False


async def send_webhook(
    config: dict,
    task_name: str,
    status: str,
    error_message: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> bool:
    """Send a webhook notification.

    Config fields:
        url: Webhook URL (required)
        method: HTTP method (default: POST)
        headers: Additional headers (default: {})
    """
    url = config.get("url")
    if not url:
        logger.error("Webhook URL not configured")
        return False

    method = config.get("method", "POST").upper()
    headers = config.get("headers", {})
    headers.setdefault("Content-Type", "application/json")

    payload = {
        "event": "task_completed",
        "task_name": task_name,
        "status": status,
        "error_message": error_message,
        "duration_seconds": duration_seconds,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=payload if method == "POST" else None,
            )
            logger.info(
                "Webhook sent to %s: %d", url, response.status_code
            )
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
) -> bool:
    """Send an email notification.

    Config fields:
        smtp_host: SMTP server host (required)
        smtp_port: SMTP server port (default: 587)
        smtp_user: SMTP username
        smtp_password: SMTP password
        from_addr: Sender email address
        to_addr: Recipient email address
        use_tls: Whether to use STARTTLS (default: True)
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = config.get("smtp_host")
    to_addr = config.get("to_addr")

    if not smtp_host or not to_addr:
        logger.error("Email SMTP host or recipient not configured")
        return False

    smtp_port = config.get("smtp_port", 587)
    smtp_user = config.get("smtp_user", "")
    smtp_password = config.get("smtp_password", "")
    from_addr = config.get("from_addr", smtp_user)
    use_tls = config.get("use_tls", True)

    subject = f"[QD2] 任务 {task_name} {'成功' if status == 'success' else '失败'}"
    body = f"任务: {task_name}\n状态: {status}\n"
    if error_message:
        body += f"错误: {error_message}\n"
    if duration_seconds:
        body += f"耗时: {duration_seconds:.1f}s\n"

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if use_tls:
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        logger.info("Email sent to %s", to_addr)
        return True
    except Exception as e:
        logger.error("Email failed: %s", e)
        return False
