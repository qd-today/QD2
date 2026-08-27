"""HAR import regression tests."""

from qd_server.api.test_request import _parse_qd_v1, _parse_standard_har


def test_qd_v1_import_preserves_body_cookies_rules_and_duplicate_headers() -> None:
    parsed = _parse_qd_v1([
        {
            "comment": "Login",
            "request": {
                "method": "POST",
                "url": "https://example.test/login",
                "headers": [
                    {"name": "X-Trace", "value": "first", "checked": False},
                    {"name": "X-Trace", "value": "second"},
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": ":method", "value": "POST"},
                ],
                "cookies": [{"name": "device", "value": "abc", "path": "/"}],
                "data": '{"username":"{{username}}"}',
                "mimeType": "application/json",
                "extractors": {"legacy": "regex:value=(.+)"},
            },
            "rule": {
                "success_asserts": [{"re": "200", "from": "status"}],
                "failed_asserts": [],
                "extract_variables": [{"name": "sid", "re": "sid=(.+)", "from": "header-Set-Cookie"}],
            },
        }
    ])[0]

    assert parsed.body == '{"username":"{{username}}"}'
    assert parsed.body_type == "json"
    assert parsed.mime_type == "application/json"
    assert parsed.cookies == [{"name": "device", "value": "abc", "path": "/"}]
    assert parsed.header_list == [
        {"name": "X-Trace", "value": "first", "checked": False},
        {"name": "X-Trace", "value": "second", "checked": True},
        {"name": "Content-Type", "value": "application/json", "checked": True},
        {"name": ":method", "value": "POST", "checked": False},
    ]
    assert ":method" not in parsed.headers
    assert parsed.name == "Login"
    assert parsed.extractors == {"legacy": "regex:value=(.+)"}
    assert parsed.success_asserts == [{"re": "200", "from": "status"}]
    assert parsed.extract_variables == [
        {"name": "sid", "re": "sid=(.+)", "from": "header-Set-Cookie"}
    ]


def test_standard_har_import_preserves_form_params_cookies_rules_and_comment() -> None:
    parsed = _parse_standard_har([
        {
            "comment": "Submit",
            "checked": False,
            "_resourceType": "xhr",
            "request": {
                "method": "POST",
                "url": "https://example.test/form",
                "headers": [],
                "cookies": [{"name": "session", "value": "token"}],
                "postData": {
                    "mimeType": "application/x-www-form-urlencoded",
                    "params": [
                        {"name": "first", "value": "hello world"},
                        {"name": "second", "value": "2"},
                    ],
                },
            },
            "rule": {
                "success_asserts": [],
                "failed_asserts": [{"re": "denied", "from": "content"}],
                "extract_variables": [],
            },
            "response": {
                "headers": [{"name": "Set-Cookie", "value": "session=token; Path=/"}],
            },
        }
    ])[0]

    assert parsed.body == "first=hello+world&second=2"
    assert parsed.body_type == "form"
    assert parsed.mime_type == "application/x-www-form-urlencoded"
    assert parsed.cookies == [{"name": "session", "value": "token"}]
    assert parsed.failed_asserts == [{"re": "denied", "from": "content"}]
    assert parsed.name == "Submit"
    assert parsed.checked is False
    assert parsed.resource_type == "xhr"
    assert parsed.response_set_cookie is True
