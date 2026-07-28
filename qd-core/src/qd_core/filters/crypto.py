"""Crypto helpers for template filters (ported from QD v1 libs/mcrypto.py).

Provides AES encrypt/decrypt and passlib-based password hashing used by
original QD templates via the ``aes_encrypt`` / ``aes_decrypt`` /
``password_hash`` filters.
"""

import base64
import random
import re
import string
from binascii import a2b_hex, b2a_hex
from collections import namedtuple
from typing import Any, Optional, Union

from Crypto.Cipher import AES
from Crypto.Random import new as crypto_random_new
from Crypto.Util.Padding import pad, unpad

from qd_core.filters.convert import to_bytes, to_text

Crypto_random = crypto_random_new()

AES_MODE_MAP = {
    "CBC": AES.MODE_CBC,
    "ECB": AES.MODE_ECB,
    "CFB": AES.MODE_CFB,
    "OFB": AES.MODE_OFB,
    "CTR": AES.MODE_CTR,
    "OPENPGP": AES.MODE_OPENPGP,
    "GCM": AES.MODE_GCM,
    "CCM": AES.MODE_CCM,
    "SIV": AES.MODE_SIV,
    "OCB": AES.MODE_OCB,
    "EAX": AES.MODE_EAX,
}


def switch_mode(mode: str) -> int:
    """Convert an AES mode name (e.g. 'CBC') to a PyCryptodome mode constant."""
    mode_upper = mode.upper()
    if mode_upper not in AES_MODE_MAP:
        raise ValueError(f"Invalid AES mode: {mode}")
    return AES_MODE_MAP[mode_upper]


def aes_encrypt(
    word: bytes,
    key: bytes,
    mode: int = AES.MODE_CBC,
    iv: Optional[bytes] = None,
    output: str = "base64",
    padding: bool = True,
    padding_style: str = "pkcs7",
) -> Union[str, bytes]:
    """AES encrypt raw bytes, returning base64/hex text or raw bytes."""
    if iv is None:
        iv = Crypto_random.read(16)

    if padding:
        word = pad(word, AES.block_size, padding_style)

    if mode in (AES.MODE_ECB, AES.MODE_CTR):
        aes = AES.new(key, mode)
    else:
        aes = AES.new(key, mode, iv)

    ciphertext = aes.encrypt(word)
    output = output.lower()
    if output == "base64":
        return base64.encodebytes(ciphertext).decode("utf-8")
    if output == "hex":
        return b2a_hex(ciphertext).decode("utf-8")
    return ciphertext


def aes_decrypt(
    word: bytes,
    key: bytes,
    mode: int = AES.MODE_CBC,
    iv: Optional[bytes] = None,
    input: str = "base64",  # noqa: A002 - matches original QD filter signature
    padding: bool = True,
    padding_style: str = "pkcs7",
) -> Union[str, bytes]:
    """AES decrypt base64/hex/raw ciphertext, returning decoded utf-8 text."""
    input_format = input.lower()
    if input_format == "base64":
        word = base64.decodebytes(word)
    elif input_format == "hex":
        word = a2b_hex(word)

    if mode in (AES.MODE_ECB, AES.MODE_CTR):
        aes = AES.new(key, mode)
    else:
        aes = AES.new(key, mode, iv)
    plain = aes.decrypt(word)

    if padding:
        return unpad(plain, AES.block_size, padding_style).decode("utf-8")
    return plain


# ---------------------------------------------------------------------------
# passlib-based password hashing (used by the password_hash template filter)
# ---------------------------------------------------------------------------

DEFAULT_PASSWORD_LENGTH = 20
ASCII_LETTERS = string.ascii_letters
DIGITS = string.digits
DEFAULT_PASSWORD_CHARS = to_text(ASCII_LETTERS + DIGITS + ".,:-_", errors="strict")

PASSLIB_E: Optional[Exception] = None
PASSLIB_AVAILABLE = False
try:
    import passlib  # type: ignore  # noqa: F401
    import passlib.hash  # type: ignore
    from passlib.utils.handlers import HasRawSalt, PrefixWrapper  # type: ignore

    try:
        from passlib.utils.binary import bcrypt64  # type: ignore
    except ImportError:
        from passlib.utils import bcrypt64  # type: ignore

    PASSLIB_AVAILABLE = True
except Exception as e:  # pragma: no cover
    PASSLIB_E = e


def random_password(length: int = DEFAULT_PASSWORD_LENGTH, chars: str = DEFAULT_PASSWORD_CHARS, seed: Any = None) -> str:
    """Return a random password string of the given length containing only chars."""
    if not isinstance(chars, str):
        raise TypeError(f"{chars} ({type(chars)}) is not a text_type")

    if seed is None:
        random_generator = random.SystemRandom()
    else:
        random_generator = random.Random(seed)
    return "".join(random_generator.choice(chars) for _ in range(length))


def random_salt(length: int = 8) -> str:
    """Return a text string suitable for use as a hash salt."""
    salt_chars = string.ascii_letters + string.digits + "./"
    return random_password(length=length, chars=salt_chars)


