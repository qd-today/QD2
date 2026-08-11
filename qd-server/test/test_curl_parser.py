"""cURL import regression tests."""

from qd_server.api.test_request import _parse_curl_command


def test_parse_curl_preserves_cookie_short_option() -> None:
    parsed = _parse_curl_command(
        "curl 'https://example.test/check' -b 'session=abc123; theme=dark'"
    )

    assert parsed.url == "https://example.test/check"
    assert parsed.headers["Cookie"] == "session=abc123; theme=dark"


def test_parse_curl_combines_cookie_header_and_long_option() -> None:
    parsed = _parse_curl_command(
        "curl --url 'https://example.test/check' "
        "-H 'cookie: first=1' --cookie='second=2'"
    )

    assert parsed.headers["cookie"] == "first=1; second=2"


def test_cookie_jar_path_is_not_mistaken_for_url() -> None:
    parsed = _parse_curl_command(
        "curl -c cookies.txt -b 'session=abc123' https://example.test/check"
    )

    assert parsed.url == "https://example.test/check"
    assert parsed.headers["Cookie"] == "session=abc123"
