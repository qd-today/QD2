"""Utility API endpoints — QD v1 compatible /util/* routes.

Ported from QD v1 web/handlers/util.py. These endpoints are PUBLIC (no auth),
matching the original behaviour, because public templates call them directly
(e.g. GET /util/delay/3 between two requests).

Not ported (see COMPATIBILITY.md): /util/dddd/* (ddddocr captcha), /util/toolbox.
"""

import asyncio
import datetime
import html
import json
import math
import re
import time
import urllib.parse
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

from qd_core.filters.crypto import rsa_decrypt, rsa_encrypt

router = APIRouter()

DELAY_MAX_TIMEOUT = 30  # seconds, same spirit as original delay_max_timeout
GMT_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"
MAX_TEXT_LENGTH = 1024 * 1024
MAX_PATTERN_LENGTH = 4096
MAX_RSA_KEY_LENGTH = 32 * 1024


def _bounded(value: str, limit: int, field: str) -> str:
    if len(value) > limit:
        raise HTTPException(status_code=413, detail=f"{field} is too large")
    return value


def _json_response(data: dict) -> Response:
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=4),
        media_type="application/json; charset=UTF-8",
    )


# --- delay ---

async def _do_delay(seconds_raw) -> PlainTextResponse:
    try:
        seconds = float(seconds_raw)
    except (TypeError, ValueError):
        return PlainTextResponse("Error, delay 0.0 second.")
    if not math.isfinite(seconds):
        return PlainTextResponse("Error, delay 0.0 second.")
    if seconds < 0:
        seconds = 0.0
    if seconds >= DELAY_MAX_TIMEOUT:
        seconds = DELAY_MAX_TIMEOUT
        await asyncio.sleep(seconds)
        return PlainTextResponse(
            f"Error, limited by delay_max_timeout, delay {seconds} second."
        )
    await asyncio.sleep(seconds)
    return PlainTextResponse(f"delay {seconds} second.")


@router.get("/delay")
async def util_delay_query(seconds: str = Query("0")):
    """GET /util/delay?seconds=N"""
    return await _do_delay(seconds)


@router.get("/delay/{seconds}")
async def util_delay_path(seconds: str):
    """GET /util/delay/N or /util/delay/N.N"""
    return await _do_delay(seconds)


# --- timestamp ---

def _yearday(year: int) -> str:
    return "366" if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0) else "365"


def _timestamp_info(ts: str = "", dt: str = "", time_format: str = "%Y-%m-%d %H:%M:%S") -> dict:
    rtv: dict = {}
    try:
        if not time_format:
            time_format = "%Y-%m-%d %H:%M:%S"
        cst_tz = ZoneInfo("Asia/Shanghai")
        utc_tz = ZoneInfo("UTC")
        from_ts = datetime.datetime.fromtimestamp

        ts_value: Optional[float] = None
        if dt:
            ts_value = datetime.datetime.strptime(dt, time_format).timestamp()
        elif ts:
            ts_value = float(ts)

        if ts_value is not None:
            rtv["完整时间戳"] = ts_value
        else:
            rtv["完整时间戳"] = time.time()
            rtv["本机时间"] = from_ts(rtv["完整时间戳"]).strftime(time_format)

        full = rtv["完整时间戳"]
        rtv["时间戳"] = int(full)
        rtv["16位时间戳"] = int(full * 1000000)
        rtv["周"] = from_ts(full).strftime("%w/%W")
        rtv["日"] = "/".join([from_ts(full).strftime("%j"), _yearday(from_ts(full).year)])
        rtv["北京时间"] = from_ts(full, cst_tz).strftime(time_format)
        rtv["GMT格式"] = from_ts(full, utc_tz).strftime(GMT_FORMAT)
        rtv["ISO格式"] = from_ts(full, utc_tz).isoformat().split("+")[0] + "Z"
        rtv["状态"] = "200"
    except Exception as e:
        rtv["状态"] = str(e)
    return rtv


@router.get("/timestamp")
async def util_timestamp_get(ts: str = Query(""), dt: str = Query(""), form: str = Query("%Y-%m-%d %H:%M:%S")):
    """GET /util/timestamp?ts=...&dt=...&form=..."""
    return _json_response(_timestamp_info(ts, dt, form))


@router.post("/timestamp")
async def util_timestamp_post(
    ts: str = Form(""), dt: str = Form(""), form: str = Form("%Y-%m-%d %H:%M:%S")
):
    return _json_response(_timestamp_info(ts, dt, form))


# --- unicode ---

def _unicode_convert(content: str, html_unescape: bool) -> dict:
    _bounded(content, MAX_TEXT_LENGTH, "content")
    rtv: dict = {}
    try:
        tmp = (
            bytes(content, "unicode_escape")
            .decode("utf-8")
            .replace(r"\u", r"\\u")
            .replace(r"\\\u", r"\\u")
        )
        tmp = bytes(tmp, "utf-8").decode("unicode_escape")
        tmp = tmp.encode("utf-8").replace(b"\xc2\xa0", b"\xa0").decode("unicode_escape")
        if html_unescape:
            tmp = html.unescape(tmp)
        rtv["转换后"] = tmp
        rtv["状态"] = "200"
    except Exception as e:
        rtv["状态"] = str(e)
    return rtv


