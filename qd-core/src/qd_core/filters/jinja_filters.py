"""Jinja2 template filters compatible with original QD (qd-today/qd).

Ports the full ``jinja_globals`` filter set from QD v1 ``libs/utils.py`` so
that original QD templates render identically under QD2.
"""

import base64
import datetime
import hashlib
import html
import random
import re
import time
import uuid
from binascii import (
    a2b_base64,
    a2b_hex,
    a2b_qp,
    a2b_uu,
    b2a_base64,
    b2a_hex,
    b2a_qp,
    b2a_uu,
    crc32,
    crc_hqx,
)
from hashlib import md5 as _md5
from hashlib import sha1
from typing import Any, Iterable, Mapping, Tuple, Union
from urllib import parse as urllib_parse

from faker import Faker
from jinja2.filters import do_float, do_int
from jinja2.runtime import Undefined
from jinja2.utils import generate_lorem_ipsum, url_quote

from qd_core.filters.convert import to_bytes, to_native, to_text
from qd_core.filters.crypto import (
    aes_decrypt,
    aes_encrypt,
    passlib_or_crypt,
    regex_escape_posix_basic,
    switch_mode,
)
from qd_core.utils.log import Log

logger = Log("QD.Core.Filters").getlogger()


# ---------------------------------------------------------------------------
# type/encoding filters
# ---------------------------------------------------------------------------

def utf8(value):
    if isinstance(value, str):
        return value.encode("utf8")
    return value


def conver2unicode(value, html_unescape=False):
    if not isinstance(value, str):
        try:
            value = value.decode()
        except Exception as e:
            logger.debug(e)
            value = str(value)
    tmp = bytes(value, "unicode_escape").decode("utf-8").replace(r"\u", r"\\u").replace(r"\\\u", r"\\u")
    tmp = bytes(tmp, "utf-8").decode("unicode_escape")
    tmp = tmp.encode("utf-8").replace(b"\xc2\xa0", b"\xa0").decode("unicode_escape")
    if html_unescape:
        tmp = html.unescape(tmp)
    return tmp


def urlencode_with_encoding(
    value: Union[str, Mapping[str, Any], Iterable[Tuple[str, Any]]],
    encoding: str = "utf-8",
    for_qs: bool = False,
) -> str:
    """Quote data for use in a URL path or query."""
    if isinstance(value, str) or not isinstance(value, Iterable):
        return url_quote(value, charset=encoding, for_qs=for_qs)

    if isinstance(value, dict):
        items: Iterable[Tuple[str, Any]] = value.items()
    else:
        items = value  # type: ignore

    return "&".join(f"{url_quote(k, for_qs=True)}={url_quote(v, for_qs=True)}" for k, v in items)


def quote_chinese(value, sep="", encoding="utf-8", decoding="utf-8"):
    if isinstance(value, str):
        return quote_chinese(value.encode(encoding))
    if isinstance(value, bytes):
        value = value.decode(decoding)
    res = [b if ord(b) < 128 else urllib_parse.quote(b) for b in value]
    if sep is not None:
        return sep.join(res)
    return res


