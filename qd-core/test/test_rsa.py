"""Tests for RSA filters (QD v1 rsa_encrypt/rsa_decrypt compatibility)."""

from Crypto.PublicKey import RSA as RSAKey
import pytest

from qd_core.filters.crypto import rsa_decrypt, rsa_encrypt


def _keypair():
    key = RSAKey.generate(2048)
    return key.export_key().decode(), key.publickey().export_key().decode()


def test_rsa_roundtrip_standard_pem():
    priv, pub = _keypair()
    ct = rsa_encrypt("hello QD2 你好", pub)
    assert isinstance(ct, str) and len(ct) > 100
    assert rsa_decrypt(ct, priv) == "hello QD2 你好"


def test_rsa_single_line_pem():
    """QD v1 accepted single-line PEM (markers + body without newlines)."""
    priv, pub = _keypair()
    single_line_pub = pub.replace("\n", "")
    ct = rsa_encrypt("data123", single_line_pub)
    assert rsa_decrypt(ct, priv) == "data123"


def test_rsa_decrypt_bad_data():
    priv, _ = _keypair()
    import base64

    bogus = base64.b64encode(b"\x00" * 256).decode()
    with pytest.raises(ValueError):
        rsa_decrypt(bogus, priv)


def test_rsa_rejects_invalid_pem():
    with pytest.raises(ValueError, match="invalid PEM markers"):
        rsa_encrypt("data", "not-a-key")


def test_rsa_in_jinja_render():
    from qd_core.client.render import render_string

    priv, pub = _keypair()
    ct = render_string("{{ rsa_encrypt('secret', pub) }}", {"pub": pub})
    plain = render_string("{{ rsa_decrypt(ct, priv) }}", {"ct": ct, "priv": priv})
    assert plain == "secret"