@router.get("/unicode")
async def util_unicode_get(content: str = Query(""), html_unescape: str = Query("false")):
    return _json_response(_unicode_convert(content, html_unescape.lower() in ("true", "1", "yes")))


@router.post("/unicode")
async def util_unicode_post(content: str = Form(""), html_unescape: str = Form("false")):
    return _json_response(_unicode_convert(content, html_unescape.lower() in ("true", "1", "yes")))


# --- gb2312 ---

def _gb2312_convert(content: str) -> dict:
    _bounded(content, MAX_TEXT_LENGTH, "content")
    rtv: dict = {}
    try:
        rtv["转换后"] = urllib.parse.quote(content, encoding="gb2312")
        rtv["状态"] = "200"
    except Exception as e:
        rtv["状态"] = str(e)
    return rtv


@router.get("/gb2312")
async def util_gb2312_get(content: str = Query("")):
    return _json_response(_gb2312_convert(content))


@router.post("/gb2312")
async def util_gb2312_post(content: str = Form("")):
    return _json_response(_gb2312_convert(content))


# --- urldecode ---

def _urldecode_convert(content: str, encoding: str, unquote_plus: bool) -> dict:
    _bounded(content, MAX_TEXT_LENGTH, "content")
    _bounded(encoding, 100, "encoding")
    rtv: dict = {}
    try:
        if unquote_plus:
            rtv["转换后"] = urllib.parse.unquote_plus(content, encoding=encoding)
        else:
            rtv["转换后"] = urllib.parse.unquote(content, encoding=encoding)
        rtv["状态"] = "200"
    except Exception as e:
        rtv["状态"] = str(e)
    return rtv


@router.get("/urldecode")
async def util_urldecode_get(
    content: str = Query(""), encoding: str = Query("utf-8"), unquote_plus: str = Query("false")
):
    return _json_response(
        _urldecode_convert(content, encoding, unquote_plus.lower() in ("true", "1", "yes"))
    )


@router.post("/urldecode")
async def util_urldecode_post(
    content: str = Form(""), encoding: str = Form("utf-8"), unquote_plus: str = Form("false")
):
    return _json_response(
        _urldecode_convert(content, encoding, unquote_plus.lower() in ("true", "1", "yes"))
    )


# --- regex ---

def _regex_findall(data: str, p: str) -> dict:
    _bounded(data, MAX_TEXT_LENGTH, "data")
    _bounded(p, MAX_PATTERN_LENGTH, "pattern")
    rtv: dict = {}
    try:
        temp = {}
        for cnt, d in enumerate(re.findall(p, data, re.IGNORECASE)):
            temp[cnt + 1] = d
        rtv["数据"] = temp
        rtv["状态"] = "OK"
    except Exception as e:
        rtv["状态"] = str(e)
    return rtv


@router.get("/regex")
async def util_regex_get(data: str = Query(""), p: str = Query("")):
    return _json_response(_regex_findall(data, p))


@router.post("/regex")
async def util_regex_post(data: str = Form(""), p: str = Form("")):
    return _json_response(_regex_findall(data, p))


# --- string replace ---

def _str_replace(s: str, p: str, t: str, r: str) -> Response:
    _bounded(s, MAX_TEXT_LENGTH, "string")
    _bounded(p, MAX_PATTERN_LENGTH, "pattern")
    _bounded(t, MAX_TEXT_LENGTH, "replacement")
    rtv: dict = {}
    try:
        rtv["原始字符串"] = s
        rtv["处理后字符串"] = re.sub(p, t, s)
        rtv["状态"] = "OK"
        if r == "text":
            return PlainTextResponse(html.escape(rtv["处理后字符串"]))
    except Exception as e:
        rtv["状态"] = str(e)
    return _json_response(rtv)


@router.get("/string/replace")
async def util_str_replace_get(
    s: str = Query(""), p: str = Query(""), t: str = Query(""), r: str = Query("")
):
    return _str_replace(s, p, t, r)


@router.post("/string/replace")
async def util_str_replace_post(
    s: str = Form(""), p: str = Form(""), t: str = Form(""), r: str = Form("")
):
    return _str_replace(s, p, t, r)


# --- rsa ---

def _rsa_action(key: str, data: str, func: str) -> PlainTextResponse:
    _bounded(key, MAX_RSA_KEY_LENGTH, "key")
    _bounded(data, MAX_TEXT_LENGTH, "data")
    try:
        if not (key and data and func):
            return PlainTextResponse("参数不完整，请确认")
        if "encode" in func:
            return PlainTextResponse(rsa_encrypt(data, key))
        if "decode" in func:
            return PlainTextResponse(rsa_decrypt(data, key))
        return PlainTextResponse("功能选择错误")
    except Exception as e:
        return PlainTextResponse(str(e))


@router.get("/rsa")
async def util_rsa_get(key: str = Query(""), data: str = Query(""), f: str = Query("encode")):
    return _rsa_action(key, data, f)


@router.post("/rsa")
async def util_rsa_post(key: str = Form(""), data: str = Form(""), f: str = Form("encode")):
    # QD v1 POST quirk: '+' was decoded to space in form data, restore it
    lines = ""
    for line in key.split("\n"):
        if "--" not in line:
            line = line.replace(" ", "+")
        lines = lines + line + "\n"
    data = data.replace(" ", "+")
    return _rsa_action(lines, data, f)