def to_bool(value):
    """Return a bool for the arg."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        value = value.lower()
    if value in ("yes", "on", "1", "true", 1):
        return True
    return False


# ---------------------------------------------------------------------------
# hash filters
# ---------------------------------------------------------------------------

def secure_hash_s(value, hash_func=sha1):
    """Return a secure hash hex digest of data."""
    digest = hash_func()
    value = to_bytes(value, errors="surrogate_or_strict")
    digest.update(value)
    return digest.hexdigest()


def md5string(value):
    return secure_hash_s(value, _md5)


def get_hash(value, hashtype="sha1"):
    h = hashlib.new(hashtype)
    h.update(to_bytes(value, errors="surrogate_or_strict"))
    return h.hexdigest()


def get_encrypted_password(password, hashtype="sha512", salt=None, salt_size=None, rounds=None, ident=None):
    passlib_mapping = {
        "md5": "md5_crypt",
        "blowfish": "bcrypt",
        "sha256": "sha256_crypt",
        "sha512": "sha512_crypt",
    }
    hashtype = passlib_mapping.get(hashtype, hashtype)
    return passlib_or_crypt(password, hashtype, salt=salt, salt_size=salt_size, rounds=rounds, ident=ident)


def _aes_encrypt(
    word: str,
    key: str,
    mode="CBC",
    iv: Union[str, bytes, None] = None,
    output_format="base64",
    padding=True,
    padding_style="pkcs7",
    no_packb=True,  # kept for signature compatibility with original QD
):
    if key is None:
        raise ValueError("key is required")
    if isinstance(iv, str):
        iv = iv.encode("utf-8")
    aes_mode = switch_mode(mode)
    return aes_encrypt(
        word.encode("utf-8"),
        key.encode("utf-8"),
        mode=aes_mode,
        iv=iv,
        output=output_format,
        padding=padding,
        padding_style=padding_style,
    )


def _aes_decrypt(
    word: str,
    key: str,
    mode="CBC",
    iv: Union[str, bytes, None] = None,
    input_format="base64",
    padding=True,
    padding_style="pkcs7",
    no_packb=True,  # kept for signature compatibility with original QD
):
    if key is None:
        raise ValueError("key is required")
    if isinstance(iv, str):
        iv = iv.encode("utf-8")
    aes_mode = switch_mode(mode)
    return aes_decrypt(
        word.encode("utf-8"),
        key.encode("utf-8"),
        mode=aes_mode,
        iv=iv,
        input=input_format,
        padding=padding,
        padding_style=padding_style,
    )


# ---------------------------------------------------------------------------
# base64 / uuid
# ---------------------------------------------------------------------------

def b64encode(value, encoding="utf-8"):
    return to_text(base64.b64encode(to_bytes(value, encoding=encoding, errors="surrogate_or_strict")))


def b64decode(value, encoding="utf-8"):
    return to_text(base64.b64decode(to_bytes(value, errors="surrogate_or_strict")), encoding=encoding)


def to_uuid(value, namespace=uuid.NAMESPACE_URL):
    uuid_namespace = namespace
    if not isinstance(uuid_namespace, uuid.UUID):
        try:
            uuid_namespace = uuid.UUID(namespace)
        except (AttributeError, ValueError) as e:
            raise ValueError(f"Invalid value '{to_native(namespace)}' for 'namespace': {to_native(e)}") from e
    return to_text(uuid.uuid5(uuid_namespace, to_native(value, errors="surrogate_or_strict")))


# ---------------------------------------------------------------------------
# time filters
# ---------------------------------------------------------------------------

def timestamp(type="int"):  # noqa: A002 - matches original QD filter signature
    if type == "float":
        return time.time()
    return int(time.time())


def get_date_time(date=True, time_=True, time_difference=0):
    if isinstance(date, str):
        date = int(date)
    if isinstance(time_, str):
        time_ = int(time_)
    if isinstance(time_difference, str):
        time_difference = int(time_difference)
    now_date = datetime.datetime.today() + datetime.timedelta(hours=time_difference)
    if date:
        if time_:
            return str(now_date).split(".", maxsplit=1)[0]
        return str(now_date.date())
    if time_:
        return str(now_date.time()).split(".", maxsplit=1)[0]
    return ""


def strftime(string_format, second=None):
    """Return a date string using string format. See time.strftime docs."""
    if second is not None:
        try:
            second = float(second)
        except Exception as e:
            raise ValueError(f"Invalid value for epoch value ({second})") from e
    return time.strftime(string_format, time.localtime(second))


# ---------------------------------------------------------------------------
# math filters
# ---------------------------------------------------------------------------

def is_num(value: Any = "") -> bool:
    value = str(value)
    if value.count(".") == 1:
        tmp = value.split(".")
        return tmp[0].lstrip("-").isdigit() and tmp[1].isdigit()
    return value.lstrip("-").isdigit()


def add(*args):
    result = 0
    if args and is_num(args[0]):
        result = float(args[0])
        for i in args[1:]:
            if is_num(i):
                result += float(i)
            else:
                return None
        return f"{result:f}"
    return result


def sub(*args):
    result = 0
    if args and is_num(args[0]):
        result = float(args[0])
        for i in args[1:]:
            if is_num(i):
                result -= float(i)
            else:
                return None
        return f"{result:f}"
    return result


def multiply(*args):
    result = 0
    if args and is_num(args[0]):
        result = float(args[0])
        for i in args[1:]:
            if is_num(i):
                result *= float(i)
            else:
                return None
        return f"{result:f}"
    return result


def divide(*args):
    result = 0
    if args and is_num(args[0]):
        result = float(args[0])
        for i in args[1:]:
            if is_num(i) and float(i) != 0:
                result /= float(i)
            else:
                return None
        return f"{result:f}"
    return result


# ---------------------------------------------------------------------------
# regex filters
# ---------------------------------------------------------------------------

def regex_replace(value="", pattern="", replacement="", count=0, ignorecase=False, multiline=False):
    """Perform a `re.sub` returning a string."""
    value = to_text(value, errors="surrogate_or_strict", nonstring="simplerepr")

    flags = 0
    if ignorecase:
        flags |= re.I
    if multiline:
        flags |= re.M
    _re = re.compile(pattern, flags=flags)
    return _re.sub(replacement, value, count)


def regex_findall(value, pattern, ignorecase=False, multiline=False):
    """Perform re.findall and return the list of matches."""
    value = to_text(value, errors="surrogate_or_strict", nonstring="simplerepr")

    flags = 0
    if ignorecase:
        flags |= re.I
    if multiline:
        flags |= re.M
    return str(re.findall(pattern, value, flags))


def regex_search(value, pattern, *args, **kwargs):
    """Perform re.search and return the list of matches or a backref."""
    value = to_text(value, errors="surrogate_or_strict", nonstring="simplerepr")

    groups = []
    for arg in args:
        if arg.startswith("\\g"):
            match = re.match(r"\\g<(\S+)>", arg).group(1)
            groups.append(match)
        elif arg.startswith("\\"):
            match = int(re.match(r"\\(\d+)", arg).group(1))
            groups.append(match)
        else:
            raise ValueError("Unknown argument")

    flags = 0
    if kwargs.get("ignorecase"):
        flags |= re.I
    if kwargs.get("multiline"):
        flags |= re.M

    match = re.search(pattern, value, flags)
    if match:
        if not groups:
            return str(match.group())
        items = []
        for item in groups:
            items.append(match.group(item))
        return str(items)
    return None


def regex_escape(value, re_type="python"):
    value = to_text(value, errors="surrogate_or_strict", nonstring="simplerepr")
    if re_type == "python":
        return re.escape(value)
    if re_type == "posix_basic":
        return regex_escape_posix_basic(value)
    raise ValueError(f"Invalid regex type ({re_type})")


# ---------------------------------------------------------------------------
# misc filters
# ---------------------------------------------------------------------------

def ternary(value, true_val, false_val, none_val=None):
    """value ? true_val : false_val"""
    if (value is None or isinstance(value, Undefined)) and none_val is not None:
        return none_val
    if bool(value):
        return true_val
    return false_val


def get_random(min_num, max_num, unit):
    random_num = random.uniform(float(min_num), float(max_num))
    return f"{random_num:.{int(unit)}f}"


def random_fliter(*args, **kwargs):
    """random filter — numeric range or random.choice fallback (name matches original QD)."""
    try:
        result = get_random(*args, **kwargs)
    except Exception as e:
        logger.debug(e)
        result = random.choice(*args, **kwargs)
    return result


def randomize_list(mylist, seed=None):
    try:
        mylist = list(mylist)
        if seed:
            r = random.Random(seed)
            r.shuffle(mylist)
        else:
            random.shuffle(mylist)
    except Exception as e:
        logger.debug(e)
        raise e
    return mylist


def mandatory(value, msg=None):
    """Make a variable mandatory."""
    if isinstance(value, Undefined):
        # pylint: disable=protected-access
        if value._undefined_name is not None:
            name = f"'{to_text(value._undefined_name)}' "
        else:
            name = ""

        if msg is not None:
            raise ValueError(to_native(msg))
        raise ValueError(f"Mandatory variable {name} not defined.")

    return value


# ---------------------------------------------------------------------------
# filter registry (mirrors original QD jinja_globals / jinja_inner_globals)
# ---------------------------------------------------------------------------

jinja_globals = {
    # types
    "int": do_int,
    "float": do_float,
    "bool": to_bool,
    "utf8": utf8,
    "unicode": conver2unicode,
    "urlencode": urlencode_with_encoding,
    "quote_chinese": quote_chinese,
    # binascii
    "b2a_hex": b2a_hex,
    "a2b_hex": a2b_hex,
    "b2a_uu": b2a_uu,
    "a2b_uu": a2b_uu,
    "b2a_base64": b2a_base64,
    "a2b_base64": a2b_base64,
    "b2a_qp": b2a_qp,
    "a2b_qp": a2b_qp,
    "crc_hqx": crc_hqx,
    "crc32": crc32,
    # format
    "format": format,
    # base64
    "b64decode": b64decode,
    "b64encode": b64encode,
    # uuid
    "to_uuid": to_uuid,
    # hash filters
    "md5": md5string,
    "sha1": secure_hash_s,
    "password_hash": get_encrypted_password,
    "hash": get_hash,
    "aes_encrypt": _aes_encrypt,
    "aes_decrypt": _aes_decrypt,
    # time
    "timestamp": timestamp,
    "date_time": get_date_time,
    "strftime": strftime,
    # calculate
    "is_num": is_num,
    "add": add,
    "sub": sub,
    "multiply": multiply,
    "divide": divide,
    "Faker": Faker,
    # regex
    "regex_replace": regex_replace,
    "regex_escape": regex_escape,
    "regex_search": regex_search,
    "regex_findall": regex_findall,
    # ternary
    "ternary": ternary,
    # random
    "random": random_fliter,
    "shuffle": randomize_list,
    # undefined
    "mandatory": mandatory,
    # debug
    "type_debug": lambda value: value.__class__.__name__,
}

jinja_inner_globals = {
    "dict": dict,
    "lipsum": generate_lorem_ipsum,
    "range": range,
}