class _BaseHash:
    algo = namedtuple("algo", ["crypt_id", "salt_size", "implicit_rounds", "salt_exact", "implicit_ident"])
    algorithms = {
        "md5_crypt": algo(crypt_id="1", salt_size=8, implicit_rounds=None, salt_exact=False, implicit_ident=None),
        "bcrypt": algo(crypt_id="2b", salt_size=22, implicit_rounds=12, salt_exact=True, implicit_ident="2b"),
        "sha256_crypt": algo(crypt_id="5", salt_size=16, implicit_rounds=535000, salt_exact=False, implicit_ident=None),
        "sha512_crypt": algo(crypt_id="6", salt_size=16, implicit_rounds=656000, salt_exact=False, implicit_ident=None),
    }

    def __init__(self, algorithm: str):
        self.algorithm = algorithm


class PasslibHash(_BaseHash):
    def __init__(self, algorithm: str):
        super().__init__(algorithm)

        if not PASSLIB_AVAILABLE:
            raise RuntimeError(f"passlib must be installed and usable to hash with '{algorithm}'") from PASSLIB_E

        try:
            self.crypt_algo = getattr(passlib.hash, algorithm)
        except Exception as e:
            raise ValueError(f"passlib does not support '{algorithm}' algorithm") from e

    def hash(self, secret, salt=None, salt_size=None, rounds=None, ident=None):
        salt = self._clean_salt(salt)
        rounds = self._clean_rounds(rounds)
        ident = self._clean_ident(ident)
        return self._hash(secret, salt=salt, salt_size=salt_size, rounds=rounds, ident=ident)

    def _clean_ident(self, ident):
        if not ident:
            if self.algorithm in self.algorithms:
                return self.algorithms[self.algorithm].implicit_ident
            return None
        if self.algorithm == "bcrypt":
            return ident
        return None

    def _clean_salt(self, salt):
        if not salt:
            return None
        if issubclass(
            self.crypt_algo.wrapped if isinstance(self.crypt_algo, PrefixWrapper) else self.crypt_algo,
            HasRawSalt,
        ):
            ret = to_bytes(salt, encoding="ascii", errors="strict")
        else:
            ret = to_text(salt, encoding="ascii", errors="strict")

        if self.algorithm == "bcrypt":
            ret = bcrypt64.repair_unused(ret)
        return ret

    def _clean_rounds(self, rounds):
        algo_data = self.algorithms.get(self.algorithm)
        if rounds:
            return rounds
        if algo_data and algo_data.implicit_rounds:
            return algo_data.implicit_rounds
        return None

    def _hash(self, secret, salt, salt_size, rounds, ident):
        settings = {}
        if salt:
            settings["salt"] = salt
        if salt_size:
            settings["salt_size"] = salt_size
        if rounds:
            settings["rounds"] = rounds
        if ident:
            settings["ident"] = ident

        if hasattr(self.crypt_algo, "hash"):
            result = self.crypt_algo.using(**settings).hash(secret)
        elif hasattr(self.crypt_algo, "encrypt"):
            result = self.crypt_algo.encrypt(secret, **settings)
        else:
            raise RuntimeError("installed passlib version not supported")

        if not result:
            raise RuntimeError(f"failed to hash with algorithm '{self.algorithm}'")

        return to_text(result, errors="strict")


def passlib_or_crypt(secret, algorithm, salt=None, salt_size=None, rounds=None, ident=None):
    """Hash a secret with passlib (crypt fallback removed — Python 3.13 dropped crypt)."""
    return PasslibHash(algorithm).hash(secret, salt=salt, salt_size=salt_size, rounds=rounds, ident=ident)


def regex_escape_posix_basic(value: str) -> str:
    """Escape POSIX BRE special characters."""
    return re.sub(r"([].[^$*\\])", r"\\\1", value)


# --- RSA (ported from QD v1 web/handlers/util.py UtilRSAHandler) ---

def _normalize_rsa_key(key: str) -> str:
    """Normalize a PEM key: accept single-line PEM (as QD v1 does) or standard PEM."""
    if "\n" in key.strip() and key.strip().count("\n") > 1:
        return key
    markers = re.findall(r"-----.*?-----", key)
    if len(markers) != 2:
        raise ValueError("证书格式错误 (invalid PEM markers)")
    body = key
    for m in markers:
        body = body.replace(m, "")
    body = body.strip().replace(" ", "")
    lines = "\n".join(body[i: i + 64] for i in range(0, len(body), 64))
    return markers[0] + "\n" + lines + "\n" + markers[1]


def rsa_encrypt(data: Union[str, bytes], key: str) -> str:
    """RSA PKCS1_v1_5 encrypt, returns base64 string (QD v1 compatible)."""
    from Crypto.Cipher import PKCS1_v1_5
    from Crypto.PublicKey import RSA

    if isinstance(data, str):
        data = data.encode("utf-8")
    cipher = PKCS1_v1_5.new(RSA.import_key(_normalize_rsa_key(key)))
    return base64.b64encode(cipher.encrypt(data)).decode("utf-8")


def rsa_decrypt(data: Union[str, bytes], key: str) -> str:
    """RSA PKCS1_v1_5 decrypt of a base64 string (QD v1 compatible)."""
    from Crypto.Cipher import PKCS1_v1_5
    from Crypto.PublicKey import RSA

    if isinstance(data, str):
        data = data.encode("utf-8")
    raw = base64.b64decode(data)
    cipher = PKCS1_v1_5.new(RSA.import_key(_normalize_rsa_key(key)))
    sentinel = crypto_random_new().read(16)
    result = cipher.decrypt(raw, sentinel)
    if result == sentinel:
        raise ValueError("RSA decrypt failed")
    return result.decode("utf-8")
